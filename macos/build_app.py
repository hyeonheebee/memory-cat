#!/usr/bin/env python3
"""저장소를 `Memory Cat.app` 번들로 조립하고 LaunchAgent plist 를 만든다.

py2app / PyInstaller 를 쓰지 않는다. 번들이라는 게 결국 정해진 폴더 구조 +
`Info.plist` + 실행 파일 하나라서, 그 정도는 표준 라이브러리만으로 만들 수 있다.
그렇게 하면 무엇이 들어갔는지 눈으로 셀 수 있고, 윈도우 PyInstaller 빌드가 겪는
코드서명·백신 오탐 문제를 macOS 쪽으로 옮겨오지 않는다.

만들어지는 구조::

    Memory Cat.app/
      Contents/
        Info.plist            ← CFBundleIdentifier / LSUIElement
        MacOS/
          MemoryCat           ← 셸 런처 (CFBundleExecutable)
          MemoryCatPython     ← 프레임워크 인터프리터 사본
        Resources/
          MemoryCat.icns      ← 앱 아이콘 (CFBundleIconFile)
          *.py                ← 앱 소스
          frames/             ← 기본 테마 4종
          venv/               ← 설치 스크립트가 미리 만들어 둔 가상환경
          pythonhome          ← 인터프리터가 붙을 프레임워크 경로
          uninstall_mac.command

`MacOS/MemoryPython` 이 왜 인터프리터 "사본" 이어야 하냐면: CoreFoundation 은
dyld 가 알려주는 실행 파일 경로에서 위로 올라가며 `Contents/Info.plist` 를 찾아
메인 번들을 정한다. 셸 스크립트가 venv 의 python 을 실행하면 실행 파일은
`Python.framework/.../Python.app/Contents/MacOS/Python` 이 되고, 알림은
`org.python.python` 이름으로 나간다. 인터프리터가 우리 번들 안에 있어야
`com.memorycat.desktop` 이 된다. (측정해서 확인함 — README 참고)

이 스크립트는 서브프로세스를 쓰지 않는다. 저장소의 파이썬 소스에는
`subprocess`/`os.system`/`osascript` 호출이 하나도 없고, 그 성질을 유지한다.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import apppaths  # noqa: E402

EXECUTABLE_NAME = "MemoryCat"
INTERPRETER_NAME = "MemoryCatPython"
PYTHON_HOME_FILE = "pythonhome"
VERSION = "1.0.0"

#: 번들 안에서의 아이콘 파일 이름. ``CFBundleIconFile`` 에 이 값이 그대로
#: 들어간다. 확장자를 붙여 둔다 — 애플 문서가 허용하는 형태고(크롬도
#: ``app.icns`` 를 쓴다), 확장자를 빼면 "Resources 안의 무엇을 가리키는가" 가
#: 규칙에 의존하게 된다. 붙여 두면 plist 값이 곧 파일 이름이라 검증이 쉽다.
ICON_FILE = "MemoryCat.icns"

#: 저장소 안에서 아이콘이 있는 위치. 빌드할 때 굽지 않고 커밋된 걸 복사한다.
#: 굽는 방법은 ``macos/make_icon.command`` 참고.
ICON_SOURCE = ("macos", ICON_FILE)

#: 번들에 들어가는 파이썬 모듈. 글롭 대신 명시해서 무엇이 배포되는지 드러낸다.
APP_MODULES = (
    "desktop_cat.py",
    "apppaths.py",
    "brain.py",
    "metrics.py",
    "i18n.py",
    "personality.py",
    "vision_theme.py",
    "import_theme.py",
    "generate_frames.py",
)

EXTRA_RESOURCES = ("uninstall_mac.command", "LICENSE")

# 런처는 경로를 문자열로 끼워 넣지 않는다. 자기 위치에서 전부 역산한다.
# 그래서 설치 경로에 `&`, 공백, 따옴표가 있어도 이 파일은 그대로다.
LAUNCHER = """\
#!/bin/bash
# Memory Cat 번들 런처. 경로는 전부 자기 위치에서 역산하므로
# 번들을 통째로 옮겨도 그대로 동작한다.
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(cd "$HERE/../Resources" && pwd)"

# 가상환경 site-packages 를 PYTHONPATH 로 붙인다. 런처가 실행하는 인터프리터는
# venv 의 python 이 아니라 번들 안 사본이라서 pyvenv.cfg 를 타지 않는다.
for candidate in "$RES"/venv/lib/python*/site-packages; do
    if [ -d "$candidate" ]; then
        PYTHONPATH="$candidate${PYTHONPATH:+:$PYTHONPATH}"
    fi
done
export PYTHONPATH

# 애플이 배포하는 인터프리터는 프레임워크를
# @executable_path/../../../../Python3 로 찾는다. 번들 안으로 복사하면 그 상대
# 경로가 깨지므로, 원래 프레임워크가 있는 폴더를 dyld 검색 경로에 넣어 준다.
# 바이너리를 고쳐서 애플 서명을 무효화하는 것보다 이쪽이 덜 침습적이다.
if [ -f "$RES/@@PYTHON_HOME_FILE@@" ]; then
    PYHOME="$(cat "$RES/@@PYTHON_HOME_FILE@@")"
    if [ -d "$PYHOME" ]; then
        export DYLD_LIBRARY_PATH="$PYHOME${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    fi
fi

# 번들 안에 __pycache__ 를 만들지 않는다. 설치된 앱은 읽기 전용으로 둔다.
export PYTHONDONTWRITEBYTECODE=1

exec "$HERE/@@INTERPRETER_NAME@@" "$RES/desktop_cat.py" "$@"
"""


class BuildError(RuntimeError):
    """번들을 만들 수 없을 때."""


def launcher_script() -> str:
    """런처 셸 스크립트 본문. 치환되는 건 파일 이름뿐, 경로는 없다."""
    return LAUNCHER.replace("@@PYTHON_HOME_FILE@@", PYTHON_HOME_FILE).replace(
        "@@INTERPRETER_NAME@@", INTERPRETER_NAME
    )


def info_plist(version: str = VERSION, icon: str = ICON_FILE) -> dict:
    """번들 Info.plist 내용.

    ``LSUIElement`` 는 앱이 이미 호출하는
    ``setActivationPolicy_(NSApplicationActivationPolicyAccessory)`` 와 같은
    말이다. Dock 아이콘도 메뉴 막대도 없는 보조 앱이라는 뜻.

    ``icon`` 이 ``None`` 이면 ``CFBundleIconFile`` 자체를 넣지 않는다. 없는
    파일을 가리키는 키를 남기는 게 키가 아예 없는 것보다 나쁘기 때문이다.
    Launch Services 는 그 경로를 캐시해 두고, 나중에 아이콘을 제대로 넣어도
    깨진 상태가 남아 있을 수 있다.

    ``CFBundleIconName`` 은 쓰지 않는다. 그건 에셋 카탈로그(``Assets.car``)를
    전제로 하는 키인데 이 번들에는 카탈로그가 없다.
    """
    payload = {
        "CFBundleDevelopmentRegion": "ko",
        "CFBundleDisplayName": apppaths.APP_NAME,
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundleIdentifier": apppaths.BUNDLE_ID,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": apppaths.APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "LSMinimumSystemVersion": "10.15",
        # 데스크톱 액세서리다. Dock 에 뜨지 않는다.
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "MIT License",
        "NSSupportsAutomaticTermination": False,
        "NSSupportsSuddenTermination": False,
    }
    if icon:
        payload["CFBundleIconFile"] = icon
    return payload


def launch_agent_plist(executable: Path, log_file: Path, working_dir: Path) -> dict:
    """LaunchAgent plist 내용.

    XML 을 손으로 쓰지 않는다. :mod:`plistlib` 이 이스케이프를 책임지므로
    경로에 ``&``, ``<``, ``>``, 따옴표가 있어도 깨지지 않는다.
    """
    return {
        "Label": apppaths.BUNDLE_ID,
        "ProgramArguments": [str(executable)],
        "WorkingDirectory": str(working_dir),
        "RunAtLoad": True,
        # 비정상 종료일 때만 되살린다. 사용자가 메뉴로 종료하면(정상 종료)
        # 다시 뜨지 않는다. ThrottleInterval 이 크래시 루프의 회전 속도를 잡는다.
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 60,
        "ProcessType": "Interactive",
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }


def framework_interpreter(base_prefix=None):
    """번들 안으로 복사할 인터프리터를 찾는다.

    프레임워크 빌드의 ``bin/python3`` 은 ``Python.app`` 으로 다시 exec 하는
    껍데기라서 복사해도 소용이 없다. 진짜 인터프리터인
    ``Resources/Python.app/Contents/MacOS/Python`` 을 찾아야 한다.
    """
    base = Path(base_prefix or sys.base_prefix)
    candidate = base / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    if candidate.is_file():
        return candidate
    return None


def _copy_executable(source: Path, target: Path) -> None:
    shutil.copy2(source, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_executable(target: Path, text: str) -> None:
    target.write_text(text, encoding="utf-8")
    target.chmod(0o755)


def migrate_user_data(source: Path, user_home: Path) -> dict:
    """저장소 폴더에 있던 사용자 데이터를 Application Support 로 옮겨 심는다.

    **복사만 한다. 원본은 건드리지 않는다.** 옮기다 실패해서 커스텀 테마가
    사라지는 상황을 만들지 않기 위해서다. 목적지에 같은 이름이 이미 있으면
    덮어쓰지 않고 건너뛴다.
    """
    moved = {"config": False, "dotenv": False, "themes": []}
    user_home.mkdir(parents=True, exist_ok=True)

    for name, key in (("config.json", "config"), (".env", "dotenv")):
        origin = source / name
        target = user_home / name
        if origin.is_file() and not origin.is_symlink() and not target.exists():
            shutil.copy2(origin, target)
            moved[key] = True

    frames = source / "frames"
    if frames.is_dir():
        user_frames = user_home / "frames"
        for entry in sorted(frames.iterdir()):
            if not entry.is_dir() or entry.is_symlink():
                continue
            if entry.name in apppaths.BUNDLED_THEMES or entry.name.startswith("."):
                continue
            if not (entry / "cat_00.png").is_file():
                continue
            target = user_frames / entry.name
            if target.exists():
                continue
            user_frames.mkdir(parents=True, exist_ok=True)
            shutil.copytree(entry, target)
            moved["themes"].append(entry.name)
    return moved


def assemble(source: Path, app: Path, interpreter=None) -> dict:
    """번들 뼈대를 채운다. ``Contents/Resources/venv`` 는 이미 있다고 가정한다."""
    if not (source / "desktop_cat.py").is_file():
        raise BuildError(f"소스 폴더가 아닙니다: {source}")

    contents = app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    for name in APP_MODULES:
        origin = source / name
        if not origin.is_file():
            raise BuildError(f"번들에 넣을 파일이 없습니다: {origin}")
        shutil.copy2(origin, resources / name)

    for name in EXTRA_RESOURCES:
        origin = source / name
        if origin.is_file():
            shutil.copy2(origin, resources / name)
    uninstaller = resources / "uninstall_mac.command"
    if uninstaller.is_file():
        uninstaller.chmod(0o755)

    frames = resources / "frames"
    for theme in apppaths.BUNDLED_THEMES:
        origin = source / "frames" / theme
        if not origin.is_dir():
            raise BuildError(f"기본 테마가 없습니다: {origin}")
        target = frames / theme
        if target.exists():
            shutil.rmtree(target)
        frames.mkdir(parents=True, exist_ok=True)
        shutil.copytree(origin, target)

    warnings = []

    # 아이콘은 빌드할 때 굽지 않는다. 커밋된 .icns 를 그대로 복사한다.
    # 이유는 두 가지. (1) 굽는 데 필요한 `iconutil` 은 서브프로세스 호출이고,
    # 이 파일은 서브프로세스를 쓰지 않는다. (2) Pillow 의 ICNS 저장은
    # 16pt·32pt 1x 칸을 만들지 못한다. 자세한 건 macos/make_icon.command.
    icon_origin = source.joinpath(*ICON_SOURCE)
    icon = ICON_FILE
    if icon_origin.is_file():
        shutil.copy2(icon_origin, resources / ICON_FILE)
    else:
        # 아이콘이 없어도 앱은 돈다. 다만 없는 파일을 가리키는 키는 남기지
        # 않는다 — 그러면 Launch Services 가 깨진 아이콘을 캐시한다.
        icon = None
        warnings.append(
            f"앱 아이콘을 찾지 못했습니다: {icon_origin}. "
            "기본 응용 프로그램 아이콘으로 표시됩니다. "
            "macos/make_icon.command 로 다시 구울 수 있습니다."
        )

    with open(contents / "Info.plist", "wb") as handle:
        plistlib.dump(info_plist(icon=icon), handle)

    _write_executable(macos / EXECUTABLE_NAME, launcher_script())

    interpreter = interpreter or framework_interpreter()
    if interpreter is None:
        # 프레임워크 빌드가 아니면 번들 정체성을 줄 방법이 없다. 앱은 돌지만
        # 알림은 여전히 "Python" 이름으로 나간다. 조용히 넘기지 않고 알린다.
        interpreter = Path(getattr(sys, "_base_executable", None) or sys.executable)
        warnings.append(
            "프레임워크 인터프리터(Python.app)를 찾지 못했습니다. "
            "앱은 동작하지만 알림이 'Python' 이름으로 표시될 수 있습니다."
        )
    _copy_executable(Path(interpreter), macos / INTERPRETER_NAME)
    (resources / PYTHON_HOME_FILE).write_text(sys.base_prefix, encoding="utf-8")

    return {"warnings": warnings, "interpreter": str(interpreter), "icon": icon}


def write_launch_agent(app: Path, plist_path: Path, log_file: Path,
                       working_dir: Path) -> None:
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    payload = launch_agent_plist(
        app / "Contents" / "MacOS" / EXECUTABLE_NAME, log_file, working_dir
    )
    with open(plist_path, "wb") as handle:
        plistlib.dump(payload, handle)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Memory Cat .app 번들 조립")
    parser.add_argument("--source", required=True, help="저장소 폴더")
    parser.add_argument("--app", required=True, help="만들 .app 경로")
    parser.add_argument("--launch-agent", help="LaunchAgent plist 경로")
    parser.add_argument("--log", help="앱 로그 파일 경로")
    parser.add_argument(
        "--skip-migration", action="store_true", help="사용자 데이터 이전 생략"
    )
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser().resolve()
    app = Path(args.app).expanduser()

    result = assemble(source, app)
    for warning in result["warnings"]:
        print(f"⚠️  {warning}")

    if not args.skip_migration:
        moved = migrate_user_data(source, apppaths.ensure_user_data_dir())
        if moved["config"]:
            print("   설정을 사용자 폴더로 옮겼습니다: config.json")
        if moved["dotenv"]:
            print("   API 키 파일을 사용자 폴더로 옮겼습니다: .env")
        for name in moved["themes"]:
            print(f"   직접 만든 테마를 사용자 폴더로 옮겼습니다: {name}")

    log_file = Path(args.log).expanduser() if args.log else apppaths.log_dir() / "cat.log"
    if args.launch_agent:
        plist_path = Path(args.launch_agent).expanduser()
    else:
        plist_path = (
            Path.home() / "Library" / "LaunchAgents" / f"{apppaths.BUNDLE_ID}.plist"
        )
    write_launch_agent(app, plist_path, log_file, Path.home())
    print(f"   LaunchAgent: {plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
