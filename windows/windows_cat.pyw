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

import psutil
from PySide6 import QtCore, QtGui, QtWidgets

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
THEME_LABELS = {"cute": "귀여운", "simple": "단순한", "madness": "광기", "derpy": "경각심"}
THEME_ORDER = ["cute", "simple", "madness", "derpy"]
SIZES = {"작게": 78, "보통": 104, "크게": 138, "왕": 176}
DEFAULT = {"theme": "cute", "size": "보통"}


def load_config():
    try:
        c = json.load(open(CONFIG, encoding="utf-8"))
        return {"theme": c.get("theme", DEFAULT["theme"]),
                "size": c.get("size", DEFAULT["size"])}
    except Exception:
        return dict(DEFAULT)


def save_config(cfg):
    try:
        json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), ensure_ascii=False)
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


def theme_label(key):
    return THEME_LABELS.get(key, key)


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
        disk = disk_usage()
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        dpct = disk.percent
        self.score = dpct
        theme = self.cfg["theme"]
        idx = int(round(dpct / 100 * (frame_count(theme) - 1)))
        self.pix = QtGui.QPixmap(frame_path(theme, idx))
        self.l1 = f"디스크 {dpct:.0f}%"
        self.l2 = f"램 {vm.percent:.0f}%"

        mood = ("여유" if dpct < 60 else "포동" if dpct < 80
                else "배불러" if dpct < 92 else "빵빵!")
        self.detail = [
            f"기분: {mood}  (디스크 {round(dpct)}%)",
            f"디스크 {dpct:.0f}%  ·  {human_gb(disk.used)} / {human_gb(disk.total)}  (여유 {human_gb(disk.free)})",
            f"RAM {vm.percent:.0f}%  ·  {human_gb(vm.used)} / {human_gb(vm.total)}",
        ]
        if sw.total > 0:
            self.detail.append(f"스왑 {sw.percent:.0f}%  ·  {human_gb(sw.used)} / {human_gb(sw.total)}")
        self.detail.append("─ 메모리 먹는 앱 ─")
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

        tm = menu.addMenu("테마")
        for key in discover_themes():
            a = tm.addAction(theme_label(key))
            a.setCheckable(True)
            a.setChecked(key == self.cfg["theme"])
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
        sm = menu.addMenu("크기")
        for label in SIZES:
            a = sm.addAction(label)
            a.setCheckable(True)
            a.setChecked(label == self.cfg["size"])
            a.triggered.connect(lambda _=False, s=label: self.set_size(s))

        menu.addSeparator()
        menu.addAction("새로고침", self.refresh)
        menu.addAction("종료", QtWidgets.QApplication.quit)
        menu.exec(e.globalPos())

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
