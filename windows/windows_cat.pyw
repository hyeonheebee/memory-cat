#!/usr/bin/env python3
"""메모리 뚱냥이 — 윈도우 버전 (PySide6).

바탕화면에 떠 있는 작은 고양이. C: 디스크(하드 용량)가 차오를수록
애기냥 -> 돼지냥으로 변하며 살짝 통통 튄다. 라벨에 디스크/램 표시.
- 드래그로 이동 / 우클릭: 상세 + 테마 + 크기 + 새로고침/종료
- 설정은 config.json 에 저장돼 유지

실행:  pythonw windows_cat.pyw   (또는 더블클릭)
필요:  pip install pyside6 psutil
"""
import json
import math
import os
import sys
from types import SimpleNamespace

import psutil
from PySide6 import QtCore, QtGui, QtWidgets

from i18n import (
    LANGUAGE_AUTO,
    LANGUAGE_OVERRIDES,
    chonk_stage,
    resolve_language,
    tr,
)

# 빌드(.exe)면 frames 는 번들 안, config 는 exe 옆에 둔다
if getattr(sys, "frozen", False):
    BASE = sys._MEIPASS
    APPDIR = os.path.dirname(sys.executable)
else:
    BASE = APPDIR = os.path.dirname(os.path.abspath(__file__))

FRAMES_DIR = os.path.join(BASE, "frames")
CONFIG = os.path.join(APPDIR, "config.json")

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
        with open(CONFIG, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False)
    except Exception:
        pass


def discover_themes():
    found = []
    if os.path.isdir(FRAMES_DIR):
        for n in sorted(os.listdir(FRAMES_DIR)):
            d = os.path.join(FRAMES_DIR, n)
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "cat_00.png")):
                found.append(n)
    return ([t for t in THEME_ORDER if t in found]
            + [t for t in found if t not in THEME_ORDER])


def theme_label(key, language):
    string_key = THEME_STRING_KEYS.get(key)
    return tr(language, string_key) if string_key else key


def size_label(key, language):
    string_key = SIZE_STRING_KEYS.get(key)
    return tr(language, string_key) if string_key else key


def frame_count(theme):
    d = os.path.join(FRAMES_DIR, theme)
    try:
        return max(1, len([f for f in os.listdir(d)
                           if f.startswith("cat_") and f.endswith(".png")]))
    except Exception:
        return 1


def frame_path(theme, idx):
    n = frame_count(theme)
    idx = max(0, min(n - 1, idx))
    return os.path.join(FRAMES_DIR, theme, f"cat_{idx:02d}.png")


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
            tr(language, "mood_detail", mood=mood, percent=round(dpct)),
            tr(language, "disk_detail", percent=dpct, used=human_gb(disk.used),
               total=human_gb(disk.total), free=human_gb(disk.free)),
            tr(language, "ram_detail", percent=vm.percent,
               used=human_gb(vm.used), total=human_gb(vm.total)),
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

        menu.addSeparator()
        menu.addAction(tr(language, "menu_refresh"), self.refresh)
        menu.addAction(tr(language, "menu_quit"), QtWidgets.QApplication.quit)
        menu.exec(e.globalPos())

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
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    cat = Cat()
    cat.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
