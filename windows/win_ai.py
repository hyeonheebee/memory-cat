"""윈도우판 AI 기능의 **Qt 없는** 부분.

맥 개발 환경에는 PySide6 가 없어서 Qt 를 import 하면 테스트가 못 돈다.
무엇을 보여줄지 정하는 일은 전부 여기서 하고, ``win_ai_ui`` 는 그 결과를
창에 얹기만 한다.

**이 파일은 파일을 지우지 않는다.** ``brain.safe_trash`` 도,
``collect_cleanup_candidates`` 도 부르지 않는다. 윈도우에는 되돌릴 수 있는
휴지통 API 가 없고, 캐시 폴더가 프로필 폴더 안쪽에 있어서 목록을 그대로
옮길 수도 없다. 설명만 한다.
"""

import datetime
import re
import traceback
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


#: 로그 파일 이름. ``apppaths.log_dir()`` 아래에 둔다.
_AI_LOG_FILE_NAME = "ai-errors.log"

#: ``sk-`` 로 시작하는 토큰. 앞에 다른 글자가 붙어도(``ssk-proj…``) ``sk-``
#: 부터는 가려진다 — 앵커를 걸지 않았기 때문이다. ``*`` 는 openai 가 키를
#: 가운데만 지워 보여줄 때(``sk-proj****abcd``) 쓰는 문자라 포함한다.
_SK_TOKEN_RE = re.compile(r"sk-[A-Za-z0-9_.\-*]+")

#: OpenAI 가 401 응답에 함께 주는 문장의 값 부분. 키가 ``sk-`` 로 시작하지
#: 않아도 이 패턴이 값을 가린다(따옴표·쉼표 전까지).
_INCORRECT_KEY_RE = re.compile(r"(Incorrect API key provided:)\s*[^'\",]*")

#: ``Authorization: Bearer <토큰>`` 형태.
_BEARER_RE = re.compile(r"Bearer\s+\S+")


def redact_secrets(text):
    """로그에 쓰기 전에 키 조각을 가린다.

    최소한 세 가지를 가린다: ``sk-`` 로 시작하는 토큰(중간에 ``*``·``.``·
    ``-``·``_`` 가 섞여도 끝까지), ``Incorrect API key provided: <값>`` 의
    값 부분(키가 ``sk-`` 로 시작하지 않아도), ``Bearer <토큰>``.
    가린 자리는 ``sk-***``·``[REDACTED]`` 처럼 알아볼 수 있는 표시로 남는다.
    """
    if not text:
        return text
    result = str(text)
    result = _SK_TOKEN_RE.sub("sk-***", result)
    result = _INCORRECT_KEY_RE.sub(r"\1 [REDACTED]", result)
    result = _BEARER_RE.sub("Bearer [REDACTED]", result)
    return result


def _exception_chain(error):
    """``error`` 부터 ``__cause__``·``__context__`` 를 따라가며 예외를 하나씩 낸다.

    두 사슬을 섞어 따라가므로(먼저 ``__cause__``, 없으면 ``__context__``)
    ``raise X from Y`` 로도, 그냥 ``except`` 안에서 다시 ``raise`` 로도 이어진
    사슬을 모두 본다. 순환은 ``id()`` 로 걸러 무한 루프를 막는다.
    """
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_invalid_key_error(error):
    """예외 사슬 어딘가에 ``status_code == 401`` 인 예외가 있는지.

    openai 의 ``AuthenticationError`` 가 이 속성을 가진다. ``vision_theme`` 은
    원래 예외를 문자열로 감싸 버리므로(``ThemeGenerationError``), 감싸인
    원본은 ``__cause__`` 를 따라가야 보인다.
    """
    return any(
        getattr(item, "status_code", None) == 401
        for item in _exception_chain(error)
    )


def _ai_error_log_path():
    return apppaths.log_dir() / _AI_LOG_FILE_NAME


def log_ai_failure(kind, error):
    """AI 실패 원문을(키 조각을 가린 뒤) 로그 파일에 덧붙여 쓴다.

    ``kind`` 는 "theme"·"diagnosis" 처럼 어떤 작업이었는지 나타내는 한 단어.
    로그 쓰기가 실패해도(폴더를 못 만들거나 파일을 못 열어도) 예외를 새로
    내지 않는다 — 사용자가 보는 흐름(번역된 안내창)은 그대로 이어져야 한다.
    """
    try:
        log_path = _ai_error_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            detail = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        except Exception:
            detail = f"{type(error).__name__}: {error}"
        timestamp = datetime.datetime.now().isoformat(timespec="seconds")
        entry = f"[{timestamp}] {kind}\n{redact_secrets(detail)}\n"
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(entry + "\n")
    except OSError:
        pass


def has_api_key() -> bool:
    return bool(brain._load_api_key())


def api_key_missing_message(language):
    """API 키가 없을 때 보여줄 (제목, 본문). 본문에 ``.env`` 경로가 들어간다.

    ``ensure_user_data_dir`` 로 그 폴더를 실제로 만든다 — 아무도 안 만들면
    안내가 존재하지 않는 폴더(%APPDATA%\\Memory Cat)를 가리키게 된다.
    """
    path = apppaths.ensure_user_data_dir() / ".env"
    return (
        tr(language, "missing_api_key_title"),
        tr(language, "missing_api_key_help", path=str(path)),
    )


#: 맥판 ``desktop_cat.diagnosis_result_content`` 과 같은 매핑. API 오류로
#: 규칙 기반 결과가 나왔을 때 어떤 문구를 보여줄지는 여기서 하나로 정한다.
_FALLBACK_REASON_KEYS = {
    "missing_api_key": "fallback_missing_api_key",
    "api_error": "fallback_api_error",
    "worker_error": "fallback_worker_error",
}


def diagnosis_lines(language):
    """결과창에 그대로 뿌릴 줄 목록. 마지막 줄은 **항상** 삭제 경고다.

    ``source`` 가 ``"fallback"`` 이면(API 키 없음·네트워크 오류 등) 첫 줄에
    안내를 넣는다. 안 넣으면 규칙 기반 결과가 AI 진단인 것처럼 보인다.
    """
    result = brain.diagnose(language=language, include_cleanup=False)
    lines = []
    if result.get("source") == "fallback":
        reason_key = _FALLBACK_REASON_KEYS.get(
            result.get("fallback_reason"), "fallback_unknown")
        lines.append(tr(
            language, "windows_diagnosis_source_fallback",
            reason=tr(language, reason_key)))
    lines.extend(result.get("why_slow", []))
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

    실패하면 원문(키 조각 포함)은 로그로만 보내고, 화면엔 번역된 안내만
    올린다 — 원문을 그대로 띄우면 버그 신고 스크린샷에 키 끝자리가 찍힌다.
    """
    problem = check_photo(photo_path, language)
    if problem:
        raise ThemeError(problem)
    try:
        vision_theme.build_theme(Path(photo_path), name, quality="medium")
    except Exception as error:          # 네트워크·API·이미지 오류를 한 자리로
        log_ai_failure("theme", error)
        if _is_invalid_key_error(error):
            path = str(apppaths.ensure_user_data_dir() / ".env")
            message = tr(language, "theme_error_invalid_key", path=path)
        else:
            message = tr(
                language, "theme_error_generic", path=str(_ai_error_log_path()))
        raise ThemeError(message) from error
    return name


def theme_failure_message(error, language):
    """테마 실패창에 올릴 문구를 정한다.

    ``create_theme`` 이 낸 ``ThemeError`` 는 이미 번역까지 끝낸 메시지이니
    그대로 쓴다. 그 밖의(있어선 안 되는) 예외가 워커까지 새 나온 경우를
    대비한 방어선 — 원문 대신 일반 안내로 감춘다.
    """
    if isinstance(error, ThemeError):
        return str(error)
    return tr(language, "theme_error_generic", path=str(_ai_error_log_path()))
