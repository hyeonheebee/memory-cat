"""윈도우판 AI 기능의 **Qt 없는** 부분.

맥 개발 환경에는 PySide6 가 없어서 Qt 를 import 하면 테스트가 못 돈다.
무엇을 보여줄지 정하는 일은 전부 여기서 하고, ``win_ai_ui`` 는 그 결과를
창에 얹기만 한다.

**이 파일은 파일을 지우지 않는다.** ``brain.safe_trash`` 도,
``collect_cleanup_candidates`` 도 부르지 않는다. 윈도우에는 되돌릴 수 있는
휴지통 API 가 없고, 캐시 폴더가 프로필 폴더 안쪽에 있어서 목록을 그대로
옮길 수도 없다. 설명만 한다.
"""

from pathlib import Path

import apppaths
import brain
import vision_theme
from i18n import tr

#: 이미지 API 가 받는 포맷. HEIC 는 여기 없다 — 아이폰 기본 포맷이라
#: 변환 없이 올리면 이유 모를 실패로 보인다.
SUPPORTED_PHOTO_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


class ThemeError(Exception):
    """커스텀 테마 생성 중 생긴 문제를 UI 에 보여줄 한 자리로 모은다."""


def has_api_key() -> bool:
    return bool(brain._load_api_key())


def api_key_missing_message(language):
    """API 키가 없을 때 보여줄 (제목, 본문). 본문에 ``.env`` 경로가 들어간다."""
    path = apppaths.user_data_dir() / ".env"
    return (
        tr(language, "missing_api_key_title"),
        tr(language, "missing_api_key_help", path=str(path)),
    )


def diagnosis_lines(language):
    """결과창에 그대로 뿌릴 줄 목록. 마지막 줄은 **항상** 삭제 경고다."""
    result = brain.diagnose(language=language, include_cleanup=False)
    lines = list(result.get("why_slow", []))
    advice = result.get("one_line_advice")
    if advice:
        lines.append("")
        lines.append(advice)
    lines.append("")
    lines.append(tr(language, "windows_delete_warning"))
    return lines


def theme_target_dir():
    """새 테마가 저장될 폴더. exe 옆이 아니라 사용자 데이터 쪽이다.

    exe 옆(``Program Files`` 등)은 관리자 권한 없이 쓸 수 없어 실패한다.
    """
    return apppaths.user_frames_dir()


def check_photo(path, language="ko"):
    """열 수 없는 형식이면 보여줄 문구를, 괜찮으면 ``None`` 을 돌려준다."""
    if Path(path).suffix.lower() not in SUPPORTED_PHOTO_SUFFIXES:
        return tr(language, "theme_error_format")
    return None


def next_theme_name(bundled_frames_dir):
    """``mypet``, ``mypet2``, ... 중 번들·사용자 폴더 어디에도 없는 첫 이름.

    한쪽에만 있는 이름을 재사용하면 기본 테마를 가리거나 기존 테마를 덮으려다
    실패한다. 맥의 ``desktop_cat.next_pet_theme_name`` 과 같은 규칙이다.
    """
    roots = (Path(bundled_frames_dir), theme_target_dir())
    candidate = "mypet"
    suffix = 2
    while any((root / candidate).exists() for root in roots):
        candidate = f"mypet{suffix}"
        suffix += 1
    return candidate


def create_theme(photo_path, name, language="ko"):
    """``vision_theme.build_theme`` 을 감싸 오류 문구를 한 자리로 모은다.

    이름이 비슷하지만 다른 함수다 — 이쪽은 윈도우 UI 가 쓰는 껍데기고,
    실제 생성은 ``vision_theme.build_theme`` 이 한다.
    """
    problem = check_photo(photo_path, language)
    if problem:
        raise ThemeError(problem)
    try:
        vision_theme.build_theme(Path(photo_path), name, quality="medium")
    except Exception as error:          # 네트워크·API·이미지 오류를 한 자리로
        raise ThemeError(str(error)) from error
    return name
