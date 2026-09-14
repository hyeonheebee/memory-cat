"""윈도우판 AI 기능의 **Qt 없는** 부분.

맥 개발 환경에는 PySide6 가 없어서 Qt 를 import 하면 테스트가 못 돈다.
무엇을 보여줄지 정하는 일은 전부 여기서 하고, ``win_ai_ui`` 는 그 결과를
창에 얹기만 한다.

**이 파일은 파일을 지우지 않는다.** ``brain.safe_trash`` 도,
``collect_cleanup_candidates`` 도 부르지 않는다. 윈도우에는 되돌릴 수 있는
휴지통 API 가 없고, 캐시 폴더가 프로필 폴더 안쪽에 있어서 목록을 그대로
옮길 수도 없다. 설명만 한다.
"""

import apppaths
import brain
from i18n import tr


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
