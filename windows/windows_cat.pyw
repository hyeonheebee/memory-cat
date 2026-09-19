#!/usr/bin/env python3
"""메모리 뚱냥이 — 윈도우 버전 (PySide6).

바탕화면에 떠 있는 작은 고양이. C: 디스크(하드 용량)가 차오를수록
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
    chonk_stage,
    resolve_language,
    tr,
)
# metrics 는 저장소 루트의 플랫폼 공통 모듈이다(GUI 의존 없음). i18n 과 같은
# 방식으로 닿는다 — build_exe.bat 의 `--paths ".."` 와 `--hidden-import`.
from metrics import ram_used_for_display
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
try:
    import win_ai_ui
except ImportError:
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
DEFAULT = {"theme": "cute", "size": "보통", "language": LANGUAGE_AUTO}


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
                else LANGUAGE_AUTO}
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
    """윈도우는 C: 가 사용자가 보는 하드 용량."""
    drive = os.path.splitdrive(APPDIR)[0] + os.sep or "C:\\"
    for path in ("C:\\", drive):
        try:
            return psutil.disk_usage(path)
        except Exception:
            continue
    return psutil.disk_usage(os.getcwd())


def human_gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


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
        self.score = dpct
        theme = self.cfg["theme"]
        idx = int(round(dpct / 100 * (frame_count(theme) - 1)))
        self.pix = QtGui.QPixmap(frame_path(theme, idx))
        language = self.language
        self.l1 = f"{tr(language, 'disk')} {dpct:.0f}%"
        self.l2 = f"{tr(language, 'ram')} {vm.percent:.0f}%"

        mood = chonk_stage(dpct, language)
        self.detail = [
            # `source` 를 반드시 넘긴다. 이 문구는 맥판과 공유하는데, 맥은
            # 메모리/디스크를 고를 수 있어서 무엇을 보고 있는지 밝혀야 한다.
            # 윈도우판은 디스크만 본다. 이 인자를 빠뜨리면 KeyError 가 나고,
            # 아래 refresh() 가 예외를 삼켜서 앱은 멀쩡히 도는데 이 정보창만
            # 통째로 빈 채로 남는다(v0.3.0 에서 실제로 그랬다).
            tr(language, "mood_detail", mood=mood, percent=round(dpct),
               source=tr(language, "source_disk")),
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
        lm = menu.addMenu(tr(language, "menu_language"))
        for choice in LANGUAGE_OVERRIDES:
            a = lm.addAction(tr(language, f"language_{choice}"))
            a.setCheckable(True)
            a.setChecked(choice == self.cfg["language"])
            a.triggered.connect(lambda _=False, c=choice: self.set_language(c))

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
        menu.addAction(tr(language, "menu_refresh"), self.refresh)
        menu.addAction(tr(language, "menu_quit"), QtWidgets.QApplication.quit)
        menu.exec(e.globalPos())

    # ---------------------------------------------------------- AI
    # 메뉴 슬롯에서 예외가 새어 나가면 PySide6 버전에 따라 앱이 그대로 종료된다
    # (refresh 의 주석과 같은 이유). 그렇다고 삼키면 사용자는 아무 일도 안
    # 일어난 줄 안다 — 잡아서 보여 준다.
    def _start_diagnosis(self, language):
        try:
            self._diagnosis_worker = win_ai_ui.show_diagnosis(self, language)
        except Exception as error:
            QtWidgets.QMessageBox.warning(
                self, tr(language, "diagnosis_title"), str(error))

    def _start_theme(self, language):
        try:
            self._theme_worker = win_ai_ui.make_theme(
                self, language, FRAMES_DIR, self._apply_new_theme)
        except Exception as error:
            QtWidgets.QMessageBox.warning(
                self, tr(language, "pet_theme_error_title"), str(error))

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

    def set_size(self, label):
        self.cfg["size"] = label
        save_config(self.cfg)
        self.apply_layout()


def main():
    # 모듈 import 시점이 아니라 여기서 부른다 — 그래야 import 만으로는 아무
    # 파일도 안 써서 테스트(WindowsSourceRunTests 등)가 실제 사용자 폴더를
    # 건드리지 않는다. Cat() 이 load_config() 로 CONFIG 를 읽기 전에 옛
    # 설정이 있으면 옮겨 둬야 첫 실행에 반영된다.
    win_app.migrate_legacy_config(LEGACY_CONFIG, CONFIG)
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
