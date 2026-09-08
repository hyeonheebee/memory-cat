# -*- mode: python ; coding: utf-8 -*-
"""릴리스용 자립 번들 스펙 (PyInstaller).

`macos/build_app.py` 와 역할이 다르다. 둘을 헷갈리면 안 된다.

* ``build_app.py`` — **로컬 설치용**. `install_mac.command` 가 그 맥에서 만든
  venv 와 그 맥의 인터프리터를 조립한다. 결과물은 만든 맥에서만 돈다
  (인터프리터가 원본 프레임워크를 절대경로로 물고, 표준 라이브러리도 거기서
  빌려 쓴다). 설치 도구로서는 이게 맞고, 그대로 둔다.
* ``memorycat.spec`` (이 파일) — **배포용**. 파이썬 본체·표준 라이브러리·확장
  모듈을 전부 번들 안에 넣는다. 받는 쪽에 파이썬이 없어도 실행된다.

빌드:

    python -m PyInstaller --noconfirm --clean macos/memorycat.spec

포장 — **반드시 ditto 로 한다**:

    ditto -c -k --sequesterRsrc --keepParent \
        "dist/Memory Cat.app" "Memory-Cat-macOS-AppleSilicon.zip"

`zip -r` 를 쓰면 안 된다. 이 번들은 `Contents/Resources/*` 대부분이
`../Frameworks/*` 로 가는 심볼릭 링크인데, `zip -r` 은 링크를 따라가서 실체를
복사한다. 그러면 크기가 커질 뿐 아니라 PyInstaller 가 붙여 둔 ad-hoc 서명이
깨져서("bundle format is ambiguous") macOS 가 "손상되었기 때문에 열 수
없습니다" 를 띄운다. arm64 는 서명 없이는 실행 자체가 안 되므로 치명적이다.

빌드 후 반드시 검사한다(선언한 OS 하한이 실물과 맞는지 등):

    MEMORY_CAT_BUNDLE="dist/Memory Cat.app" MEMORY_CAT_REQUIRE_BUNDLE=1 \
        python -m pytest -q

`MEMORY_CAT_REQUIRE_BUNDLE=1` 을 빼면 번들을 못 찾았을 때 조용히 건너뛴다.
릴리스를 구울 때는 반드시 건다.

빌드에 쓰는 인터프리터가 곧 번들에 들어가는 인터프리터다. **Homebrew 파이썬
으로 구우면 안 된다** — Homebrew 는 병(bottle)을 빌드하는 기계의 OS 기준으로
굽기 때문에, Sequoia 에서 설치했으면 minos 15.0 이 박히고 그게 그대로 앱의
하한이 된다. macOS 11~14 사용자는 앱이 조용히 죽는다. python.org 설치본의
`macos11` 접미사 파일(framework 빌드, minos 11.0)을 쓴다. 이유와 굽는 순서는
`requirements-release.txt` 에 적어 두었다.

아키텍처는 빌드하는 기계를 따른다. universal2 는 만들지 않는다 —
psutil·Pillow·jiter 에 universal2 휠이 없어서 어차피 한쪽만 들어간다.
Intel 용이 필요하면 Intel 러너에서 이 스펙을 그대로 한 번 더 돌린다
(`.github/workflows/build-intel-mac.yml`).
"""

import platform
import sys
from pathlib import Path

# 스펙 파일에는 __file__ 이 없다. PyInstaller 가 넣어 주는 SPECPATH 를 쓴다.
REPO = Path(SPECPATH).resolve().parent  # noqa: F821  (SPECPATH is injected)

# 릴리스 태그와 반드시 같이 움직여야 하는 값. 태그를 올리면 여기도 올린다.
VERSION = "0.2.0"

# 번들이 요구하는 최소 macOS. **아키텍처마다 다르다.**
#
#   arm64  → 11.0   Apple Silicon 자체가 macOS 11 부터라 더 내려갈 수 없다.
#   x86_64 → 10.13  pyobjc 의 x86_64 휠이 여기를 타깃한다.
#
# 하나로 박아 두면 인텔 사용자 중 10.13~10.15 를 이유 없이 막는다(Launch
# Services 가 아예 열어 주지 않는다). 반대로 낮게 적으면 그 사이 macOS 에서
# dyld 가 조용히 죽인다. 둘 다 사용자에겐 "안 켜진다" 로만 보인다.
#
# 이 표는 손으로 관리한다. 대신 진실은 테스트가 지킨다 —
# BuiltBundleFloorTests 가 번들 안 모든 Mach-O 의 minos 최댓값과 이 값이
# **정확히 같은지** 본다. 휠이 올라가서 하한이 바뀌면 빌드가 시끄럽게
# 실패하니, 그때 이 표를 고치면 된다. 조용히 틀리는 일은 없다.
FLOOR_BY_ARCH = {
    "arm64": "11.0",
    "x86_64": "10.13",
}
_MACHINE = platform.machine()
if _MACHINE not in FLOOR_BY_ARCH:
    raise SystemExit(
        f"모르는 아키텍처 {_MACHINE!r} 입니다. FLOOR_BY_ARCH 에 추가하세요."
    )
MINIMUM_MACOS = FLOOR_BY_ARCH[_MACHINE]

# 기본 테마 목록은 apppaths 가 단일 진실 원천이다. 여기에 베껴 적으면 한쪽만
# 고쳤을 때 조용히 어긋난다(기본 테마를 추가했는데 번들에 안 들어가는 식).
# PyInstaller 는 스펙을 빌드 프로세스 안에서 exec 한다. 경로를 얹은 채로
# 두면 이후 훅이 `metrics`/`i18n` 같은 흔한 이름을 import 할 때 저장소 모듈이
# 이겨 버린다. import 하자마자 되돌린다(Analysis 는 pathex 로 따로 받는다).
sys.path.insert(0, str(REPO))
try:
    import apppaths  # noqa: E402  (위에서 경로를 얹은 뒤에야 import 된다)
finally:
    sys.path.remove(str(REPO))

BUNDLED_THEMES = apppaths.BUNDLED_THEMES

# `frames/` 에는 개발 중 만든 개인 테마(mypet*, gandi-* 등 — 실제 반려동물 사진이
# 들어간다)와 추적하지 않는 잡파일(_preview.png)이 같이 쌓인다. 공개 배포물에
# 그게 섞이면 되돌릴 수 없으므로, 폴더를 통째로 넣지 않고 **테마별로 실제 쓰는
# 프레임 파일만** 골라 넣는다.
#
# 검사는 assert 로 하지 않는다. `python -O` 로 빌드하면 assert 가 통째로
# 사라져서, 개인 사진 유출 방어선이 인터프리터 플래그 하나로 꺼져 버린다.
datas = []
for _theme in BUNDLED_THEMES:
    _src = REPO / "frames" / _theme
    if not _src.is_dir():
        raise SystemExit(f"기본 테마 {_theme} 가 없다: {_src}")
    _frames = sorted(_src.glob("cat_*.png"))
    if not _frames:
        raise SystemExit(f"기본 테마 {_theme} 에 cat_*.png 가 없다: {_src}")
    for _png in _frames:
        datas.append((str(_png), f"frames/{_theme}"))

# 배포물에도 라이선스 원문을 넣는다(MIT 요구사항).
datas.append((str(REPO / "LICENSE"), "."))


a = Analysis(  # noqa: F821
    [str(REPO / "desktop_cat.py")],
    pathex=[str(REPO)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 안 쓰는 GUI/과학 스택이 딸려 들어가면 번들만 커진다.
    excludes=["tkinter", "matplotlib", "pytest", "setuptools", "pip"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    # 이 이름이 그대로 CFBundleExecutable 이 된다(PyInstaller building/osx.py).
    # `build_app.py` 번들과 반드시 같아야 한다: install_mac.command 가 등록한
    # LaunchAgent 가 `Contents/MacOS/MemoryCat` 을 절대경로로 가리키고 있어서,
    # 이름을 바꾸면 기존 설치자가 새 번들로 덮어썼을 때 로그인 시 실행이
    # 조용히 실패한다(KeepAlive 가 60초마다 재시도만 반복).
    # 사용자에게 보이는 이름은 CFBundleName/CFBundleDisplayName 이라 영향 없다.
    name="MemoryCat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # LSUIElement 와 별개로, 터미널 창을 띄우지 않는다.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # 빌드하는 기계의 아키텍처
    codesign_identity=None,  # 미서명. 릴리스 노트에서 우회법을 안내한다.
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Memory Cat",
)

app = BUNDLE(  # noqa: F821
    coll,
    name="Memory Cat.app",
    icon=str(REPO / "macos" / "MemoryCat.icns"),
    bundle_identifier="com.memorycat.desktop",
    version=VERSION,
    info_plist={
        "CFBundleName": "Memory Cat",
        "CFBundleDisplayName": "Memory Cat",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        # 번들 전체의 하한은 **가장 높은 minos 를 요구하는 바이너리** 가 정한다.
        # 이 값을 낮게 적으면 그 사이 macOS 에서 Launch Services 가 막지 않고
        # 그냥 띄우고, dyld 가 프로세스를 죽인다. LSUIElement 라 창도 에러도
        # 안 뜨는 "조용한 무반응" — v0.1.0 을 못 쓰게 만든 그 증상이다.
        #
        # 부트로더(Contents/MacOS/MemoryCat) 하나만 보면 안 된다. 그건 번들에서
        # 가장 낮은 값을 갖기 때문에 무슨 값을 적어도 통과한다. 하한을 올리는
        # 것은 대개 파이썬 본체와 그 표준 라이브러리 .so 들이다.
        #
        # 값은 위 FLOOR_BY_ARCH 가 정한다(아키텍처마다 다르다).
        # 확인은 tests/test_macos_bundle.py 의 BuiltBundleFloorTests 가 한다.
        # 빌드 후 반드시 돌린다:
        #     MEMORY_CAT_BUNDLE="dist/Memory Cat.app" \
        #     MEMORY_CAT_REQUIRE_BUNDLE=1 python -m pytest -q
        "LSMinimumSystemVersion": MINIMUM_MACOS,
        # 독에 아이콘을 띄우지 않는 배경 앱. 바탕화면 위 고양이가 본체다.
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        # 아래 세 개는 build_app.py 번들과 파리티를 맞추려고 유지한다.
        "CFBundleDevelopmentRegion": "ko",
        "NSSupportsAutomaticTermination": False,
        "NSSupportsSuddenTermination": False,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHumanReadableCopyright": "Copyright (c) 2026 Hyeonhee Shim. MIT License.",
    },
)
