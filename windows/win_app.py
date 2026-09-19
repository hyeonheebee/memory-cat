"""윈도우 앱(``windows_cat.pyw``)의 **Qt 없는** 시작 로직.

맥 개발 환경에는 PySide6 가 없어서 Qt 를 import 하는 코드는 테스트를 못
돈다. ``windows_cat.pyw`` 를 시작할 때 필요한 판단 중 Qt·openai·Pillow
없이도 되는 것들을 여기 모아 두고 이 모듈에서 검사한다. stdlib 와
``apppaths`` 만 쓴다 — ``windows_cat.pyw`` 가 **직접**(try/except 없이)
import 하는 필수 모듈이라서, 여기서 무거운 의존성을 끌어오면 그 자체가
고양이를 못 띄우는 이유가 된다.
"""

from pathlib import Path


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
    legacy_path = Path(legacy_path)
    target_path = Path(target_path)

    if target_path.exists():
        return False
    if not legacy_path.is_file():
        return False

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        data = legacy_path.read_bytes()
        with open(target_path, "xb") as handle:
            handle.write(data)
    except OSError:
        return False
    return True
