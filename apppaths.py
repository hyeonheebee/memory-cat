#!/usr/bin/env python3
"""메모리 뚱냥이가 쓰는 경로를 한 곳에서 정한다.

앱을 `.app` 번들로 설치하면 소스와 기본 테마는 번들 안(사실상 읽기 전용)에
들어가고, 사용자가 만든 것들은 번들 밖에 남아야 한다. 그래서 경로를 두 종류로
나눈다.

* **번들 자원** — `desktop_cat.py` 옆에 있는 것들. 기본 테마 4종이 여기 있다.
  앱을 다시 설치하면 통째로 덮어써진다.
* **사용자 데이터** — ``~/Library/Application Support/Memory Cat/``.
  설정(``config.json``), 직접 만든 펫 테마(``frames/mypet*``), API 키(``.env``)가
  여기 있다. 앱을 지워도, 저장소 폴더를 지워도 남는다.

저장소에서 바로 실행하는 개발 환경에서도 같은 규칙이 적용된다. 다만 ``.env`` 는
저장소 옆에 두는 관행이 있어서 사용자 데이터 쪽을 먼저 보고 없으면 소스 옆을
본다(:func:`dotenv_candidates`).
"""

import os
from pathlib import Path

APP_NAME = "Memory Cat"
BUNDLE_ID = "com.memorycat.desktop"

#: 번들 안에 함께 배포되는 기본 테마. 이 이름들만 번들로 복사한다.
BUNDLED_THEMES = ("cute", "simple", "madness", "derpy")

#: 사용자 데이터 위치를 통째로 옮기고 싶을 때 쓰는 탈출구(주로 테스트용).
HOME_ENV = "MEMORY_CAT_HOME"

_SOURCE_DIR = Path(__file__).resolve().parent


def source_dir() -> Path:
    """앱 소스와 기본 테마가 놓인 폴더(번들이면 ``Contents/Resources``)."""
    return _SOURCE_DIR


def bundled_frames_dir() -> Path:
    """기본 테마가 들어 있는 읽기 전용 ``frames/``."""
    return _SOURCE_DIR / "frames"


def user_data_dir() -> Path:
    """설정·커스텀 테마·API 키가 사는 곳. 없으면 만들지는 않는다."""
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / APP_NAME


def ensure_user_data_dir() -> Path:
    """:func:`user_data_dir` 을 만들어서 돌려준다. 실패해도 예외는 안 낸다."""
    target = user_data_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return target


def user_frames_dir() -> Path:
    """사용자가 만든 테마가 쌓이는 ``frames/``."""
    return user_data_dir() / "frames"


def config_file() -> Path:
    return user_data_dir() / "config.json"


def log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / APP_NAME


def dotenv_candidates():
    """``.env`` 를 찾을 순서. 사용자 데이터가 먼저, 소스 옆이 나중."""
    return (user_data_dir() / ".env", _SOURCE_DIR / ".env")


def theme_roots():
    """테마를 찾을 폴더들. 뒤쪽이 앞쪽을 가린다(사용자 테마 우선)."""
    return (bundled_frames_dir(), user_frames_dir())


def theme_dir(theme):
    """테마 이름 하나를 실제 폴더로 바꾼다. 사용자 테마가 기본 테마를 이긴다.

    어느 쪽에도 없으면 사용자 쪽 경로를 돌려준다. 호출부는 어차피
    ``os.listdir`` 실패를 감싸고 있어서 없는 경로가 와도 괜찮다.
    """
    name = str(theme)
    fallback = user_frames_dir() / name
    for root in reversed(theme_roots()):
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return fallback
