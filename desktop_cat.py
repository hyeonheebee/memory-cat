#!/usr/bin/env python3
"""메모리 뚱냥이 — macOS 바탕화면 둥둥 버전.

항상 위에 떠 있는 작은 고양이. 디스크(하드 용량)가 차오를수록
애기냥 -> 돼지냥으로 빵빵해지며 살짝 통통 튄다. 라벨에 디스크/램 표시.
우클릭: AI 진단 + 성격 + 테마 + 크기 + 새로고침/종료. 설정은 config.json 에 저장.

테마는 frames/<이름>/ 폴더를 자동 인식한다. 새 테마 추가:
  python import_theme.py 내이미지.png 테마이름   (가로 N단계 시트)
"""
import json
import os
import threading

import objc
from AppKit import (
    NSApplication, NSApplicationActivationPolicyAccessory, NSWindow,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered, NSColor, NSView,
    NSImage, NSMenu, NSMenuItem, NSTimer, NSScreen, NSFont, NSFontAttributeName,
    NSForegroundColorAttributeName, NSShadow, NSShadowAttributeName,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSCompositingOperationSourceOver, NSCompositingOperationCopy,
    NSRectFillUsingOperation, NSApp,
    NSAlert, NSTextField, NSAlertFirstButtonReturn, NSAlertSecondButtonReturn,
    NSOpenPanel, NSModalResponseOK,
)
from Foundation import (
    NSObject, NSMakeRect, NSMakePoint, NSMakeSize, NSAttributedString,
    NSOperationQueue, NSUserNotification, NSUserNotificationCenter,
)

import metrics as mc
from brain import diagnose as run_diagnosis, safe_trash
from i18n import (
    LANGUAGE_AUTO,
    LANGUAGE_EN,
    LANGUAGE_KO,
    LANGUAGE_OVERRIDES,
    chonk_stage,
    diagnosis_personality_descriptor,
    resolve_language,
    tr,
)
from personality import (
    CUSTOM_PERSONALITY,
    DEFAULT_PERSONALITY,
    config_personality,
    normalize_custom_personality,
    preset_label,
    preset_names,
)
from vision_theme import ThemeGenerationError, build_theme as build_pet_theme

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES_BASE = os.path.join(HERE, "frames")
CONFIG = os.path.join(HERE, "config.json")
REFRESH_SEC = 4.0
DISK_FULL_PROMPT_PERCENT = 92.0
NSStatusWindowLevel = 25
CATBOTTOM = 46.0

THEME_STRING_KEYS = {
    "cute": "theme_cute",
    "simple": "theme_simple",
    "madness": "theme_madness",
    "derpy": "theme_derpy",
}
THEME_ORDER = ["cute", "simple", "madness", "derpy"]
SIZES = {"작게": 78.0, "보통": 104.0, "크게": 138.0, "왕": 176.0}
SIZE_STRING_KEYS = {
    "작게": "size_small",
    "보통": "size_medium",
    "크게": "size_large",
    "왕": "size_king",
}
DEFAULT = {
    "theme": "cute",
    "size": "보통",
    "personality": DEFAULT_PERSONALITY,
    "custom_personality": "",
    "language": LANGUAGE_AUTO,
}


def config_path():
    """Return the runtime config path, honoring the demo override."""
    return os.environ.get("MEMORY_CAT_CONFIG") or CONFIG


def load_config(path=None):
    if path is None:
        path = config_path()
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception:
        loaded = {}

    cfg = dict(DEFAULT)
    if isinstance(loaded, dict):
        cfg["theme"] = loaded.get("theme", DEFAULT["theme"])
        size = loaded.get("size", DEFAULT["size"])
        cfg["size"] = size if size in SIZES else DEFAULT["size"]
        selection, custom = config_personality(loaded)
        cfg["personality"] = selection
        cfg["custom_personality"] = custom
        language = loaded.get("language", LANGUAGE_AUTO)
        cfg["language"] = language if language in LANGUAGE_OVERRIDES else LANGUAGE_AUTO
    return cfg


def save_config(cfg, path=None):
    if path is None:
        path = config_path()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False)
        return True
    except Exception:
        return False


def diagnosis_notification_text(result, language=LANGUAGE_KO):
    """진단 JSON을 macOS 알림에 들어갈 짧은 텍스트로 만든다."""
    why = [str(line).strip() for line in result.get("why_slow", []) if str(line).strip()]
    advice = str(result.get("one_line_advice", "")).strip()
    lines = [f"• {line}" for line in why[:3]]
    if advice:
        lines.append(f"🐾 {advice}")
    return "\n".join(lines) or tr(language, "diagnosis_empty")


def diagnosis_result_content(result, personality_label, language=LANGUAGE_KO):
    """진단 JSON을 결과창에서 읽기 쉬운 제목·본문·동작으로 바꾼다."""
    if result.get("source") == "openai":
        title = tr(
            language,
            "diagnosis_result_openai_title",
            personality=diagnosis_personality_descriptor(
                personality_label, language
            ),
        )
        source = None
    else:
        title = tr(language, "diagnosis_result_fallback_title")
        reason_key = {
            "missing_api_key": "fallback_missing_api_key",
            "api_error": "fallback_api_error",
            "worker_error": "fallback_worker_error",
        }.get(result.get("fallback_reason"), "fallback_unknown")
        source = tr(
            language,
            "diagnosis_source_fallback",
            reason=tr(language, reason_key),
        )

    why = [str(line).strip() for line in result.get("why_slow", []) if str(line).strip()]
    causes = "\n".join(f"• {line}" for line in why) or tr(language, "diagnosis_empty")
    advice = str(result.get("one_line_advice", "")).strip() or tr(
        language, "diagnosis_empty"
    )
    reclaimable = str(result.get("estimated_reclaimable", "0 B"))
    body = "\n\n".join(
        part
        for part in (
            source,
            causes,
            f"{tr(language, 'diagnosis_advice_heading')}\n{advice}",
            tr(language, "diagnosis_reclaimable", size=reclaimable),
        )
        if part
    )
    cleanup_count = sum(
        len(recommendation.get("items", []))
        for recommendation in result.get("cleanup_recommendations", [])
    )
    return {
        "title": title,
        "body": body,
        "can_review_cleanup": cleanup_count > 0,
    }


def _diagnosis_worker(personality, custom_personality, language, callback):
    """API/측정을 작업 스레드에서 수행하고 callback만 메인 큐로 보낸다."""
    try:
        result = run_diagnosis(
            personality=personality,
            custom_personality=custom_personality,
            language=language,
        )
    except Exception:
        result = {
            "why_slow": [tr(language, "diagnosis_error")],
            "one_line_advice": tr(language, "retry_later"),
            "cleanup_recommendations": [],
            "source": "fallback",
            "fallback_reason": "worker_error",
        }
    NSOperationQueue.mainQueue().addOperationWithBlock_(lambda: callback(result))


def _pet_theme_worker(photo_path, theme_name, callback):
    """Build a pet theme off the UI thread and return on the main queue."""
    try:
        result = dict(build_pet_theme(photo_path, theme_name, "medium"))
        result["theme_name"] = theme_name
    except ThemeGenerationError as exc:
        result = {"theme_name": theme_name, "error": str(exc)}
    except Exception as exc:
        result = {"theme_name": theme_name, "error": str(exc)}
    NSOperationQueue.mainQueue().addOperationWithBlock_(lambda: callback(result))


def process_cleanup_recommendations(recommendations, confirm_item, trash_func=None):
    """각 항목을 확인받은 뒤에만 safe_trash를 호출한다."""
    trash_func = safe_trash if trash_func is None else trash_func
    summary = {"moved": 0, "already_in_trash": 0, "skipped": 0, "failed": 0}
    for recommendation in recommendations:
        for item in recommendation.get("items", []):
            path = item.get("path")
            if not path or not confirm_item(recommendation, item):
                summary["skipped"] += 1
                continue
            try:
                trash_func(path)
                if recommendation.get("category") == "trash":
                    summary["already_in_trash"] += 1
                else:
                    summary["moved"] += 1
            except Exception:
                summary["failed"] += 1
    return summary


def discover_themes():
    """frames/ 안의 테마 폴더 자동 인식. 알려진 것 먼저, 나머지 알파벳순."""
    found = []
    if os.path.isdir(FRAMES_BASE):
        for n in sorted(os.listdir(FRAMES_BASE)):
            d = os.path.join(FRAMES_BASE, n)
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "cat_00.png")):
                found.append(n)
    return ([t for t in THEME_ORDER if t in found]
            + [t for t in found if t not in THEME_ORDER])


def next_pet_theme_name(frames_base=None):
    """Return mypet, mypet2, ... without overwriting an existing path."""
    root = FRAMES_BASE if frames_base is None else os.fspath(frames_base)
    candidate = "mypet"
    suffix = 2
    while os.path.exists(os.path.join(root, candidate)):
        candidate = f"mypet{suffix}"
        suffix += 1
    return candidate


def theme_label(key, language=LANGUAGE_KO):
    string_key = THEME_STRING_KEYS.get(key)
    return tr(language, string_key) if string_key else key


def size_label(key, language=LANGUAGE_KO):
    string_key = SIZE_STRING_KEYS.get(key)
    return tr(language, string_key) if string_key else key


def frame_count(theme):
    d = os.path.join(FRAMES_BASE, theme)
    try:
        return max(1, len([f for f in os.listdir(d)
                           if f.startswith("cat_") and f.endswith(".png")]))
    except Exception:
        return 1


def frame_path(theme, idx):
    n = frame_count(theme)
    idx = max(0, min(n - 1, idx))
    return os.path.join(FRAMES_BASE, theme, f"cat_{idx:02d}.png")


def layout_for(cat):
    return cat + 24.0, cat + CATBOTTOM + 8.0


class CatView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(CatView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._image = None
        self._l1, self._l2 = "…", ""
        self._bob = 0.0
        self._cat = 100.0
        self._controller = None
        return self

    def setController_(self, c):
        self._controller = c

    def setCat_(self, cat):
        self._cat = cat

    def updateImage_l1_l2_(self, image, l1, l2):
        self._image, self._l1, self._l2 = image, l1, l2
        self.setNeedsDisplay_(True)

    def setBob_(self, v):
        self._bob = v
        self.setNeedsDisplay_(True)

    def mouseDownCanMoveWindow(self):
        return True

    def drawRect_(self, rect):
        NSColor.clearColor().set()
        NSRectFillUsingOperation(self.bounds(), NSCompositingOperationCopy)
        w = self.frame().size.width
        if self._image is not None:
            x = (w - self._cat) / 2.0
            self._image.drawInRect_fromRect_operation_fraction_(
                NSMakeRect(x, CATBOTTOM + self._bob, self._cat, self._cat),
                NSMakeRect(0, 0, 0, 0), NSCompositingOperationSourceOver, 1.0)
        self._line_size_y_w_(self._l1, 14, 24, w)
        self._line_size_y_w_(self._l2, 12, 7, w)

    def _line_size_y_w_(self, text, fsize, y, w):
        if not text:
            return
        shadow = NSShadow.alloc().init()
        shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.9))
        shadow.setShadowBlurRadius_(2.5)
        shadow.setShadowOffset_(NSMakeSize(0, -1))
        attrs = {
            NSFontAttributeName: NSFont.boldSystemFontOfSize_(fsize),
            NSForegroundColorAttributeName: NSColor.whiteColor(),
            NSShadowAttributeName: shadow,
        }
        s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
        s.drawAtPoint_(NSMakePoint((w - s.size().width) / 2.0, y))

    def rightMouseDown_(self, event):
        if self._controller is not None:
            self._controller.popUpMenu_(event)


class CatController(NSObject):
    def initWithView_window_(self, view, window):
        self = objc.super(CatController, self).init()
        if self is None:
            return None
        self.view = view
        self.window = window
        self.cfg = load_config()
        self.language = resolve_language(self.cfg["language"])
        themes = discover_themes()
        if themes and self.cfg["theme"] not in themes:
            self.cfg["theme"] = themes[0]
        self.phase = 0.0
        self.score = 0.0
        self.detail = []
        self._diagnosis_running = False
        self._diagnosis_thread = None
        self._active_diagnosis_context = None
        self._last_diagnosis = None
        self._last_diagnosis_context = None
        self._pet_theme_running = False
        self._pet_theme_thread = None
        self._disk_full_prompt_shown = False
        self._notification_center = (
            NSUserNotificationCenter.defaultUserNotificationCenter()
        )
        try:
            self._notification_center.setDelegate_(self)
        except Exception:
            pass
        return self

    def start(self):
        self.applyLayout()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            REFRESH_SEC, self, b"refresh:", None, True)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.06, self, b"animate:", None, True)

    def applyLayout(self):
        cat = SIZES.get(self.cfg["size"], SIZES["보통"])
        w, h = layout_for(cat)
        fr = self.window.frame()
        top = fr.origin.y + fr.size.height
        self.window.setFrame_display_(NSMakeRect(fr.origin.x, top - h, w, h), True)
        self.view.setFrame_(NSMakeRect(0, 0, w, h))
        self.view.setCat_(cat)
        self.refresh_(None)

    def animate_(self, timer):
        import math
        self.phase += 0.13
        self.view.setBob_(math.sin(self.phase) * (2.0 + 3.0 * self.score / 100.0))

    def refresh_(self, timer):
        disk = mc.disk_usage()
        score, vm, sw = mc.pressure_score()
        dpct = disk.percent
        self.score = dpct
        self._maybe_prompt_disk_full(dpct)
        theme = self.cfg["theme"]
        n = frame_count(theme)
        idx = int(round(dpct / 100 * (n - 1)))
        img = NSImage.alloc().initWithContentsOfFile_(frame_path(theme, idx))
        language = self.language
        self.view.updateImage_l1_l2_(
            img,
            f"{tr(language, 'disk')} {dpct:.0f}%",
            f"{tr(language, 'ram')} {vm.percent:.0f}%",
        )

        mood = chonk_stage(dpct, language)
        self.detail = [
            tr(language, "mood_detail", mood=mood, percent=round(dpct)),
            tr(language, "disk_detail", percent=dpct, used=mc.human_gb(disk.used), total=mc.human_gb(disk.total), free=mc.human_gb(disk.free)),
            tr(language, "ram_detail", percent=vm.percent, used=mc.human_gb(vm.used), total=mc.human_gb(vm.total)),
        ]
        if sw.total > 0:
            self.detail.append(tr(language, "swap_detail", percent=sw.percent, used=mc.human_gb(sw.used), total=mc.human_gb(sw.total)))
        self.detail.append(tr(language, "memory_apps"))
        try:
            for name, rss in mc.top_memory_apps():
                self.detail.append(f"{rss / 1024 ** 2:,.0f} MB   {name}")
        except Exception:
            pass

    def setTheme_(self, sender):
        self.cfg["theme"] = sender.representedObject()
        save_config(self.cfg)
        self.refresh_(None)

    def makePetTheme_(self, sender):
        if getattr(self, "_pet_theme_running", False):
            return

        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setAllowedFileTypes_(["png", "jpg", "jpeg", "heic"])
        NSApp.activateIgnoringOtherApps_(True)
        if panel.runModal() != NSModalResponseOK:
            return

        selected_url = panel.URL()
        photo_path = selected_url.path() if selected_url is not None else None
        if not photo_path:
            return

        alert = NSAlert.alloc().init()
        alert.setMessageText_(tr(self.language, "pet_theme_consent_title"))
        alert.setInformativeText_(tr(self.language, "pet_theme_consent_body"))
        alert.addButtonWithTitle_(tr(self.language, "pet_theme_continue"))
        alert.addButtonWithTitle_(tr(self.language, "cancel"))
        if alert.runModal() != NSAlertFirstButtonReturn:
            return

        theme_name = next_pet_theme_name()
        self._pet_theme_running = True
        self._pet_theme_thread = threading.Thread(
            target=_pet_theme_worker,
            args=(photo_path, theme_name, self._finish_pet_theme),
            name="memory-cat-pet-theme",
            daemon=True,
        )
        self._pet_theme_thread.start()

    @objc.python_method
    def _finish_pet_theme(self, result):
        self._pet_theme_running = False
        error = result.get("error")
        if error:
            title = tr(self.language, "pet_theme_error_title")
            if not self._notify(title, error):
                self._show_information_alert(title, error)
            return

        theme_name = result["theme_name"]
        self.cfg["theme"] = theme_name
        save_config(self.cfg)
        self.refresh_(None)
        title = tr(self.language, "pet_theme_complete_title")
        body = tr(
            self.language,
            "pet_theme_complete_body",
            count=result.get("detected_stages", 0),
            theme=theme_name,
        )
        if not self._notify(title, body):
            self._show_information_alert(title, body)

    def setSize_(self, sender):
        self.cfg["size"] = sender.representedObject()
        save_config(self.cfg)
        self.applyLayout()

    def setPersonality_(self, sender):
        self.cfg["personality"] = sender.representedObject()
        save_config(self.cfg)
        label = preset_label(self.cfg["personality"], self.language)
        self._notify(tr(self.language, "personality_changed_title"), tr(self.language, "personality_changed_body", personality=label))

    def setCustomPersonality_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(tr(self.language, "custom_title"))
        alert.setInformativeText_(tr(self.language, "custom_hint"))
        alert.addButtonWithTitle_(tr(self.language, "save"))
        alert.addButtonWithTitle_(tr(self.language, "cancel"))
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 380, 28))
        field.setStringValue_(self.cfg.get("custom_personality", ""))
        alert.setAccessoryView_(field)
        NSApp.activateIgnoringOtherApps_(True)
        if alert.runModal() != NSAlertFirstButtonReturn:
            return

        custom = normalize_custom_personality(field.stringValue())
        if not custom:
            self._notify(tr(self.language, "custom_empty_title"), tr(self.language, "custom_empty_body"))
            return
        self.cfg["personality"] = CUSTOM_PERSONALITY
        self.cfg["custom_personality"] = custom
        save_config(self.cfg)
        self._notify(tr(self.language, "custom_saved_title"), custom)

    def setLanguage_(self, sender):
        self.cfg["language"] = sender.representedObject()
        self.language = resolve_language(self.cfg["language"])
        save_config(self.cfg)
        self.refresh_(None)
        selected = tr(self.language, f"language_{self.language}")
        self._notify(tr(self.language, "language_changed_title"), tr(self.language, "language_changed_body", language=selected))

    def showLastDiagnosis_(self, sender):
        result = getattr(self, "_last_diagnosis", None)
        context = getattr(self, "_last_diagnosis_context", None)
        if result is not None and context is not None:
            self._show_diagnosis_result(result, context, allow_cleanup=False)

    def diagnose_(self, sender):
        if self._diagnosis_running:
            self._notify(tr(self.language, "diagnosis_already_title"), tr(self.language, "diagnosis_already_body"))
            return
        personality, custom = config_personality(self.cfg)
        personality_display = (
            tr(self.language, "personality_custom_label")
            if personality == CUSTOM_PERSONALITY
            else preset_label(personality, self.language)
        )
        self._active_diagnosis_context = {
            "personality": personality,
            "personality_label": personality_display,
            "language": self.language,
        }
        self._diagnosis_running = True
        self._notify(tr(self.language, "diagnosis_running_title"), tr(self.language, "diagnosis_running_body"))
        self._diagnosis_thread = threading.Thread(
            target=_diagnosis_worker,
            args=(personality, custom, self.language, self._finish_diagnosis),
            name="memory-cat-diagnosis",
            daemon=True,
        )
        self._diagnosis_thread.start()

    @objc.python_method
    def _maybe_prompt_disk_full(self, disk_percent):
        if getattr(self, "_disk_full_prompt_shown", False):
            return False
        if disk_percent < DISK_FULL_PROMPT_PERCENT:
            return False
        self._disk_full_prompt_shown = True
        self._show_disk_full_prompt()
        return True

    @objc.python_method
    def _show_disk_full_prompt(self):
        notification = NSUserNotification.alloc().init()
        notification.setTitle_(tr(self.language, "disk_full_prompt_title"))
        notification.setInformativeText_(
            tr(self.language, "disk_full_prompt_body")
        )
        notification.setHasActionButton_(True)
        notification.setActionButtonTitle_(
            tr(self.language, "disk_full_prompt_action")
        )
        notification.setUserInfo_({"memory_cat_action": "diagnose"})
        center = getattr(self, "_notification_center", None)
        if center is None:
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
            self._notification_center = center
        try:
            center.setDelegate_(self)
        except Exception:
            pass
        center.deliverNotification_(notification)

    def userNotificationCenter_didActivateNotification_(
        self, center, notification
    ):
        user_info = dict(notification.userInfo() or {})
        if user_info.get("memory_cat_action") != "diagnose":
            return
        center.removeDeliveredNotification_(notification)
        self.diagnose_(None)

    def userNotificationCenter_shouldPresentNotification_(
        self, center, notification
    ):
        return True

    @objc.python_method
    def _finish_diagnosis(self, result):
        self._diagnosis_running = False
        context = getattr(self, "_active_diagnosis_context", None)
        if context is None:
            cfg = getattr(self, "cfg", DEFAULT)
            personality, _ = config_personality(cfg)
            language = getattr(self, "language", LANGUAGE_KO)
            context = {
                "personality": personality,
                "personality_label": (
                    tr(language, "personality_custom_label")
                    if personality == CUSTOM_PERSONALITY
                    else preset_label(personality, language)
                ),
                "language": language,
            }
        self._active_diagnosis_context = None
        self._last_diagnosis = result
        self._last_diagnosis_context = dict(context)

        language = context["language"]
        body = diagnosis_notification_text(result, language)
        title = diagnosis_result_content(
            result,
            personality_label=context["personality_label"],
            language=language,
        )["title"]
        if not self._notify(title, body):
            self._show_information_alert(title, body)

        recommendations = result.get("cleanup_recommendations", [])
        wants_cleanup = self._show_diagnosis_result(
            result, self._last_diagnosis_context, allow_cleanup=True
        )
        if (
            wants_cleanup
            and recommendations
            and self._confirm_cleanup_review(recommendations)
        ):
            summary = process_cleanup_recommendations(
                recommendations, self._confirm_cleanup_item
            )
            self._show_cleanup_summary(summary)

    @objc.python_method
    def _show_diagnosis_result(self, result, context, allow_cleanup):
        language = context["language"]
        content = diagnosis_result_content(
            result,
            personality_label=context["personality_label"],
            language=language,
        )
        alert = NSAlert.alloc().init()
        alert.setMessageText_(content["title"])
        alert.setInformativeText_(content["body"])
        alert.addButtonWithTitle_(tr(language, "close"))
        can_review = allow_cleanup and content["can_review_cleanup"]
        if can_review:
            alert.addButtonWithTitle_(tr(language, "review_items"))
        NSApp.activateIgnoringOtherApps_(True)
        response = alert.runModal()
        return can_review and response == NSAlertSecondButtonReturn

    @objc.python_method
    def _notify(self, title, body):
        try:
            notification = NSUserNotification.alloc().init()
            notification.setTitle_(title)
            notification.setInformativeText_(body)
            center = getattr(self, "_notification_center", None)
            if center is None:
                center = NSUserNotificationCenter.defaultUserNotificationCenter()
                self._notification_center = center
            center.deliverNotification_(notification)
            return True
        except Exception:
            return False

    @objc.python_method
    def _show_information_alert(self, title, body):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(body)
        alert.addButtonWithTitle_(tr(self.language, "confirm"))
        NSApp.activateIgnoringOtherApps_(True)
        alert.runModal()

    @objc.python_method
    def _confirm_cleanup_review(self, recommendations):
        count = sum(len(item.get("items", [])) for item in recommendations)
        if count == 0:
            return False
        alert = NSAlert.alloc().init()
        alert.setMessageText_(tr(self.language, "cleanup_review_title"))
        alert.setInformativeText_(tr(self.language, "cleanup_review_body", count=count))
        alert.addButtonWithTitle_(tr(self.language, "review_items"))
        alert.addButtonWithTitle_(tr(self.language, "later"))
        NSApp.activateIgnoringOtherApps_(True)
        return alert.runModal() == NSAlertFirstButtonReturn

    @objc.python_method
    def _confirm_cleanup_item(self, recommendation, item):
        category = recommendation.get("category")
        path = item.get("path", "")
        size = item.get("size", tr(self.language, "unknown_size"))
        reason = recommendation.get("reason", "")
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"{recommendation.get('label', tr(self.language, 'cleanup_candidate'))} · {size}")
        if category == "trash":
            action_note = tr(self.language, "trash_review_note")
            primary = tr(self.language, "confirm")
        else:
            action_note = tr(self.language, "move_question")
            primary = tr(self.language, "move_to_trash")
        alert.setInformativeText_(f"{path}\n\n{reason}\n{action_note}")
        alert.addButtonWithTitle_(primary)
        alert.addButtonWithTitle_(tr(self.language, "skip"))
        NSApp.activateIgnoringOtherApps_(True)
        return alert.runModal() == NSAlertFirstButtonReturn

    @objc.python_method
    def _show_cleanup_summary(self, summary):
        parts = []
        if summary["moved"]:
            parts.append(tr(self.language, "summary_moved", count=summary["moved"]))
        if summary["already_in_trash"]:
            parts.append(tr(self.language, "summary_in_trash", count=summary["already_in_trash"]))
        if summary["skipped"]:
            parts.append(tr(self.language, "summary_skipped", count=summary["skipped"]))
        if summary["failed"]:
            parts.append(tr(self.language, "summary_failed", count=summary["failed"]))
        body = " · ".join(parts) or tr(self.language, "summary_none")
        if summary["moved"]:
            body += tr(self.language, "summary_reclaim_note")
        self._notify(tr(self.language, "cleanup_result_title"), body)

    def popUpMenu_(self, event):
        menu = NSMenu.alloc().init()
        for line in self.detail:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(line, None, "")
            it.setEnabled_(False)
            menu.addItem_(it)
        menu.addItem_(NSMenuItem.separatorItem())

        has_last_diagnosis = getattr(self, "_last_diagnosis", None) is not None
        if self._diagnosis_running:
            diagnose_key = "menu_diagnosing"
        elif has_last_diagnosis:
            diagnose_key = "menu_diagnose_again"
        else:
            diagnose_key = "menu_diagnose"
        diagnose_title = tr(self.language, diagnose_key)
        di = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            diagnose_title, b"diagnose:", ""
        )
        di.setTarget_(self)
        di.setEnabled_(not self._diagnosis_running)
        menu.addItem_(di)
        if has_last_diagnosis and not self._diagnosis_running:
            last_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                tr(self.language, "menu_last_diagnosis"),
                b"showLastDiagnosis:",
                "",
            )
            last_item.setTarget_(self)
            menu.addItem_(last_item)
        menu.addItem_(NSMenuItem.separatorItem())

        theme_menu = NSMenu.alloc().init()
        for key in discover_themes():
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(theme_label(key, self.language), b"setTheme:", "")
            it.setTarget_(self)
            it.setRepresentedObject_(key)
            if key == self.cfg["theme"]:
                it.setState_(1)
            theme_menu.addItem_(it)
        ti = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(tr(self.language, "menu_theme"), None, "")
        ti.setSubmenu_(theme_menu)
        menu.addItem_(ti)

        pet_theme_running = getattr(self, "_pet_theme_running", False)
        pet_theme_key = (
            "menu_pet_theme_running" if pet_theme_running else "menu_pet_theme"
        )
        pet_theme_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            tr(self.language, pet_theme_key), b"makePetTheme:", ""
        )
        pet_theme_item.setTarget_(self)
        pet_theme_item.setEnabled_(not pet_theme_running)
        menu.addItem_(pet_theme_item)

        size_menu = NSMenu.alloc().init()
        for label in SIZES:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(size_label(label, self.language), b"setSize:", "")
            it.setTarget_(self)
            it.setRepresentedObject_(label)
            if label == self.cfg["size"]:
                it.setState_(1)
            size_menu.addItem_(it)
        si = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(tr(self.language, "menu_size"), None, "")
        si.setSubmenu_(size_menu)
        menu.addItem_(si)

        personality_menu = NSMenu.alloc().init()
        for name in preset_names():
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                preset_label(name, self.language), b"setPersonality:", ""
            )
            it.setTarget_(self)
            it.setRepresentedObject_(name)
            if name == self.cfg["personality"]:
                it.setState_(1)
            personality_menu.addItem_(it)
        custom_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            tr(self.language, "menu_custom"), b"setCustomPersonality:", ""
        )
        custom_item.setTarget_(self)
        if self.cfg["personality"] == CUSTOM_PERSONALITY:
            custom_item.setState_(1)
        personality_menu.addItem_(custom_item)
        pi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(tr(self.language, "menu_personality"), None, "")
        pi.setSubmenu_(personality_menu)
        menu.addItem_(pi)

        language_menu = NSMenu.alloc().init()
        for override in LANGUAGE_OVERRIDES:
            if override == LANGUAGE_AUTO:
                current = tr(self.language, f"language_{self.language}")
                label = tr(self.language, "language_auto", language=current)
            else:
                label = tr(self.language, f"language_{override}")
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, b"setLanguage:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(override)
            if override == self.cfg["language"]:
                item.setState_(1)
            language_menu.addItem_(item)
        language_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            tr(self.language, "menu_language"), None, ""
        )
        language_item.setSubmenu_(language_menu)
        menu.addItem_(language_item)

        menu.addItem_(NSMenuItem.separatorItem())
        r = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(tr(self.language, "menu_refresh"), b"refresh:", "")
        r.setTarget_(self)
        menu.addItem_(r)
        q = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(tr(self.language, "menu_quit"), b"quit:", "")
        q.setTarget_(self)
        menu.addItem_(q)
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self.view)

    def quit_(self, sender):
        NSApp.terminate_(self)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    cfg = load_config()
    cat = SIZES.get(cfg["size"], SIZES["보통"])
    w, h = layout_for(cat)
    screen = NSScreen.mainScreen().frame()
    rect = NSMakeRect(screen.size.width - w - 40, screen.size.height - h - 80, w, h)
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
    window.setOpaque_(False)
    window.setBackgroundColor_(NSColor.clearColor())
    window.setLevel_(NSStatusWindowLevel)
    window.setMovableByWindowBackground_(True)
    window.setHasShadow_(False)
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorStationary)

    view = CatView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    window.setContentView_(view)
    controller = CatController.alloc().initWithView_window_(view, window)
    view.setController_(controller)

    window.orderFrontRegardless()
    controller.start()
    app.run()


if __name__ == "__main__":
    main()
