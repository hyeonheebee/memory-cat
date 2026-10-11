#!/usr/bin/env python3
"""메모리 뚱냥이 — 윈도우 버전 (PySide6).

바탕화면에 떠 있는 작은 고양이. 시스템 드라이브(하드 용량)가 차오를수록
애기냥 -> 돼지냥으로 변하며 살짝 통통 튄다. 라벨에 디스크/램 표시.
- 드래그로 이동 / 우클릭: 상세 + 테마 + 크기 + 새로고침/종료
- 설정은 %APPDATA%\\Memory Cat\\config.json 에 저장돼 유지

실행:  pythonw windows_cat.pyw   (또는 더블클릭)
필요:  pip install pyside6 psutil
"""
import json
import math
import os
import sys
import traceback
from types import SimpleNamespace

# 이 파일은 windows/ 안에 있는데 i18n·metrics 는 저장소 루트에 있다. 파이썬은
# 스크립트를 직접 실행할 때 sys.path[0] 에 스크립트 폴더만 넣으므로, 루트를
# 직접 얹어 준다 — 안 그러면 어느 디렉터리에서 실행하든 ModuleNotFoundError 다.
# exe(frozen) 는 build_exe.bat 의 `--paths ".."` 로 이미 담겨 와서 건드리지 않는다.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil
from PySide6 import QtCore, QtGui, QtWidgets

from i18n import (
    LANGUAGE_AUTO,
    LANGUAGE_OVERRIDES,
    clean_pet_name,
    pet_name,
    resolve_language,
    tr,
)
# metrics 는 저장소 루트의 플랫폼 공통 모듈이다(GUI 의존 없음). i18n 과 같은
# 방식으로 닿는다 — build_exe.bat 의 `--paths ".."` 와 `--hidden-import`.
# disk_usage·human_gb 는 이 파일의 같은 이름 함수가 그대로 위임할 것이라
# 이름이 겹치지 않게 _metrics_* 로 따로 받는다.
from metrics import (
    DEFAULT_SIZE_SOURCE,
    SIZE_SOURCES,
    disk_usage as _metrics_disk_usage,
    human_gb as _metrics_human_gb,
    ram_used_for_display,
)
# apppaths 도 루트의 가벼운 모듈이다(os·sys·pathlib 만). 사용자가 만든 테마가
# 사는 곳(%APPDATA%\Memory Cat\frames)을 여기서 받는다 — exe 옆이나 번들
# frames 에는 쓸 수 없어서 새 테마는 늘 그쪽에 생긴다.
import apppaths
# win_app 은 windows/ 안에 있는 Qt 없는 모듈이다(stdlib + apppaths 만). 설정
# 파일을 옛 위치(exe 옆)에서 새 위치(apppaths.config_file())로 옮기는 판단이
# 여기 있다. 무거운 의존성이 없어서 win_ai_ui 처럼 try/except 로 감싸지
# 않는다 — 이게 없으면 설정을 옮길 방법이 아예 없다.
import win_app

# 진단·테마 만들기는 선택 기능이다. openai·Pillow 같은 의존성이 없는 소스 실행
# 환경(예: 업데이트 후 pip 를 다시 안 돌린 경우)에서도 고양이는 떠야 한다.
# .pyw 는 import 가 실패하면 창 하나 없이 조용히 끝나기 때문이다.
# exe 는 build_exe.bat 의 --hidden-import 로 항상 담긴다. PyInstaller 가
# pydantic_core·jiter·numpy 같은 간접 의존성의 DLL 을 놓치는 경우가
# 있어서, 실패하면 흔적이라도 남긴다 — 안 그러면 메뉴가 기록 없이
# 조용히 사라져서 사용자도 우리도 이유를 알 방법이 없다.
# win_ai 도 같이 묶어서 import 한다 — 메뉴 핸들러(_start_diagnosis·
# _start_theme)가 실패를 win_ai.log_ai_failure 로 남기려면 이 모듈이
# 필요한데, win_ai_ui 와 의존성(PIL·openai 경유)이 겹쳐서 한쪽만 실패하는
# 경우는 사실상 없다 — 따로 try/except 를 두 겹 만들지 않고 하나로 묶는다.
try:
    import win_ai
    import win_ai_ui
except ImportError:
    win_ai = None
    win_ai_ui = None
    try:
        log_path = apppaths.log_dir() / "ai-features-unavailable.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        # 로그 기록은 부가 정보일 뿐이다 — 못 써도 고양이는 떠야 한다.
        pass

# 빌드(.exe)면 frames 는 번들 안에 둔다(읽기 전용). config 는 apppaths 가
# 정하는 사용자 데이터 폴더(%APPDATA%\Memory Cat)에 둔다 — exe 옆에 두면
# Program Files 처럼 쓰기 권한이 없는 곳에 깔렸을 때 저장이 통째로 실패하고,
# exe 를 다른 드라이브로 옮기면 테마 선택이 풀렸다(실기 확인됨).
if getattr(sys, "frozen", False):
    BASE = sys._MEIPASS
    APPDIR = os.path.dirname(sys.executable)
else:
    BASE = APPDIR = os.path.dirname(os.path.abspath(__file__))

FRAMES_DIR = os.path.join(BASE, "frames")
CONFIG = str(apppaths.config_file())
# 옛 버전이 exe 옆에 저장하던 자리. main() 이 한 번 새 자리로 옮겨 준다.
LEGACY_CONFIG = os.path.join(APPDIR, "config.json")

REFRESH_MS = 4000
CATBOTTOM = 46
THEME_STRING_KEYS = {
    "cute": "theme_cute",
    "simple": "theme_simple",
    "madness": "theme_madness",
    "derpy": "theme_derpy",
}
THEME_ORDER = ["cute", "simple", "madness", "derpy"]
SIZES = {"작게": 78, "보통": 104, "크게": 138, "왕": 176}
SIZE_STRING_KEYS = {
    "작게": "size_small",
    "보통": "size_medium",
    "크게": "size_large",
    "왕": "size_king",
}
#: ``size_source`` = 무엇을 보고 몸집을 정할지(맥과 같은 선택지·기본값).
#: v0.4.0 전 윈도우는 디스크만 봤다 — 설정 파일에 이 값이 없는 옛 사용자도
#: 맥처럼 메모리로 시작한다.
DEFAULT = {"theme": "cute", "size": "보통", "language": LANGUAGE_AUTO,
           "size_source": DEFAULT_SIZE_SOURCE, "pet_name": ""}


def system_languages():
    """윈도우의 표시 언어 목록. macOS 의 NSLocale 자리에 QLocale 을 쓴다."""
    try:
        return list(QtCore.QLocale.system().uiLanguages())
    except Exception:
        return []


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as handle:
            c = json.load(handle)
        language = c.get("language", LANGUAGE_AUTO)
        return {"theme": c.get("theme", DEFAULT["theme"]),
                "size": c.get("size", DEFAULT["size"]),
                "language": language if language in LANGUAGE_OVERRIDES
                else LANGUAGE_AUTO,
                "size_source": win_app.normalize_size_source(
                    c.get("size_source")),
                "pet_name": clean_pet_name(c.get("pet_name"))}
    except Exception:
        return dict(DEFAULT)


def save_config(cfg):
    try:
        # CONFIG 는 이제 %APPDATA%\Memory Cat 아래다. 처음 실행이면 그 폴더
        # 자체가 없을 수 있다(apppaths.user_data_dir() 은 만들지 않는다).
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False)
    except Exception:
        pass


def theme_roots():
    """테마를 찾을 폴더들: 번들 frames, 그리고 사용자가 만든 테마가 사는 곳.

    번들만 보면 "내 반려동물로 테마 만들기" 로 만든 테마가 메뉴에 안 뜨고,
    재시작하면 __init__ 이 설정의 테마를 themes[0] 으로 되돌려 버린다.
    """
    return (FRAMES_DIR, str(apppaths.user_frames_dir()))


def theme_dir(theme):
    """테마 이름 -> 폴더. 사용자 쪽에 그 폴더가 있으면 사용자 쪽이 이긴다.

    맥의 apppaths.theme_dir 와 같은 규칙이다. 어느 쪽에도 없으면 번들 쪽을
    돌려준다 — 호출부가 listdir 실패와 없는 그림을 이미 견딘다.
    """
    user = os.path.join(str(apppaths.user_frames_dir()), theme)
    if os.path.isdir(user):
        return user
    return os.path.join(FRAMES_DIR, theme)


def discover_themes():
    found = set()
    for root in theme_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            # vision_theme 은 ".building" 같은 점 폴더에서 만든 뒤 옮긴다.
            # 만드는 중인 테마가 메뉴에 뜨면 안 된다.
            if n.startswith("."):
                continue
            d = os.path.join(root, n)
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "cat_00.png")):
                found.add(n)
    found = sorted(found)
    return ([t for t in THEME_ORDER if t in found]
            + [t for t in found if t not in THEME_ORDER])


def theme_label(key, language):
    string_key = THEME_STRING_KEYS.get(key)
    return tr(language, string_key) if string_key else key


def size_label(key, language):
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


def disk_usage():
    """사용자가 보는 하드 용량은 ``metrics.disk_usage()`` 가 정한다
    (시스템 드라이브 우선, 데모 override 도 거기서 처리).

    여기서는 그 결과로 위임만 한다 — 정보창·프레임 선택·진단(``win_ai``)
    이 모두 같은 값을 봐야 한다. 예전엔 여기서 ``C:\\`` 를 먼저 봐서,
    ``SystemDrive`` 가 C: 가 아닌 PC 나 ``MEMORY_CAT_DEMO_DISK_PERCENT``
    데모 변수를 켰을 때 진단(``win_ai._disk_detail_line``, ``metrics``
    쪽을 본다)과 서로 다른 수치를 보여줬다.
    """
    return _metrics_disk_usage()


def human_gb(n):
    """``metrics.human_gb`` 로 위임한다 — disk_usage() 와 같은 이유(R27 계열):

    옛 버전은 이 파일에 계산식(``n / 1024 ** 3``)을 따로 갖고 있었다.
    ``win_ai`` 의 진단은 ``brain.human_gb``(= ``metrics.human_gb``)를 쓰는데,
    텍스트만 같을 뿐 서로 다른 함수라 한쪽만 고치면 정보창과 진단 줄의
    단위 표시가 갈라질 수 있었다.
    """
    return _metrics_human_gb(n)


def top_memory_apps(limit=5):
    totals = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            m = p.info["memory_info"]
            if not m:
                continue
            name = p.info.get("name") or "?"
            totals[name] = totals.get(name, 0) + m.rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def _autostart_command():
    """이 실행본을 다시 띄울 명령줄(exe 면 exe, 소스면 pythonw + 이 파일)."""
    return win_app.autostart_command(
        sys.executable, getattr(sys, "frozen", False), os.path.abspath(__file__))


def worker_running(worker):
    """AI 워커가 아직 도는지. 없거나 끝났으면 False."""
    return worker is not None and worker.isRunning()


class Cat(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool)
        # Tool 창은 Qt 가 WA_QuitOnClose 를 꺼 둔다 — 앱을 붙잡는 창으로 안
        # 센다. 그러면 진단 결과창·안내창·사진 선택창이 닫히는 순간 Qt 가
        # "마지막 창이 닫혔다" 고 보고 앱을 끝낸다(R7 실기: 고양이가 꺼짐).
        # setWindowFlags 가 이 속성을 다시 끄므로 반드시 그 **뒤에** 켠다.
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_QuitOnClose, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("MemoryCat")

        self.cfg = load_config()
        self.language = resolve_language(self.cfg["language"], system_languages())
        themes = discover_themes()
        if themes and self.cfg["theme"] not in themes:
            self.cfg["theme"] = themes[0]
        self.pix = None
        self.l1, self.l2 = "…", ""
        self.detail = []
        self.bob = 0.0
        self.phase = 0.0
        self.score = 0.0
        self._drag = None
        # AI 워커(QThread) 참조. 지역 변수로 두면 GC 가 도는 스레드를 거둬 가서
        # 앱이 죽거나 작업이 조용히 멈춘다. 메뉴의 "진행 중" 표시도 이걸 본다.
        self._diagnosis_worker = None
        self._theme_worker = None

        cat = self.cat_size()
        w, h = cat + 24, cat + CATBOTTOM + 8
        scr = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        self.setGeometry(scr.right() - w - 40, scr.top() + 60, w, h)

        self.t_refresh = QtCore.QTimer(self)
        self.t_refresh.timeout.connect(self.refresh)
        self.t_refresh.start(REFRESH_MS)
        self.t_anim = QtCore.QTimer(self)
        self.t_anim.timeout.connect(self.animate)
        self.t_anim.start(60)
        self.refresh()

    def cat_size(self):
        return SIZES.get(self.cfg["size"], SIZES["보통"])

    def apply_layout(self):
        cat = self.cat_size()
        self.resize(cat + 24, cat + CATBOTTOM + 8)   # 좌상단 고정됨
        self.refresh()

    # ---------------------------------------------------------- data
    def refresh(self):
        # QTimer 슬롯에서 예외가 새어 나가면 PySide6 버전에 따라 앱이 그대로
        # 종료된다. 한 틱이 실패해도 삼키고 다음 틱을 기다린다.
        try:
            self._refresh_once()
        except Exception:
            pass

    def _refresh_once(self):
        disk = disk_usage()
        vm = psutil.virtual_memory()
        try:
            sw = psutil.swap_memory()
        except OSError:
            # 일부 환경은 swap_memory() 만 실패한다. 스왑을 0 으로 두고 계속한다.
            sw = SimpleNamespace(total=0, used=0, percent=0.0)
        dpct = disk.percent
        theme = self.cfg["theme"]
        language = self.language
        # 몸집·두 줄·기분 줄은 맥과 같은 판단(metrics.size_reading)을 쓴다.
        # 메모리 점수는 맥의 metrics.pressure_score 와 같은 vm.percent 다.
        view = win_app.cat_view(
            self.cfg["size_source"], memory=vm.percent, disk=dpct,
            ram_percent=vm.percent, frames=frame_count(theme),
            language=language)
        self.score = view.score
        self.pix = QtGui.QPixmap(frame_path(theme, view.index))
        self.l1 = view.l1
        self.l2 = view.l2

        self.detail = [
            view.mood_line,
            tr(language, "disk_detail", percent=dpct, used=human_gb(disk.used),
               total=human_gb(disk.total), free=human_gb(disk.free)),
            # 계산은 metrics.ram_used_for_display 가 한 곳에서 한다 —
            # 맥과 윈도우가 각자 세면 갈라진다.
            tr(language, "ram_detail", percent=vm.percent,
               used=human_gb(ram_used_for_display(vm)),
               total=human_gb(vm.total)),
        ]
        if sw.total > 0:
            self.detail.append(
                tr(language, "swap_detail", percent=sw.percent,
                   used=human_gb(sw.used), total=human_gb(sw.total)))
        self.detail.append(tr(language, "memory_apps"))
        try:
            for name, rss in top_memory_apps():
                self.detail.append(f"{rss / 1024 ** 2:,.0f} MB   {name}")
        except Exception:
            pass
        self.update()

    def animate(self):
        self.phase += 0.13
        self.bob = math.sin(self.phase) * (2.0 + 3.0 * self.score / 100.0)
        self.update()

    # ---------------------------------------------------------- paint
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        cat = self.cat_size()
        if self.pix and not self.pix.isNull():
            x = (w - cat) / 2.0
            y = 6.0 + self.bob
            p.drawPixmap(QtCore.QRectF(x, y, cat, cat), self.pix,
                         QtCore.QRectF(self.pix.rect()))
        self._text(p, self.l1, 11, True, QtCore.QRect(0, h - 34, w, 18))
        self._text(p, self.l2, 9, True, QtCore.QRect(0, h - 16, w, 14))

    def _text(self, p, text, pt, bold, rect):
        if not text:
            return
        f = QtGui.QFont()
        f.setPointSize(pt)
        f.setBold(bold)
        p.setFont(f)
        al = QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
        p.setPen(QtGui.QColor(0, 0, 0, 235))
        p.drawText(rect.adjusted(1, 1, 1, 1), al, text)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.drawText(rect, al, text)

    # ---------------------------------------------------------- mouse
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & QtCore.Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def contextMenuEvent(self, e):
        menu = QtWidgets.QMenu()
        for line in self.detail:
            a = menu.addAction(line)
            a.setEnabled(False)
        menu.addSeparator()

        language = self.language
        tm = menu.addMenu(tr(language, "menu_theme"))
        for key in discover_themes():
            a = tm.addAction(theme_label(key, language))
            a.setCheckable(True)
            a.setChecked(key == self.cfg["theme"])
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
        sm = menu.addMenu(tr(language, "menu_size"))
        for label in SIZES:
            a = sm.addAction(size_label(label, language))
            a.setCheckable(True)
            a.setChecked(label == self.cfg["size"])
            a.triggered.connect(lambda _=False, s=label: self.set_size(s))
        srcm = menu.addMenu(tr(language, "menu_size_source"))
        for option in SIZE_SOURCES:
            a = srcm.addAction(tr(language, f"size_source_{option}"))
            a.setCheckable(True)
            a.setChecked(option == self.cfg["size_source"])
            a.triggered.connect(
                lambda _=False, o=option: self.set_size_source(o))
        lm = menu.addMenu(tr(language, "menu_language"))
        for choice in LANGUAGE_OVERRIDES:
            a = lm.addAction(tr(language, f"language_{choice}"))
            a.setCheckable(True)
            a.setChecked(choice == self.cfg["language"])
            a.triggered.connect(lambda _=False, c=choice: self.set_language(c))

        a = menu.addAction(tr(language, "menu_pet_name"))
        a.triggered.connect(lambda _=False: self.set_pet_name())

        if win_ai_ui is not None:
            menu.addSeparator()
            if worker_running(self._diagnosis_worker):
                a = menu.addAction(tr(language, "menu_diagnosing"))
                a.setEnabled(False)
            else:
                a = menu.addAction(tr(language, "menu_diagnose"))
                a.triggered.connect(lambda _=False: self._start_diagnosis(language))
            if worker_running(self._theme_worker):
                a = menu.addAction(tr(language, "menu_pet_theme_running"))
                a.setEnabled(False)
            else:
                a = menu.addAction(tr(language, "menu_pet_theme"))
                a.triggered.connect(lambda _=False: self._start_theme(language))

        menu.addSeparator()
        a = menu.addAction(tr(language, "menu_autostart"))
        a.setCheckable(True)
        a.setChecked(win_app.autostart_enabled(win_app.registry_module()))
        # 인자 대신 액션의 체크 상태를 읽는다 — PySide6 가 triggered 의 bool 을
        # 안 넘기는 경우 기본값(False)으로 "끄기" 가 돼 버린다.
        a.triggered.connect(
            lambda _=False, act=a: self.toggle_autostart(act.isChecked()))
        menu.addAction(tr(language, "menu_refresh"), self.refresh)
        menu.addAction(tr(language, "menu_quit"), QtWidgets.QApplication.quit)
        menu.exec(e.globalPos())

    # ---------------------------------------------------------- AI
    # 메뉴 슬롯에서 예외가 새어 나가면 PySide6 버전에 따라 앱이 그대로 종료된다
    # (refresh 의 주석과 같은 이유). 그렇다고 삼키면 사용자는 아무 일도 안
    # 일어난 줄 안다 — 잡아서 보여 준다.
    def _start_diagnosis(self, language):
        try:
            self._diagnosis_worker = win_ai_ui.show_diagnosis(
                self, language, pet=self.cfg["pet_name"])
        except Exception as error:
            # 워커가 시작되기 전에 터진 예외(예: has_api_key() 가 부르는
            # dotenv 로더)라 _DiagnosisWorker.run() 의 안전망을 안 거친다 —
            # 여기서도 원문은 로그로만 보내고, 화면엔 번역된 안내만 띄운다.
            win_ai.log_ai_failure("diagnosis", error)
            QtWidgets.QMessageBox.warning(
                self, tr(language, "diagnosis_title"),
                tr(language, "diagnosis_error"))

    def _start_theme(self, language):
        try:
            self._theme_worker = win_ai_ui.make_theme(
                self, language, FRAMES_DIR, self._apply_new_theme)
        except Exception as error:
            # 위와 같은 이유 — 워커 시작 전에 터진 예외는 _ThemeWorker.run()
            # 을 안 거친다. 그 run() 과 같은 규칙을 그대로 따른다: ThemeError
            # 는 이미 번역까지 끝난 메시지라 로그로 다시 남기지 않는다.
            if not isinstance(error, win_ai.ThemeError):
                win_ai.log_ai_failure("theme", error)
            QtWidgets.QMessageBox.warning(
                self, tr(language, "pet_theme_error_title"),
                win_ai.theme_failure_message(error, language))

    def _apply_new_theme(self, name):
        # 워커 시그널이 QueuedConnection 으로 GUI 스레드에서 부른다. 새 테마는
        # 사용자 frames 에 생기고, theme_roots() 가 그쪽도 보므로 바로 잡힌다.
        self.cfg["theme"] = name
        save_config(self.cfg)
        self.refresh()

    def set_language(self, choice):
        self.cfg["language"] = choice
        self.language = resolve_language(choice, system_languages())
        save_config(self.cfg)
        self.refresh()

    def set_theme(self, key):
        self.cfg["theme"] = key
        save_config(self.cfg)
        self.refresh()

    def set_pet_name(self):
        # 맥 setPetName_ 과 같은 흐름: 묻고 → 다듬어 저장 → 확인. 비우면 기본
        # 호칭으로 돌아간다(이름을 지우는 것도 선택이다).
        language = self.language
        text, ok = QtWidgets.QInputDialog.getText(
            self, tr(language, "pet_name_title"), tr(language, "pet_name_hint"),
            QtWidgets.QLineEdit.EchoMode.Normal, self.cfg["pet_name"])
        if not ok:
            return
        self.cfg["pet_name"] = clean_pet_name(text)
        save_config(self.cfg)
        QtWidgets.QMessageBox.information(
            self, tr(language, "menu_pet_name"),
            tr(language, "pet_name_saved_title",
               pet=pet_name(self.cfg["pet_name"], language)))

    def toggle_autostart(self, enabled):
        # 레지스트리 값이 곧 상태라 설정 파일엔 적지 않는다. 막혀서 못 바꾸면
        # (회사 PC 정책 등) 체크만 바뀐 척하지 않게 알려 준다.
        if not win_app.set_autostart(
                bool(enabled), _autostart_command(), win_app.registry_module()):
            QtWidgets.QMessageBox.warning(
                self, tr(self.language, "menu_autostart"),
                tr(self.language, "autostart_error"))

    def set_size_source(self, option):
        self.cfg["size_source"] = win_app.normalize_size_source(option)
        save_config(self.cfg)
        self.refresh()

    def set_size(self, label):
        self.cfg["size"] = label
        save_config(self.cfg)
        self.apply_layout()


#: 중복 실행 방지 잠금(QLockFile). 지역 변수로만 두면 main() 이 끝나기도
#: 전에 GC 가 거둬 가서(다음 줄에서 열린 파일 핸들의 참조가 하나뿐이라)
#: 잠금이 풀려 버린다 — 모듈 전역에 붙잡아 프로세스가 끝날 때까지 살려 둔다.
_instance_lock = None


def main():
    global _instance_lock
    # 모듈 import 시점이 아니라 여기서 부른다 — 그래야 import 만으로는 아무
    # 파일도 안 써서 테스트(WindowsSourceRunTests 등)가 실제 사용자 폴더를
    # 건드리지 않는다. Cat() 이 load_config() 로 CONFIG 를 읽기 전에 옛
    # 설정이 있으면 옮겨 둬야 첫 실행에 반영된다.
    win_app.migrate_legacy_config(LEGACY_CONFIG, CONFIG)

    # exe 를 두 번 실행하면 고양이가 두 마리 뜬다(실기 확인됨). QApplication
    # 을 만들기 전에 잠가서, 이미 다른 뚱냥이가 살아 있으면 창 하나 없이
    # 조용히 끝낸다 — 맥의 desktop_cat.acquire_instance_lock 과 같은 원칙
    # (win_app.claim_single_instance 의 docstring 참고): 잠금 판정을 못
    # 믿을 상황이면 막지 않는다.
    #
    # QLockFile 생성과 enum 조회 자체는 win_app.claim_single_instance 의
    # 보호막(모든 예외를 삼키고 True 를 돌려주는) 밖이다 — PySide6 버전
    # 차이 등으로 여기서 예외가 나면 .pyw 라 창도 로그도 없이 그냥
    # 죽어 버린다. 그래서 이 두 줄도 같은 원칙으로 감싼다.
    try:
        _instance_lock = QtCore.QLockFile(win_app.instance_lock_path())
        lock_failed = QtCore.QLockFile.LockError.LockFailedError
    except Exception:
        _instance_lock = None  # 판정을 못 하면 막지 않는다
    else:
        if not win_app.claim_single_instance(_instance_lock, lock_failed):
            # 창 하나 없이 그냥 끝나면 현장에서 원인을 알 방법이 없다 — 흔적
            # 한 줄을 남긴다. 이 호출 자체도 예외를 내지 않는다(docstring 참고).
            win_app.log_instance_already_running()
            return

    # D-1: 잠금을 통과한 뒤에만 남긴다 — 곧바로 접히는 두 번째 exe 가 이 줄을
    # 쓰면 "이번 세션의 첫 AI 동작" 판정이 흐려진다. 로그 함수는 OSError 를
    # 삼키지만, 고양이가 뜨는 걸 막을 이유는 없으니 그 밖의 예외도 막는다.
    if win_ai is not None:
        try:
            win_ai.log_session_started()
        except Exception:
            pass

    # R7 #4: 자동 실행이 켜져 있는데 exe 를 옮겼으면 지금 경로로 다시 적는다.
    # 켜져 있지 않으면 아무것도 안 쓴다. 실패해도 고양이는 떠야 한다.
    try:
        win_app.refresh_autostart(_autostart_command(), win_app.registry_module())
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    cat = Cat()
    cat.show()
    code = app.exec()
    if worker_running(cat._diagnosis_worker) or worker_running(cat._theme_worker):
        # AI 워커가 아직 돌고 있으면 정상 종료 경로를 타지 않고 곧바로 끝낸다.
        # - sys.exit 로 가면 cat 과 함께 도는 QThread 가 파괴되고, ~QThread 가
        #   qFatal("Destroyed while thread is still running") 로 abort 한다.
        #   파이썬 종료 중 워커가 GIL 을 다시 잡으려다 창 없이 멈출 수도 있다.
        # - wait() 로 기다리면 OpenAI 호출은 중간에 끊을 수 없어서 최대 1~2분
        #   아무 반응 없이 멈춘다.
        # 설정은 바뀔 때마다 save_config 로 이미 저장했으니 잃는 것이 없다.
        # 만들다 만 테마가 남더라도 점으로 시작하는 임시 폴더(.building)라서
        # discover_themes 가 건너뛴다.
        os._exit(code)
    sys.exit(code)


if __name__ == "__main__":
    main()
