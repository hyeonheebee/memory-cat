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
    NSAlert, NSTextField, NSAlertFirstButtonReturn,
)
from Foundation import (
    NSObject, NSMakeRect, NSMakePoint, NSMakeSize, NSAttributedString,
    NSOperationQueue, NSUserNotification, NSUserNotificationCenter,
)

import metrics as mc
from brain import diagnose as run_diagnosis, safe_trash
from personality import (
    CUSTOM_PERSONALITY,
    DEFAULT_PERSONALITY,
    config_personality,
    normalize_custom_personality,
    preset_names,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES_BASE = os.path.join(HERE, "frames")
CONFIG = os.path.join(HERE, "config.json")
REFRESH_SEC = 4.0
NSStatusWindowLevel = 25
CATBOTTOM = 46.0

THEME_LABELS = {"cute": "귀여운", "simple": "단순한", "madness": "광기", "derpy": "경각심"}
THEME_ORDER = ["cute", "simple", "madness", "derpy"]
SIZES = {"작게": 78.0, "보통": 104.0, "크게": 138.0, "왕": 176.0}
DEFAULT = {
    "theme": "cute",
    "size": "보통",
    "personality": DEFAULT_PERSONALITY,
    "custom_personality": "",
}


def load_config(path=CONFIG):
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
    return cfg


def save_config(cfg, path=CONFIG):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False)
        return True
    except Exception:
        return False


def diagnosis_notification_text(result):
    """진단 JSON을 macOS 알림에 들어갈 짧은 텍스트로 만든다."""
    why = [str(line).strip() for line in result.get("why_slow", []) if str(line).strip()]
    advice = str(result.get("one_line_advice", "")).strip()
    lines = [f"• {line}" for line in why[:3]]
    if advice:
        lines.append(f"🐾 {advice}")
    return "\n".join(lines) or "진단 결과를 만들지 못했습니다. 잠시 후 다시 시도해 주세요."


def _diagnosis_worker(personality, custom_personality, callback):
    """API/측정을 작업 스레드에서 수행하고 callback만 메인 큐로 보낸다."""
    try:
        result = run_diagnosis(
            personality=personality,
            custom_personality=custom_personality,
        )
    except Exception:
        result = {
            "why_slow": ["진단 데이터를 읽는 중 문제가 생겼습니다."],
            "one_line_advice": "잠시 후 다시 시도해 주세요.",
            "cleanup_recommendations": [],
            "source": "fallback",
        }
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


def theme_label(key):
    return THEME_LABELS.get(key, key)


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
        themes = discover_themes()
        if themes and self.cfg["theme"] not in themes:
            self.cfg["theme"] = themes[0]
        self.phase = 0.0
        self.score = 0.0
        self.detail = []
        self._diagnosis_running = False
        self._diagnosis_thread = None
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
        theme = self.cfg["theme"]
        n = frame_count(theme)
        idx = int(round(dpct / 100 * (n - 1)))
        img = NSImage.alloc().initWithContentsOfFile_(frame_path(theme, idx))
        self.view.updateImage_l1_l2_(
            img, f"디스크 {dpct:.0f}%", f"램 {vm.percent:.0f}%")

        mood = ("여유 😺" if dpct < 60 else "포동 🐈" if dpct < 80
                else "배불러 🍙" if dpct < 92 else "빵빵! 🐷")
        self.detail = [
            f"기분: {mood}  (디스크 {round(dpct)}%)",
            f"💾 디스크 {dpct:.0f}%  ·  {mc.human_gb(disk.used)} / {mc.human_gb(disk.total)}  (여유 {mc.human_gb(disk.free)})",
            f"🧠 RAM {vm.percent:.0f}%  ·  {mc.human_gb(vm.used)} / {mc.human_gb(vm.total)}",
        ]
        if sw.total > 0:
            self.detail.append(
                f"스왑 {sw.percent:.0f}%  ·  {mc.human_gb(sw.used)} / {mc.human_gb(sw.total)}")
        self.detail.append("─ 메모리 먹는 앱 ─")
        try:
            for name, rss in mc.top_memory_apps():
                self.detail.append(f"{rss / 1024 ** 2:,.0f} MB   {name}")
        except Exception:
            pass

    def setTheme_(self, sender):
        self.cfg["theme"] = sender.representedObject()
        save_config(self.cfg)
        self.refresh_(None)

    def setSize_(self, sender):
        self.cfg["size"] = sender.representedObject()
        save_config(self.cfg)
        self.applyLayout()

    def setPersonality_(self, sender):
        self.cfg["personality"] = sender.representedObject()
        save_config(self.cfg)
        self._notify("뚱냥이 성격 변경", f"이제 {self.cfg['personality']} 말투로 진단할게요.")

    def setCustomPersonality_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("뚱냥이 성격을 직접 알려 주세요")
        alert.setInformativeText_("예: 다정하지만 핵심만 말하고, 말끝에 냥을 붙여줘")
        alert.addButtonWithTitle_("저장")
        alert.addButtonWithTitle_("취소")
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 380, 28))
        field.setStringValue_(self.cfg.get("custom_personality", ""))
        alert.setAccessoryView_(field)
        NSApp.activateIgnoringOtherApps_(True)
        if alert.runModal() != NSAlertFirstButtonReturn:
            return

        custom = normalize_custom_personality(field.stringValue())
        if not custom:
            self._notify("성격을 저장하지 않았어요", "한 문장 이상 입력해 주세요.")
            return
        self.cfg["personality"] = CUSTOM_PERSONALITY
        self.cfg["custom_personality"] = custom
        save_config(self.cfg)
        self._notify("커스텀 성격 저장", custom)

    def diagnose_(self, sender):
        if self._diagnosis_running:
            self._notify("🧠 이미 진단 중이에요", "뚱냥이가 숫자를 살펴보고 있습니다.")
            return
        personality, custom = config_personality(self.cfg)
        self._diagnosis_running = True
        self._notify("🧠 왜 느린지 보는 중", "고양이가 디스크와 메모리를 살펴보고 있어요.")
        self._diagnosis_thread = threading.Thread(
            target=_diagnosis_worker,
            args=(personality, custom, self._finish_diagnosis),
            name="memory-cat-diagnosis",
            daemon=True,
        )
        self._diagnosis_thread.start()

    @objc.python_method
    def _finish_diagnosis(self, result):
        self._diagnosis_running = False
        body = diagnosis_notification_text(result)
        if not self._notify("🧠 뚱냥이 진단", body):
            self._show_information_alert("🧠 뚱냥이 진단", body)

        recommendations = result.get("cleanup_recommendations", [])
        if recommendations and self._confirm_cleanup_review(recommendations):
            summary = process_cleanup_recommendations(
                recommendations, self._confirm_cleanup_item
            )
            self._show_cleanup_summary(summary)

    @objc.python_method
    def _notify(self, title, body):
        try:
            notification = NSUserNotification.alloc().init()
            notification.setTitle_(title)
            notification.setInformativeText_(body)
            NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(
                notification
            )
            return True
        except Exception:
            return False

    @objc.python_method
    def _show_information_alert(self, title, body):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(body)
        alert.addButtonWithTitle_("확인")
        NSApp.activateIgnoringOtherApps_(True)
        alert.runModal()

    @objc.python_method
    def _confirm_cleanup_review(self, recommendations):
        count = sum(len(item.get("items", [])) for item in recommendations)
        if count == 0:
            return False
        alert = NSAlert.alloc().init()
        alert.setMessageText_("안전한 정리 후보를 볼까요?")
        alert.setInformativeText_(
            f"화이트리스트 항목 {count}개를 하나씩 확인합니다. "
            "동의한 항목만 macOS 휴지통으로 이동하며 영구 삭제하지 않습니다."
        )
        alert.addButtonWithTitle_("항목별 검토")
        alert.addButtonWithTitle_("나중에")
        NSApp.activateIgnoringOtherApps_(True)
        return alert.runModal() == NSAlertFirstButtonReturn

    @objc.python_method
    def _confirm_cleanup_item(self, recommendation, item):
        category = recommendation.get("category")
        path = item.get("path", "")
        size = item.get("size", "크기 알 수 없음")
        reason = recommendation.get("reason", "")
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"{recommendation.get('label', '정리 후보')} · {size}")
        if category == "trash":
            action_note = "이미 휴지통 안에 있어 확인만 하며, 영구 삭제하지 않습니다."
            primary = "확인"
        else:
            action_note = "이 항목을 macOS 휴지통으로 이동할까요?"
            primary = "휴지통으로 이동"
        alert.setInformativeText_(f"{path}\n\n{reason}\n{action_note}")
        alert.addButtonWithTitle_(primary)
        alert.addButtonWithTitle_("건너뛰기")
        NSApp.activateIgnoringOtherApps_(True)
        return alert.runModal() == NSAlertFirstButtonReturn

    @objc.python_method
    def _show_cleanup_summary(self, summary):
        parts = []
        if summary["moved"]:
            parts.append(f"{summary['moved']}개를 휴지통으로 이동")
        if summary["already_in_trash"]:
            parts.append(f"휴지통 안 {summary['already_in_trash']}개 확인")
        if summary["skipped"]:
            parts.append(f"{summary['skipped']}개 건너뜀")
        if summary["failed"]:
            parts.append(f"{summary['failed']}개 이동 실패")
        body = " · ".join(parts) or "변경한 항목이 없습니다."
        if summary["moved"]:
            body += " 공간은 휴지통을 직접 비운 뒤 확보됩니다."
        self._notify("🧹 정리 결과", body)

    def popUpMenu_(self, event):
        menu = NSMenu.alloc().init()
        for line in self.detail:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(line, None, "")
            it.setEnabled_(False)
            menu.addItem_(it)
        menu.addItem_(NSMenuItem.separatorItem())

        diagnose_title = "🧠 진단 중…" if self._diagnosis_running else "🧠 왜 느려?"
        di = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            diagnose_title, b"diagnose:", ""
        )
        di.setTarget_(self)
        di.setEnabled_(not self._diagnosis_running)
        menu.addItem_(di)
        menu.addItem_(NSMenuItem.separatorItem())

        theme_menu = NSMenu.alloc().init()
        for key in discover_themes():
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(theme_label(key), b"setTheme:", "")
            it.setTarget_(self)
            it.setRepresentedObject_(key)
            if key == self.cfg["theme"]:
                it.setState_(1)
            theme_menu.addItem_(it)
        ti = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("테마", None, "")
        ti.setSubmenu_(theme_menu)
        menu.addItem_(ti)

        size_menu = NSMenu.alloc().init()
        for label in SIZES:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, b"setSize:", "")
            it.setTarget_(self)
            it.setRepresentedObject_(label)
            if label == self.cfg["size"]:
                it.setState_(1)
            size_menu.addItem_(it)
        si = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("크기", None, "")
        si.setSubmenu_(size_menu)
        menu.addItem_(si)

        personality_menu = NSMenu.alloc().init()
        for name in preset_names():
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                name, b"setPersonality:", ""
            )
            it.setTarget_(self)
            it.setRepresentedObject_(name)
            if name == self.cfg["personality"]:
                it.setState_(1)
            personality_menu.addItem_(it)
        custom_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "직접 입력…", b"setCustomPersonality:", ""
        )
        custom_item.setTarget_(self)
        if self.cfg["personality"] == CUSTOM_PERSONALITY:
            custom_item.setState_(1)
        personality_menu.addItem_(custom_item)
        pi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("성격", None, "")
        pi.setSubmenu_(personality_menu)
        menu.addItem_(pi)

        menu.addItem_(NSMenuItem.separatorItem())
        r = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("새로고침", b"refresh:", "")
        r.setTarget_(self)
        menu.addItem_(r)
        q = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("종료", b"quit:", "")
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
