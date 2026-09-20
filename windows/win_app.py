"""윈도우 앱(``windows_cat.pyw``)의 **Qt 없는** 시작 로직.

맥 개발 환경에는 PySide6 가 없어서 Qt 를 import 하는 코드는 테스트를 못
돈다. ``windows_cat.pyw`` 를 시작할 때 필요한 판단 중 Qt·openai·Pillow
없이도 되는 것들을 여기 모아 두고 이 모듈에서 검사한다. stdlib 와
``apppaths`` 만 쓴다 — ``windows_cat.pyw`` 가 **직접**(try/except 없이)
import 하는 필수 모듈이라서, 여기서 무거운 의존성을 끌어오면 그 자체가
고양이를 못 띄우는 이유가 된다.
"""

import datetime
from pathlib import Path

# apppaths 는 저장소 루트의 가벼운 모듈이다(os·sys·pathlib 만) — Qt 도 없고
# 무거운 의존성도 없어서 이 "Qt 없는" 모듈에서도 그대로 쓸 수 있다. 잠금
# 파일이 살 폴더(맥과 같은 %APPDATA%\Memory Cat)를 여기서 받는다.
import apppaths

#: 맥의 desktop_cat.INSTANCE_LOCK_NAME 과 같은 이름 — 잠금은 플랫폼마다
#: 따로지만(맥은 fcntl.flock, 윈도우는 QLockFile) 파일 이름은 맞춰 둔다.
INSTANCE_LOCK_NAME = "memory-cat.lock"

#: 이미 떠 있는 인스턴스를 만나 조용히 접을 때 남기는 로그 파일 이름.
#: win_ai 의 ai-errors.log 와 같은 폴더(apppaths.log_dir())에 둔다.
INSTANCE_ALREADY_RUNNING_LOG_NAME = "instance-lock.log"


def instance_lock_path():
    """중복 실행 방지 잠금 파일 경로. ``apppaths.ensure_user_data_dir()``
    (%APPDATA%\\Memory Cat) 아래 ``memory-cat.lock``.

    ``ensure_user_data_dir()`` 을 써서 폴더가 없으면 만든다 — ``QLockFile``
    은 파일을 열 폴더가 이미 있어야 한다(스스로 만들지 않는다).
    """
    return str(apppaths.ensure_user_data_dir() / INSTANCE_LOCK_NAME)


def claim_single_instance(lock, lock_failed_error):
    """뚱냥이가 이 컴퓨터에 한 마리만 뜨도록 판정한다. ``True`` 면 계속
    실행해도 된다(=내가 유일하거나, 판정을 못 믿을 상황).

    ``lock`` 은 ``QtCore.QLockFile`` 과 같은 모양이면 된다
    (``setStaleLockTime(ms)``, ``tryLock(timeout_ms) -> bool``,
    ``error()``) — Qt 를 직접 import 하지 않고 테스트하기 위해서다.
    ``lock_failed_error`` 자리에는 호출부가
    ``QtCore.QLockFile.LockError.LockFailedError`` 를 넘긴다.

    판정 순서:

    1. ``setStaleLockTime(0)`` — "0 밀리초"는 시간으로 오래됐다고 보지
       않는다는 뜻이 아니라, ``QLockFile`` 이 잠금을 쥔 PID 가 **아직
       살아 있는지**만으로 죽은 잠금을 스스로 회수하게 한다는 뜻이다.
       이전 실행이 ``main()`` 의 ``os._exit()`` 처럼 잠금 파일을 정리할
       틈 없이 끝나도(강제 종료 포함), 다음 실행의 ``tryLock`` 이 그
       PID 가 이미 죽었다는 걸 보고 잠금을 되찾는다.
    2. ``tryLock(0)`` 이 성공하면(=이 프로세스가 잠금을 쥐면) ``True``.
    3. 실패했는데 ``error() == lock_failed_error`` (진짜 다른 뚱냥이가
       살아서 잠금을 쥐고 있음)면 ``False`` — 이번 실행은 막는다.
    4. 그 밖의 실패(권한 오류, 지원 안 하는 파일 시스템 등)는 ``True`` —
       판정 자체를 못 믿는 환경이면 막지 않는다. 맥의
       ``desktop_cat.acquire_instance_lock`` 과 같은 원칙: 두 마리가
       뜨는 것보다 한 마리도 안 뜨는 쪽이 나쁘다.
    5. ``lock`` 의 어떤 호출이든 예외를 내면(예상 못 한 PySide6 동작)
       ``True`` — 잠금 판정 자체가 고양이를 못 띄우는 이유가 되면 안
       된다.
    """
    try:
        lock.setStaleLockTime(0)
        if lock.tryLock(0):
            return True
        return lock.error() != lock_failed_error
    except Exception:
        return True


def log_instance_already_running():
    """이미 다른 뚱냥이가 떠 있어 이번 실행을 접을 때 흔적 한 줄을 남긴다.

    ``main()`` 은 이 경우 창 하나 없이 조용히 끝난다(사용자 관점에선 아무
    일도 안 일어난 것처럼 보인다) — 로그가 없으면 exe 를 실수로 두 번
    띄운 것인지, 다른 이유로 죽은 것인지 현장에서 구분할 방법이 없다.

    ``win_ai.log_ai_failure`` 와 같은 원칙: 로그 쓰기 자체가 실패해도(폴더를
    못 만들거나 파일을 못 열어도) 예외를 새로 내지 않는다 — 이 로그가 없어도
    (판정을 못 믿는 상황에서) 앱 흐름은 그대로 이어져야 한다. 정상 실행
    경로(잠금을 얻어서 계속 뜨는 경우)에서는 아예 불리지 않으니 매번 뜰 때
    로그가 쌓이는 일도 없다.
    """
    try:
        log_path = apppaths.log_dir() / INSTANCE_ALREADY_RUNNING_LOG_NAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] 이미 다른 인스턴스가 떠 있어 실행을 접었습니다.\n")
    except OSError:
        pass


def migrate_legacy_config(legacy_path, target_path):
    """구버전 config.json(exe 옆)을 새 위치(``apppaths.config_file()``)로
    **한 번만** 복사한다. 원본은 지우지 않는다.

    - target 이 이미 있으면 아무것도 하지 않는다(덮어쓰기 금지) — 이미
      새 위치에서 앱을 써 온 사람의 최신 설정을 legacy 로 되돌리면 안 된다.
    - legacy 가 파일이 아니면(없거나 폴더면) 옮길 것이 없다.
    - target 의 부모 폴더가 없으면 만든다. 그 자리에 파일이 있는 등
      못 만드는 경우는 OSError 로 걸러 False 를 돌려준다.
    - 다른 인스턴스가 동시에 옮기는 경우를 대비해 target 은 배타 생성
      (``"xb"``)으로 연다 — 이미 누가 만들었으면 여기서 걸리고, 서로
      덮어쓰지 않는다.
    - 실패는 전부 OSError 로 삼킨다. 옛 설정을 못 옮겨도 고양이는 떠야
      한다.
    """
    legacy = Path(legacy_path)
    target = Path(target_path)

    if target.exists():
        return False
    if not legacy.is_file():
        return False

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = legacy.read_bytes()
        handle = open(target, "xb")
    except OSError:
        # 이 시점까지는 target 을 만들지 못했다(부모 폴더 실패, legacy 읽기
        # 실패, 또는 다른 인스턴스가 그새 먼저 만들어서 "xb" 가 걸린 경우) —
        # 지울 파일이 없다.
        return False

    # open("xb") 가 성공했다는 것은 이 호출이 target 을 방금 만들었다는
    # 뜻이다. 여기부터 쓰기가 실패하면(디스크 꽉 참, OneDrive 동기화 충돌
    # 등) 빈/부분 파일을 그대로 남기면 다음 실행도 "target 이 이미 있다"고
    # 보고 영영 재시도를 안 한다 — 우리가 만든 파일만 지워서 다음 실행이
    # 다시 시도하게 한다. 원래 있던 target 이나 legacy 는 절대 안 건드린다.
    # config.json 은 작아서 쓰기가 한 번(단일 write 호출)으로 끝난다 — 그
    # 한 번의 write 도중 강제 종료되는 극단적인 경우까지는 못 막는다.
    try:
        with handle:
            handle.write(data)
    except OSError:
        try:
            target.unlink()
        except OSError:
            pass
        return False
    return True
