"""AI 실패를 사용자에게 어떻게 보여 주고 무엇을 로그에 남길지 — 맥·윈도우 공용.

Qt 도 AppKit 도 import 하지 않는다. 맥 ``desktop_cat`` 과 윈도우 ``win_ai`` 가
같은 판단을 쓰게 하려고 R7 에서 ``win_ai`` 에서 옮겨 왔다 — 전엔 윈도우만
오류 원문을 번역 안내로 바꾸고 키 조각을 가렸고, 맥은 ``str(exc)`` 를 그대로
알림에 띄워 ``sk-proj****…abcd`` 같은 키 끝자리가 화면에 나왔다(G-1).
사진 고르기 전 키 확인(F-2)도 같은 이유로 여기 있다.
"""

import datetime
import re
import threading
import traceback

from openai import OpenAI

import apppaths
import brain
from i18n import tr

#: 로그 파일 이름. ``apppaths.log_dir()`` 아래에 둔다.
_AI_LOG_FILE_NAME = "ai-errors.log"

#: R5 M3: 동의 로그(``log_consent``)는 GUI 스레드에서, 진단·테마 실패 로그는
#: 워커 스레드(``_DiagnosisWorker``/``_ThemeWorker``)에서 남는다 — 둘이 같은
#: 파일에 동시에 append 할 수 있다. ``open(..., "a")`` 자체가 두 스레드의
#: 쓰기를 자동으로 순서 매겨 주지 않으므로, 이 파일에 쓰는 모든 자리를 이
#: 락으로 감싼다.
_LOG_LOCK = threading.Lock()

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


def is_invalid_key_error(error):
    """예외 사슬 어딘가에 ``status_code == 401`` 인 예외가 있는지.

    openai 의 ``AuthenticationError`` 가 이 속성을 가진다. ``vision_theme`` 은
    원래 예외를 문자열로 감싸 버리므로(``ThemeGenerationError``), 감싸인
    원본은 ``__cause__`` 를 따라가야 보인다.
    """
    return any(
        getattr(item, "status_code", None) == 401
        for item in _exception_chain(error)
    )


def ai_error_log_path():
    return apppaths.log_dir() / _AI_LOG_FILE_NAME


def _timestamp():
    """로그 줄 머리의 시각. R6: 밀리초까지 남긴다.

    초 단위로는 "consent shown → accepted" 간격이 0.2초인지 0.8초인지 못
    가른다(둘 다 같은 초나 1초 차로 찍힌다) — 사람이 읽고 눌렀는지, 클릭이
    그냥 넘어갔는지를 이 간격으로 판정하기로 했다(K-1).
    """
    return datetime.datetime.now().isoformat(timespec="milliseconds")


def log_ai_failure(kind, error):
    """AI 실패 원문을(키 조각을 가린 뒤) 로그 파일에 덧붙여 쓴다.

    ``kind`` 는 "theme"·"diagnosis" 처럼 어떤 작업이었는지 나타내는 한 단어.
    로그 쓰기가 실패해도(폴더를 못 만들거나 파일을 못 열어도) 예외를 새로
    내지 않는다 — 사용자가 보는 흐름(번역된 안내창)은 그대로 이어져야 한다.
    """
    try:
        log_path = ai_error_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            detail = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        except Exception:
            detail = f"{type(error).__name__}: {error}"
        timestamp = _timestamp()
        entry = f"[{timestamp}] {kind}\n{redact_secrets(detail)}\n"
        with _LOG_LOCK, open(log_path, "a", encoding="utf-8") as handle:
            handle.write(entry + "\n")
    except OSError:
        pass


def append_log_line(text):
    """``ai-errors.log`` 에 타임스탬프를 붙여 한 줄 남긴다.

    ``log_ai_failure`` 와 같은 파일·같은 로그 폴더를 쓴다. 폴더가 없으면
    만들고, 쓰기 실패(``OSError``)는 삼켜 사용자가 보는 흐름을 막지 않는다.

    R5 M3: ``_LOG_LOCK`` 으로 감싼다 — 동의 로그는 GUI 스레드에서, 진단
    fallback·워커 시작 로그는 워커 스레드에서 남아 같은 파일에 동시에 쓸 수
    있다.
    """
    try:
        log_path = ai_error_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = _timestamp()
        with _LOG_LOCK, open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {text}\n")
    except OSError:
        pass


#: 키 확인 시간 상한(초). GUI 스레드에서 도는 짧은 확인이라 길게 두지 않는다
#: — 넘기면 판정하지 않고 지금까지처럼 진행한다.
_KEY_CHECK_TIMEOUT = 5.0


def check_api_key():
    """키가 실제로 통하는지 ``"ok"``·``"invalid"``·``"unknown"`` 중 하나로.

    모델 목록 GET 한 번이다 — 사진을 보내지 않고 과금도 없다. 재시도는 하지
    않는다. **401 만** ``"invalid"`` 다. 그 밖의 실패(네트워크·타임아웃·403)는
    ``"unknown"`` — 예를 들어 권한을 좁힌 프로젝트 키는 모델 목록엔 403 을
    내도 이미지 생성은 될 수 있다. 모르는 걸 무효로 판정하면 멀쩡한 사용자를
    막는다.
    """
    try:
        client = OpenAI(
            api_key=brain._load_api_key(),
            timeout=_KEY_CHECK_TIMEOUT, max_retries=0)
        client.models.list()
    except Exception as error:
        return "invalid" if is_invalid_key_error(error) else "unknown"
    return "ok"


def invalid_key_message(language):
    """키가 틀렸을 때의 안내. 사전 확인(F-2)과 업로드 뒤 401 이 같은 문구를 쓴다."""
    path = str(apppaths.ensure_user_data_dir() / ".env")
    return tr(language, "theme_error_invalid_key", path=path)


def theme_key_problem(language):
    """F-2: 사진을 고르기 **전에** 키를 확인한다. 막아야 하면 안내 문구,
    아니면 ``None``.

    전에는 키 상태를 "있음/없음" 둘로만 봐서, 있지만 무효인 키는 사진 선택
    → 전송 동의 → 업로드까지 다 간 뒤에야 401 로 실패했다. 결과(ok·invalid·
    unknown)는 동의 줄과 같은 로그에 한 줄 남긴다 — 키나 오류 원문은 남기지
    않는다.
    """
    status = check_api_key()
    append_log_line(f"key check: {status}")
    if status == "invalid":
        return invalid_key_message(language)
    return None


def theme_failure_text(error, language):
    """테마 생성 실패를 사용자에게 보여 줄 문구로 바꾼다. 원문은 로그로만.

    원문(키 조각 포함)을 그대로 띄우면 버그 신고 스크린샷에 키 끝자리가
    찍힌다. 그래서 원문은 가린 뒤 로그에 남기고, 화면엔 401 이면 키 안내,
    그 밖이면 로그 위치를 알려 주는 일반 안내만 돌려준다.
    """
    log_ai_failure("theme", error)
    if is_invalid_key_error(error):
        return invalid_key_message(language)
    return tr(language, "theme_error_generic", path=str(ai_error_log_path()))

