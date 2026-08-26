#!/usr/bin/env python3
"""메모리 뚱냥이 — macOS 바탕화면 둥둥 버전.

항상 위에 떠 있는 작은 고양이. 디스크(하드 용량)가 차오를수록
애기냥 -> 돼지냥으로 빵빵해지며 살짝 통통 튄다. 라벨에 디스크/램 표시.
우클릭: AI 진단 + 성격 + 테마 + 크기 + 새로고침/종료.

설정과 직접 만든 테마는 ``~/Library/Application Support/Memory Cat/`` 에,
기본 테마 4종은 앱 번들 안에 있다(:mod:`apppaths` 참고). 두 곳을 모두 훑어서
테마 목록을 만든다. 새 테마 추가:
  python import_theme.py 내이미지.png 테마이름   (가로 N단계 시트)
"""
import errno
import fcntl
import json
import os
import threading
import time

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
    NSAlertThirdButtonReturn,
    NSOpenPanel, NSModalResponseOK,
)
from Foundation import (
    NSObject, NSMakeRect, NSMakePoint, NSMakeSize, NSAttributedString,
    NSOperationQueue, NSUserNotification, NSUserNotificationCenter,
    NSDistributedNotificationCenter, NSRunLoop, NSDate, NSDefaultRunLoopMode,
)

import apppaths
import metrics as mc
from brain import _load_api_key, diagnose as run_diagnosis, safe_trash
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
# 기본 테마 4종은 앱(번들) 안에, 사용자가 만든 테마는 사용자 폴더에 산다.
# 자세한 규칙은 apppaths 모듈 참고.
FRAMES_BASE = str(apppaths.bundled_frames_dir())
USER_FRAMES_BASE = str(apppaths.user_frames_dir())
#: 테마를 못 읽을 때 쓰는 기본 아이콘. 번들 안이라 항상 있다.
FALLBACK_ALERT_ICON_PATH = os.path.join(FRAMES_BASE, "cute", "cat_00.png")
CONFIG = str(apppaths.config_file())
REFRESH_SEC = 4.0
DISK_FULL_NOTIFICATION_ID = "memory-cat-disk-full"
CLEANUP_SUMMARY_NOTIFICATION_ID = "memory-cat-cleanup-summary"
# 알림이 배달 목록에 반영되는 데 걸리는 시간을 넉넉히 잡은 값.
NOTIFICATION_VERIFY_SEC = 1.0
# 아이폰 기본값인 heic 포함. 이미지 API 는 heic 를 받지 않으므로
# vision_theme.api_ready_photo 가 업로드 직전에 변환한다.
PET_PHOTO_TYPES = ["png", "jpg", "jpeg", "webp", "heic", "heif"]
DISK_FULL_PROMPT_PERCENT = 92.0
#: 뚱냥이 한 마리만 뜨게 하는 잠금 파일. 사용자 데이터 폴더 안에 산다.
INSTANCE_LOCK_NAME = "memory-cat.lock"
#: 두 번째 실행이 "앞으로 나와" 하고 부르는 신호와, 살아 있다는 응답.
REVEAL_NOTIFICATION = "com.memorycat.desktop.reveal"
REVEAL_ACK_NOTIFICATION = "com.memorycat.desktop.reveal-ack"
#: 응답을 이만큼 기다린다. 넘기면 먼저 뜬 뚱냥이가 멈춰 있다고 본다.
REVEAL_ACK_TIMEOUT_SEC = 2.0
NSStatusWindowLevel = 25
CATBOTTOM = 46.0
# 항목 검토 중 "정리 중단"을 고른 신호. bool 이 아니라서 기존 콜백과 섞이지 않는다.
CLEANUP_ABORT = "abort"

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


def frame_index_for(theme, disk_percent):
    """디스크 사용률을 그 테마의 프레임 번호로 옮긴다.

    바탕화면 고양이와 알럿 아이콘이 같은 계산을 써야 한쪽만 다른 몸집으로
    나오는 일이 없다.
    """
    n = frame_count(theme)
    return int(round(disk_percent / 100 * (n - 1)))


def alert_icon_path():
    """알럿에 띄울 아이콘 경로. 지금 테마의, 지금 몸집으로 보여 준다.

    반려동물 사진으로 자기 테마를 만든 사람에게 기본 고양이를 보여 주면
    화면에 떠 있는 동물과 말을 거는 동물이 달라진다. 그리고 "배불러요" 라고
    말하는 창에 홀쭉한 그림이 붙어 있으면 말과 그림이 따로 논다. 디스크가
    찬 만큼 부푼 프레임을 쓴다.

    테마나 사용률을 읽지 못하면 번들 안 기본 고양이로 돌아간다. 아이콘을
    못 구했다고 알럿까지 안 뜨면 안 된다.
    """
    try:
        theme = load_config()["theme"]
    except Exception:
        return FALLBACK_ALERT_ICON_PATH
    try:
        index = frame_index_for(theme, mc.disk_usage().percent)
    except Exception:
        index = 0  # 측정에 실패해도 그 테마의 얼굴은 보여 준다.
    try:
        candidate = frame_path(theme, index)
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    return FALLBACK_ALERT_ICON_PATH


def new_cat_alert():
    """Create an NSAlert showing the theme the user is actually running."""
    alert = NSAlert.alloc().init()
    try:
        icon = NSImage.alloc().initWithContentsOfFile_(alert_icon_path())
        if icon is not None:
            alert.setIcon_(icon)
    except Exception:
        pass
    return alert


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
        # 첫 실행이면 ~/Library/Application Support/Memory Cat/ 이 아직 없다.
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False)
        return True
    except Exception:
        return False


def instance_lock_path():
    """잠금 파일 경로. 설정과 같은 사용자 데이터 폴더 안."""
    return str(apppaths.user_data_dir() / INSTANCE_LOCK_NAME)


#: 잠금은 열린 파일을 붙잡고 있어야 유지된다. 파이썬이 거둬가지 않게 여기에 둔다.
_instance_lock_handle = None


def acquire_instance_lock(path=None):
    """뚱냥이가 이 컴퓨터에 한 마리만 뜨도록 잠금을 건다.

    ``(handle, busy)`` 를 돌려준다. ``handle`` 이 있으면 내가 유일한
    뚱냥이다. ``busy`` 가 True 면 이미 다른 뚱냥이가 살아 있다.
    둘 다 비어 있으면 잠금 자체를 걸 수 없는 환경이라는 뜻이고, 이때는
    **막지 않는다**. 두 마리가 뜨는 것보다 한 마리도 안 뜨는 쪽이 나쁘다.

    ``flock`` 은 파일이 아니라 **열린 fd** 에 걸리는 잠금이라, 프로세스가
    어떻게 죽든(정상 종료·크래시·강제 종료·``kill -9``) 커널이 알아서
    풀어 준다. PID 파일처럼 죽은 잠금이 남아 앱을 영영 못 켜게 만드는 일이
    없다. ``launchctl kickstart -k`` 나 ``KeepAlive`` 재시작도 앞 프로세스가
    끝난 뒤에 새 프로세스를 띄우므로 그대로 통과한다.
    """
    if path is None:
        apppaths.ensure_user_data_dir()
        path = instance_lock_path()
    try:
        handle = open(path, "a+")
    except OSError:
        return None, False
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return None, True
        # 잠금을 지원하지 않는 파일 시스템 등. 확신이 없으면 켜 준다.
        return None, False
    try:
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
    except OSError:
        pass  # PID 는 로그 볼 때 참고용일 뿐, 잠금 자체와는 상관없다.
    return handle, False


def hold_instance_lock(handle):
    """잠금 파일을 프로세스가 끝날 때까지 붙잡아 둔다."""
    global _instance_lock_handle
    _instance_lock_handle = handle
    return handle


class RevealAckWaiter(NSObject):
    """두 번째 실행이 "나 살아 있어" 응답을 기다리는 동안 쓰는 수신기."""

    def init(self):
        self = objc.super(RevealAckWaiter, self).init()
        if self is None:
            return None
        self._acknowledged = False
        return self

    def revealAcknowledged_(self, notification):
        self._acknowledged = True

    @objc.python_method
    def acknowledged(self):
        return self._acknowledged


def request_reveal(timeout=REVEAL_ACK_TIMEOUT_SEC):
    """이미 떠 있는 뚱냥이에게 앞으로 나오라고 부르고 응답을 기다린다.

    응답이 오면 True. 시간 안에 아무 말이 없으면 False — 먼저 뜬 쪽이
    멈춰 있거나 막 끝나는 중이라는 뜻이다.
    """
    center = NSDistributedNotificationCenter.defaultCenter()
    waiter = RevealAckWaiter.alloc().init()
    try:
        center.addObserver_selector_name_object_(
            waiter, b"revealAcknowledged:", REVEAL_ACK_NOTIFICATION, None)
        center.postNotificationName_object_(REVEAL_NOTIFICATION, None)
    except Exception:
        return False
    try:
        loop = NSRunLoop.currentRunLoop()
        deadline = time.monotonic() + timeout
        while not waiter.acknowledged() and time.monotonic() < deadline:
            loop.runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.05),
            )
        return waiter.acknowledged()
    finally:
        try:
            center.removeObserver_(waiter)
        except Exception:
            pass


def show_already_running_alert(language=None):
    """부른 뚱냥이가 대답을 안 할 때만 뜨는 안내창."""
    if language is None:
        language = resolve_language(load_config()["language"])
    alert = new_cat_alert()
    alert.setMessageText_(tr(language, "already_running_title"))
    alert.setInformativeText_(tr(language, "already_running_body"))
    alert.addButtonWithTitle_(tr(language, "confirm"))
    NSApp.activateIgnoringOtherApps_(True)
    alert.runModal()


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
    help_text = None
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
        if result.get("fallback_reason") == "missing_api_key":
            # 키가 없어서 떨어진 경우에만 넣는다. 다른 실패 사유는 사용자가
            # 할 수 있는 게 없어서 안내가 오히려 방해가 된다.
            help_text = tr(
                language,
                "missing_api_key_help",
                path=apppaths.user_data_dir() / ".env",
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
            help_text,
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


def cleanup_queue(recommendations):
    """검토 순서대로 (추천, 항목) 쌍을 펼친다."""
    return [
        (recommendation, item)
        for recommendation in recommendations
        for item in recommendation.get("items", [])
    ]


def process_cleanup_recommendations(recommendations, confirm_item, trash_func=None):
    """각 항목을 확인받은 뒤에만 safe_trash를 호출한다.

    ``confirm_item`` 이 ``CLEANUP_ABORT`` 를 돌려주면 남은 항목은 묻지 않고
    전부 건너뛴 것으로 세고 즉시 끝낸다. 그 밖의 값은 예전처럼 참/거짓으로만
    본다.
    """
    trash_func = safe_trash if trash_func is None else trash_func
    summary = {"moved": 0, "already_in_trash": 0, "skipped": 0, "failed": 0}
    queue = cleanup_queue(recommendations)
    for index, (recommendation, item) in enumerate(queue):
        path = item.get("path")
        decision = confirm_item(recommendation, item) if path else False
        if decision == CLEANUP_ABORT:
            summary["skipped"] += len(queue) - index
            return summary
        if not decision:
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


def theme_roots():
    """테마를 찾을 폴더 목록. 번들 기본 테마 + 사용자가 만든 테마."""
    return [FRAMES_BASE, USER_FRAMES_BASE]


def theme_dir(theme):
    """테마 이름을 실제 폴더 경로로. 같은 이름이면 사용자 테마가 이긴다."""
    name = str(theme)
    for root in reversed(theme_roots()):
        candidate = os.path.join(root, name)
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(USER_FRAMES_BASE, name)


def discover_themes():
    """테마 폴더 자동 인식. 알려진 것 먼저, 나머지 알파벳순.

    번들 안 기본 테마와 사용자 폴더의 커스텀 테마를 함께 본다. 두 곳에 같은
    이름이 있으면 한 번만 나온다(그리고 :func:`theme_dir` 이 사용자 쪽을 고른다).
    """
    found = []
    for root in theme_roots():
        if not os.path.isdir(root):
            continue
        for n in sorted(os.listdir(root)):
            d = os.path.join(root, n)
            if n in found or n.startswith("."):
                continue
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "cat_00.png")):
                found.append(n)
    return ([t for t in THEME_ORDER if t in found]
            + [t for t in found if t not in THEME_ORDER])


def next_pet_theme_name(frames_base=None):
    """Return mypet, mypet2, ... without overwriting an existing path.

    ``frames_base`` 를 주지 않으면 번들과 사용자 폴더를 모두 확인한다.
    한쪽에만 있는 이름을 재사용하면 기본 테마를 가려 버리기 때문이다.
    """
    roots = theme_roots() if frames_base is None else [os.fspath(frames_base)]
    candidate = "mypet"
    suffix = 2
    while any(os.path.exists(os.path.join(root, candidate)) for root in roots):
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
    d = theme_dir(theme)
    try:
        return max(1, len([f for f in os.listdir(d)
                           if f.startswith("cat_") and f.endswith(".png")]))
    except Exception:
        return 1


def frame_path(theme, idx):
    n = frame_count(theme)
    idx = max(0, min(n - 1, idx))
    return os.path.join(theme_dir(theme), f"cat_{idx:02d}.png")


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
        self._cleanup_summary_message = None
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
        self.listenForRevealRequests()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            REFRESH_SEC, self, b"refresh:", None, True)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.06, self, b"animate:", None, True)

    def listenForRevealRequests(self):
        """앱을 두 번째로 연 사람이 보내는 "앞으로 나와" 신호를 받는다."""
        center = NSDistributedNotificationCenter.defaultCenter()
        try:
            center.addObserver_selector_name_object_(
                self, b"revealRequested:", REVEAL_NOTIFICATION, None)
        except Exception:
            return
        self._distributed_center = center

    def revealRequested_(self, notification):
        """고양이를 사용자 눈앞으로 데려오고, 살아 있다고 답장한다.

        답장이 있어야 두 번째 프로세스가 "이미 잘 돌아가고 있구나" 하고
        조용히 물러난다. 고양이를 못 옮기더라도 답장은 반드시 보낸다.
        """
        try:
            self.revealCat()
        except Exception:
            pass  # 콜백에서 예외가 새면 run loop 가 끝난다. 답장이 더 급하다.
        center = getattr(self, "_distributed_center", None)
        if center is None:
            center = NSDistributedNotificationCenter.defaultCenter()
        try:
            center.postNotificationName_object_(REVEAL_ACK_NOTIFICATION, None)
        except Exception:
            pass

    def revealCat(self):
        """창을 화면 안쪽으로 되돌리고 맨 앞에 세운다.

        두 번 연 사람은 고양이가 보고 싶은 것이다. 창이 화면 밖으로
        끌려 나갔거나 다른 창에 가려 있어도 다시 보이게 만든다.
        """
        window = getattr(self, "window", None)
        if window is None:
            return
        try:
            frame = window.frame()
            visible = NSScreen.mainScreen().visibleFrame()
            x = max(
                visible.origin.x,
                min(
                    frame.origin.x,
                    visible.origin.x + visible.size.width - frame.size.width,
                ),
            )
            y = max(
                visible.origin.y,
                min(
                    frame.origin.y,
                    visible.origin.y + visible.size.height - frame.size.height,
                ),
            )
            if (x, y) != (frame.origin.x, frame.origin.y):
                window.setFrameOrigin_(NSMakePoint(x, y))
        except Exception:
            pass  # 화면 정보를 못 읽어도 맨 앞으로 올리는 건 해야 한다.
        window.orderFrontRegardless()

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
        # NSTimer 콜백에서 예외가 새어 나가면 run loop 가 그대로 끝나 앱이
        # 종료된다. LaunchAgent 에 KeepAlive 가 없어 재로그인 전까지 되살아나지
        # 않으므로, 한 틱이 실패해도 삼키고 다음 틱을 기다린다.
        try:
            self._refresh_once()
        except Exception:
            pass

    @objc.python_method
    def _refresh_once(self):
        disk = mc.disk_usage()
        score, vm, sw = mc.safe_pressure_score()
        dpct = disk.percent
        self.score = dpct
        self._maybe_prompt_disk_full(dpct)
        theme = self.cfg["theme"]
        idx = frame_index_for(theme, dpct)
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

        # 사진을 다 고른 뒤에 "키가 없다"고 하면 헛수고를 시키는 것이다.
        # 누르자마자 알려 준다.
        if not _load_api_key():
            self._show_missing_api_key_alert()
            return

        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setAllowedFileTypes_(PET_PHOTO_TYPES)
        NSApp.activateIgnoringOtherApps_(True)
        if panel.runModal() != NSModalResponseOK:
            return

        selected_url = panel.URL()
        photo_path = selected_url.path() if selected_url is not None else None
        if not photo_path:
            return

        alert = new_cat_alert()
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
        alert = new_cat_alert()
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
    def _notification_center_ref(self):
        """알림센터 핸들. 처음 쓸 때 한 번만 잡아 둔다."""
        center = getattr(self, "_notification_center", None)
        if center is None:
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
            self._notification_center = center
        return center

    @objc.python_method
    def _deliver_verified(self, notification, identifier, verify_selector):
        """알림을 배달하고, 정말 떴는지 나중에 확인하도록 예약한다.

        ``deliverNotification_`` 은 알림이 억제되거나 차단돼도 예외를 내지
        않는다. 그래서 "보냈다"와 "보였다"가 다르다. 식별자를 붙여 두고
        ``NOTIFICATION_VERIFY_SEC`` 뒤에 배달 목록을 훑는다(배달된 알림은
        50ms 쯤 뒤 목록에 나타난다).

        배달 자체가 실패하면 ``False`` 를 돌려준다. 그 자리에서 대체 창을
        띄우는 건 호출부 몫이다. 예약이 걸렸으면 ``True``.
        """
        notification.setIdentifier_(identifier)
        center = self._notification_center_ref()
        try:
            center.setDelegate_(self)
        except Exception:
            pass
        try:
            center.deliverNotification_(notification)
        except Exception:
            return False
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            NOTIFICATION_VERIFY_SEC, self, verify_selector, None, False)
        return True

    @objc.python_method
    def _notification_was_delivered(self, identifier):
        """그 식별자를 가진 알림이 실제로 배달 목록에 있는지."""
        center = getattr(self, "_notification_center", None)
        try:
            delivered = list(center.deliveredNotifications() or []) if center else []
            return any(
                str(item.identifier() or "") == identifier for item in delivered
            )
        except Exception:
            return False

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
        # 디스크가 꽉 찼다는 경고는 조용히 사라지면 안 된다.
        if not self._deliver_verified(
            notification, DISK_FULL_NOTIFICATION_ID, b"verifyDiskFullPrompt:"
        ):
            self._show_disk_full_alert()

    def verifyDiskFullPrompt_(self, timer):
        if not self._notification_was_delivered(DISK_FULL_NOTIFICATION_ID):
            self._show_disk_full_alert()

    @objc.python_method
    def _show_disk_full_alert(self):
        """알림이 뜨지 않는 환경을 위한 대체 경로. 진단으로 바로 이어준다."""
        alert = new_cat_alert()
        alert.setMessageText_(tr(self.language, "disk_full_prompt_title"))
        alert.setInformativeText_(tr(self.language, "disk_full_prompt_body"))
        alert.addButtonWithTitle_(tr(self.language, "disk_full_prompt_action"))
        alert.addButtonWithTitle_(tr(self.language, "close"))
        NSApp.activateIgnoringOtherApps_(True)
        if alert.runModal() == NSAlertFirstButtonReturn:
            self.diagnose_(None)

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
        alert = new_cat_alert()
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
    def _show_missing_api_key_alert(self):
        """키가 없어 AI 기능을 못 쓸 때, 어디에 무엇을 넣으면 되는지 보여 준다."""
        self._show_information_alert(
            tr(self.language, "missing_api_key_title"),
            tr(
                self.language,
                "missing_api_key_help",
                path=apppaths.user_data_dir() / ".env",
            ),
        )

    @objc.python_method
    def _show_information_alert(self, title, body):
        alert = new_cat_alert()
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
        alert = new_cat_alert()
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
        alert = new_cat_alert()
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
        # 항목이 최대 80개라 중간에 빠져나갈 길이 없으면 갇힌다. Esc로도 멈춘다.
        stop_button = alert.addButtonWithTitle_(tr(self.language, "stop_cleanup"))
        stop_button.setKeyEquivalent_("\033")
        NSApp.activateIgnoringOtherApps_(True)
        response = alert.runModal()
        if response == NSAlertThirdButtonReturn:
            return CLEANUP_ABORT
        return response == NSAlertFirstButtonReturn

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
        title = tr(self.language, "cleanup_result_title")
        # 사용자가 방금 승인한 파일 작업의 결과다. 조용히 사라지면 뭘 지웠는지
        # 알 길이 없으므로 디스크 경고와 같은 방식으로 배달을 확인한다.
        self._cleanup_summary_message = (title, body)
        notification = NSUserNotification.alloc().init()
        notification.setTitle_(title)
        notification.setInformativeText_(body)
        if not self._deliver_verified(
            notification, CLEANUP_SUMMARY_NOTIFICATION_ID, b"verifyCleanupSummary:"
        ):
            self._show_cleanup_summary_alert()

    def verifyCleanupSummary_(self, timer):
        if not self._notification_was_delivered(CLEANUP_SUMMARY_NOTIFICATION_ID):
            self._show_cleanup_summary_alert()

    @objc.python_method
    def _show_cleanup_summary_alert(self):
        """알림이 뜨지 않는 환경을 위한 대체 경로. 정리 결과를 창으로 보여준다."""
        message = getattr(self, "_cleanup_summary_message", None)
        if message is None:
            return
        title, body = message
        self._cleanup_summary_message = None
        self._show_information_alert(title, body)

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

    lock, busy = acquire_instance_lock()
    if busy:
        # 이미 한 마리 떠 있다. 두 마리가 겹쳐 뛰면서 같은 config.json 을
        # 서로 덮어쓰는 걸 막는다. 대신 있던 고양이를 앞으로 불러낸다.
        if request_reveal():
            return
        # 대답이 없다. 그 사이 사라졌을 수도 있으니 잠금을 한 번 더 노려본다.
        # (kickstart 재시작이 겹치는 순간 등) 여전히 잡혀 있으면 멈춰 있는
        # 것이니, 아무 일도 안 일어난 것처럼 보이지 않게 알려 준다.
        lock, busy = acquire_instance_lock()
        if busy:
            show_already_running_alert()
            return
    hold_instance_lock(lock)

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
