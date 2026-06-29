#!/usr/bin/env python3
"""메모리 뚱냥이 — macOS 바탕화면 둥둥 버전.

항상 위에 떠 있는 작은 고양이. 디스크(하드 용량)가 차오를수록
애기냥 -> 돼지냥으로 빵빵해지며 살짝 통통 튄다. 라벨에 디스크/램 표시.
우클릭: 상세 + 테마 + 크기 + 새로고침/종료. 설정은 config.json 에 저장.

테마는 frames/<이름>/ 폴더를 자동 인식한다. 새 테마 추가:
  python import_theme.py 내이미지.png 테마이름   (가로 N단계 시트)
"""
import json
import os

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
)
from Foundation import NSObject, NSMakeRect, NSMakePoint, NSMakeSize, NSAttributedString

import metrics as mc

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES_BASE = os.path.join(HERE, "frames")
CONFIG = os.path.join(HERE, "config.json")
REFRESH_SEC = 4.0
NSStatusWindowLevel = 25
CATBOTTOM = 46.0

THEME_LABELS = {"cute": "귀여운", "simple": "단순한", "madness": "광기", "derpy": "경각심"}
THEME_ORDER = ["cute", "simple", "madness", "derpy"]
SIZES = {"작게": 78.0, "보통": 104.0, "크게": 138.0, "왕": 176.0}
DEFAULT = {"theme": "cute", "size": "보통"}


def load_config():
    try:
        c = json.load(open(CONFIG))
        return {"theme": c.get("theme", DEFAULT["theme"]),
                "size": c.get("size", DEFAULT["size"])}
    except Exception:
        return dict(DEFAULT)


def save_config(cfg):
    try:
        json.dump(cfg, open(CONFIG, "w"), ensure_ascii=False)
    except Exception:
        pass


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

    def popUpMenu_(self, event):
        menu = NSMenu.alloc().init()
        for line in self.detail:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(line, None, "")
            it.setEnabled_(False)
            menu.addItem_(it)
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
