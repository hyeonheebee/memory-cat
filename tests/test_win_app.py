"""``windows/win_app.py`` — 윈도우 앱 시작 로직 중 Qt 없는 부분을 검사한다.

PySide6 는 맥 개발 환경에 없어서 ``windows_cat.pyw`` 자체는 못 돌린다.
그래서 설정 파일을 옛 위치(exe 옆)에서 새 위치(``%APPDATA%\\Memory Cat``)로
옮기는 판단만 여기 ``win_app.py`` 에 두고 테스트한다. ``windows_cat.pyw``
와의 배선은 소스를 정적으로 검사해서 확인한다(직접 실행은 안 된다).
"""
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO = Path(__file__).resolve().parent.parent
_WINDOWS_DIR = str(_REPO / "windows")
if _WINDOWS_DIR not in sys.path:
    sys.path.insert(0, _WINDOWS_DIR)

import win_app  # noqa: E402


class _FailingWriteHandle:
    """진짜로 연 파일(exclusive "xb")을 감싸되, write 만 실패하게 흉내낸다.

    디스크 꽉 참·OneDrive 동기화 충돌처럼 "만들기(open)는 되는데 쓰기는
    실패" 하는 상황을 재현한다 — 진짜 디스크를 채우지 않고, 진짜 파일
    시스템 위에서 실제로 빈 파일이 먼저 생기는 순서까지 그대로 흉내낸다.
    """

    def __init__(self, real_handle):
        self._real = real_handle

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._real.close()
        return False

    def write(self, data):
        raise OSError("simulated write failure (test)")


def _open_with_failing_write(path, mode):
    """``win_app.open`` 자리에 패치해서 쓰는 함수. target 은 진짜로 만들고
    (exclusive 생성 시맨틱은 그대로 검사됨), write 호출만 실패시킨다."""
    real_handle = open(path, mode)
    return _FailingWriteHandle(real_handle)


class MigrateLegacyConfigTests(unittest.TestCase):
    def test_copies_legacy_file_when_target_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy" / "config.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"theme": "derpy"}', encoding="utf-8")
            # target 의 부모 폴더는 일부러 안 만든다 — 없어도 만들어져야 한다.
            target = Path(tmp) / "roaming" / "Memory Cat" / "config.json"

            result = win_app.migrate_legacy_config(legacy, target)

            self.assertTrue(result)
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(encoding="utf-8"),
                              '{"theme": "derpy"}')
            # 원본은 그대로 남는다.
            self.assertTrue(legacy.is_file())
            self.assertEqual(legacy.read_text(encoding="utf-8"),
                              '{"theme": "derpy"}')

    def test_does_not_overwrite_when_target_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy" / "config.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"theme": "derpy"}', encoding="utf-8")
            target = Path(tmp) / "roaming" / "Memory Cat" / "config.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"theme": "cute"}', encoding="utf-8")

            result = win_app.migrate_legacy_config(legacy, target)

            self.assertFalse(result)
            self.assertEqual(target.read_text(encoding="utf-8"),
                              '{"theme": "cute"}')

    def test_write_failure_after_create_removes_the_partial_target(self):
        """쓰기 실패(디스크 꽉 참 등)로 만든 빈/부분 target 을 남기면 다음
        실행이 "target 이 이미 있다"고 착각해 영영 재시도하지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy" / "config.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"theme": "derpy"}', encoding="utf-8")
            target = Path(tmp) / "roaming" / "Memory Cat" / "config.json"

            with patch("win_app.open", _open_with_failing_write, create=True):
                result = win_app.migrate_legacy_config(legacy, target)

            self.assertFalse(result)
            self.assertFalse(
                target.exists(),
                "쓰기 실패 뒤에도 빈/부분 target 파일이 남아 있습니다 — "
                "다음 실행이 재시도를 못 합니다.",
            )
            # legacy 는 절대 안 건드린다.
            self.assertTrue(legacy.is_file())
            self.assertEqual(legacy.read_text(encoding="utf-8"),
                              '{"theme": "derpy"}')

    def test_a_second_call_after_a_failed_write_self_heals(self):
        """실패로 지워진 뒤 다음 호출은 정상적으로 복사를 마친다."""
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy" / "config.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"theme": "derpy"}', encoding="utf-8")
            target = Path(tmp) / "roaming" / "Memory Cat" / "config.json"

            with patch("win_app.open", _open_with_failing_write, create=True):
                first = win_app.migrate_legacy_config(legacy, target)
            self.assertFalse(first)
            self.assertFalse(target.exists())

            second = win_app.migrate_legacy_config(legacy, target)

            self.assertTrue(second)
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(encoding="utf-8"),
                              '{"theme": "derpy"}')

    def test_returns_false_when_legacy_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy" / "config.json"  # 안 만든다
            target = Path(tmp) / "roaming" / "Memory Cat" / "config.json"

            result = win_app.migrate_legacy_config(legacy, target)

            self.assertFalse(result)
            self.assertFalse(target.exists())

    def test_returns_false_when_legacy_path_is_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy_dir"
            legacy.mkdir()
            target = Path(tmp) / "roaming" / "Memory Cat" / "config.json"

            result = win_app.migrate_legacy_config(legacy, target)

            self.assertFalse(result)
            self.assertFalse(target.exists())

    def test_returns_false_without_raising_when_target_parent_cannot_be_made(self):
        """target 의 부모 자리에 파일이 있으면 mkdir 이 못 만든다."""
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy" / "config.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"theme": "derpy"}', encoding="utf-8")
            # "roaming" 자리를 폴더가 아니라 파일로 만들어 mkdir(parents=True)
            # 가 실패하게 한다.
            blocker = Path(tmp) / "roaming"
            blocker.write_text("", encoding="utf-8")
            target = blocker / "Memory Cat" / "config.json"

            result = win_app.migrate_legacy_config(legacy, target)

            self.assertFalse(result)


class _RecordingLock:
    """``QtCore.QLockFile`` 과 같은 모양(``setStaleLockTime``·``tryLock``·
    ``error``)을 흉내내는 가짜. 호출 순서·인자를 기록해 둔다."""

    def __init__(self, try_lock_result=True, error_value=None, raise_on=None):
        self.calls = []
        self._try_lock_result = try_lock_result
        self._error_value = error_value
        self._raise_on = raise_on  # 이 이름의 메서드가 불리면 예외를 던진다.

    def setStaleLockTime(self, ms):
        if self._raise_on == "setStaleLockTime":
            raise RuntimeError("simulated failure (test)")
        self.calls.append(("setStaleLockTime", ms))

    def tryLock(self, timeout_ms):
        if self._raise_on == "tryLock":
            raise RuntimeError("simulated failure (test)")
        self.calls.append(("tryLock", timeout_ms))
        return self._try_lock_result

    def error(self):
        if self._raise_on == "error":
            raise RuntimeError("simulated failure (test)")
        self.calls.append(("error",))
        return self._error_value


#: QtCore.QLockFile.LockError.LockFailedError 자리에 넣는 표식. 진짜 enum 값이
#: 무엇이든 상관없이 "이 값과 같은지"만 비교하는 로직인지를 검사한다.
_LOCK_FAILED = object()


class ClaimSingleInstanceTests(unittest.TestCase):
    """``win_app.claim_single_instance`` — Qt 없이 판정 로직만 검사한다."""

    def test_returns_true_when_the_lock_is_acquired(self):
        lock = _RecordingLock(try_lock_result=True)
        self.assertTrue(win_app.claim_single_instance(lock, _LOCK_FAILED))

    def test_sets_stale_lock_time_to_zero_before_trying_the_lock(self):
        lock = _RecordingLock(try_lock_result=True)
        win_app.claim_single_instance(lock, _LOCK_FAILED)
        self.assertEqual(
            lock.calls[0], ("setStaleLockTime", 0),
            "setStaleLockTime(0) 을 tryLock 보다 먼저 부르지 않습니다.",
        )

    def test_try_lock_is_called_with_a_zero_timeout(self):
        lock = _RecordingLock(try_lock_result=True)
        win_app.claim_single_instance(lock, _LOCK_FAILED)
        self.assertIn(("tryLock", 0), lock.calls)

    def test_returns_false_when_another_instance_already_holds_the_lock(self):
        lock = _RecordingLock(try_lock_result=False, error_value=_LOCK_FAILED)
        self.assertFalse(win_app.claim_single_instance(lock, _LOCK_FAILED))

    def test_returns_true_for_any_other_lock_error(self):
        """권한 오류 등 LockFailedError 가 아닌 실패는 막지 않는다."""
        other_error = object()
        lock = _RecordingLock(try_lock_result=False, error_value=other_error)
        self.assertTrue(win_app.claim_single_instance(lock, _LOCK_FAILED))

    def test_returns_true_when_try_lock_raises(self):
        lock = _RecordingLock(raise_on="tryLock")
        self.assertTrue(win_app.claim_single_instance(lock, _LOCK_FAILED))

    def test_returns_true_when_set_stale_lock_time_raises(self):
        lock = _RecordingLock(raise_on="setStaleLockTime")
        self.assertTrue(win_app.claim_single_instance(lock, _LOCK_FAILED))

    def test_returns_true_when_error_raises(self):
        lock = _RecordingLock(try_lock_result=False, raise_on="error")
        self.assertTrue(win_app.claim_single_instance(lock, _LOCK_FAILED))


class InstanceLockPathTests(unittest.TestCase):
    """``win_app.instance_lock_path`` — 맥의 ``memory-cat.lock`` 과 같은 이름."""

    def test_lock_file_lives_under_memory_cat_home_and_the_folder_is_made(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "mchome"  # 일부러 안 만든다 — 만들어지는지 본다.
            with patch.dict(os.environ, {"MEMORY_CAT_HOME": str(home)}):
                result = win_app.instance_lock_path()

            self.assertEqual(Path(result), home / "memory-cat.lock")
            self.assertTrue(
                home.is_dir(),
                "instance_lock_path() 가 사용자 데이터 폴더를 안 만듭니다.",
            )


class LogInstanceAlreadyRunningTests(unittest.TestCase):
    """이미 다른 뚱냥이가 떠 있어 이번 실행을 접을 때, 창 하나 없이 그냥
    끝나면 현장에서 원인을 알 방법이 없다 — exe 를 두 번 눌렀는지, 다른
    이유로 죽었는지 구분이 안 된다. 흔적 한 줄을 남기되, 이 로그 기록
    자체가 고양이를 못 띄우는 이유가 되면 안 된다(``win_ai.log_ai_failure``
    와 같은 원칙)."""

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._patch = patch.object(
            win_app.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_it_writes_a_timestamped_line(self):
        win_app.log_instance_already_running()
        entries = list(Path(self._log_tmp.name).iterdir())
        self.assertEqual(len(entries), 1, "로그 파일이 정확히 하나 생겨야 합니다.")
        text = entries[0].read_text(encoding="utf-8")
        self.assertRegex(text, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_calling_twice_appends_rather_than_overwriting(self):
        win_app.log_instance_already_running()
        win_app.log_instance_already_running()
        entries = list(Path(self._log_tmp.name).iterdir())
        text = entries[0].read_text(encoding="utf-8")
        self.assertEqual(
            len([line for line in text.splitlines() if line.strip()]), 2,
            "두 번 부르면 두 줄이 남아야 합니다(덮어쓰면 안 됩니다).",
        )

    def test_it_never_raises_when_the_log_folder_cannot_be_created(self):
        blocked = Path(self._log_tmp.name) / "blocked-as-a-file"
        blocked.write_text("파일")
        with patch.object(win_app.apppaths, "log_dir", return_value=blocked / "logs"):
            win_app.log_instance_already_running()      # 예외가 새면 실패


class WindowsCatWiringTests(unittest.TestCase):
    """``windows_cat.pyw`` 는 못 돌리니 소스를 정적으로 검사한다."""

    APP = _REPO / "windows" / "windows_cat.pyw"

    def setUp(self):
        if not self.APP.is_file():
            self.skipTest(f"파일이 없습니다: {self.APP}")
        self.source = self.APP.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source, filename=str(self.APP))

    def test_config_comes_from_apppaths_config_file(self):
        found = False
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "CONFIG"
                            for t in node.targets)):
                dumped = ast.dump(node.value)
                if "config_file" in dumped and "apppaths" in dumped:
                    found = True
        self.assertTrue(
            found,
            "CONFIG 가 apppaths.config_file() 에서 오지 않습니다 — "
            "exe 를 다른 드라이브로 옮기면 설정이 또 떨어집니다.",
        )

    def test_win_app_is_imported_directly_not_inside_try_except(self):
        """win_app 은 Qt·openai 의존이 없는 필수 모듈이라 그냥 import 한다."""
        imports_win_app_at_top_level = any(
            isinstance(node, ast.Import)
            and any(alias.name == "win_app" for alias in node.names)
            for node in self.tree.body
        )
        self.assertTrue(
            imports_win_app_at_top_level,
            "windows_cat.pyw 최상위에서 `import win_app` 을 직접 하지 않습니다.",
        )

    def _main_function(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                return node
        return None

    def _top_level_function(self, name):
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def _class_method(self, class_name, method_name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return item
        return None

    def test_menu_slot_handlers_log_and_never_show_the_raw_error(self):
        """워커가 시작되기도 전에 터진 예외(``win_ai.has_api_key()`` 가 부르는
        dotenv 로더, ``win_ai.check_photo`` 등)는 ``_DiagnosisWorker``·
        ``_ThemeWorker`` 의 안전망(``win_ai_ui.py``)을 거치지 않는다 —
        ``_start_diagnosis``·``_start_theme`` 이 직접 잡는데, 여기서
        ``str(error)`` 를 그대로 ``QMessageBox`` 에 넘기면 영어 원문 예외가
        화면에 뜬다. 리터럴 문자열 하나만 보면 포맷이 조금만 바뀌어도
        놓치므로 AST 로 각 except 블록을 직접 본다: ``str(<예외 이름>)`` 호출이
        없어야 하고, ``win_ai.log_ai_failure`` 는 반드시 불러야 한다.
        """
        for method_name in ("_start_diagnosis", "_start_theme"):
            with self.subTest(method=method_name):
                method = self._class_method("Cat", method_name)
                self.assertIsNotNone(method, f"Cat.{method_name} 을 못 찾았습니다.")

                handlers = [
                    n for n in ast.walk(method) if isinstance(n, ast.ExceptHandler)
                ]
                self.assertTrue(handlers, f"{method_name} 에 except 블록이 없습니다.")
                error_names = {h.name for h in handlers if h.name}
                self.assertTrue(
                    error_names,
                    f"{method_name} 의 except 가 예외를 이름으로 받지 않습니다.",
                )

                logs_failure = False
                for handler in handlers:
                    for node in ast.walk(handler):
                        if not isinstance(node, ast.Call):
                            continue
                        func = node.func
                        if isinstance(func, ast.Name):
                            call_name = func.id
                        elif isinstance(func, ast.Attribute):
                            call_name = func.attr
                        else:
                            continue
                        if (call_name == "str" and node.args
                                and isinstance(node.args[0], ast.Name)
                                and node.args[0].id in error_names):
                            self.fail(
                                f"{method_name} 이 str(error) 를 그대로 다이얼로그에 "
                                "넘깁니다 — 영어 원문 예외가 화면에 보입니다."
                            )
                        if call_name == "log_ai_failure":
                            logs_failure = True
                self.assertTrue(
                    logs_failure,
                    f"{method_name} 이 win_ai.log_ai_failure 를 부르지 않습니다.",
                )

    def test_disk_usage_imports_from_metrics_at_top_level(self):
        """R27: 정보창·프레임 선택·진단이 같은 값을 봐야 한다.

        ``windows_cat.pyw`` 는 PySide6 가 없는 맥에서 실행도 import 도 안
        돼서, ``metrics.disk_usage`` 로 실제로 위임하는지는 직접 호출로
        확인할 수 없다 — 소스를 정적으로 본다.
        """
        imports_disk_usage = any(
            isinstance(node, ast.ImportFrom) and node.module == "metrics"
            and any(alias.name == "disk_usage" for alias in node.names)
            for node in self.tree.body
        )
        self.assertTrue(
            imports_disk_usage,
            "windows_cat.pyw 최상위에서 `from metrics import disk_usage`"
            " (별칭 포함) 을 하지 않습니다.",
        )

    @staticmethod
    def _non_docstring_body(func):
        """함수 본문에서 독스트링(설명문)을 뺀 실행문만.

        독스트링은 사람이 읽는 설명이라 "C:" 같은 옛 로직 얘기를 그대로
        적어 둘 수 있다 — ``ast.dump`` 로 실행문만 검사해야 설명과 실제
        코드를 헷갈리지 않는다.
        """
        body = func.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]
        return ast.dump(ast.Module(body=body, type_ignores=[]))

    def test_disk_usage_function_delegates_to_metrics_and_drops_c_drive_first(self):
        """옛 ``disk_usage()`` 는 ``C:\\`` 를 먼저 봐서 ``SystemDrive`` 가
        C: 가 아닌 PC 나 ``MEMORY_CAT_DEMO_DISK_PERCENT`` 데모 변수에서
        ``win_ai`` 의 진단(``metrics.disk_usage`` 경유)과 어긋났다(R27).
        이제는 ``metrics.disk_usage()`` 로 위임만 해야 한다 — 자체 fallback
        체인이나 ``C:\\`` 하드코딩이 남아 있으면 안 된다.
        """
        func = self._top_level_function("disk_usage")
        self.assertIsNotNone(func, "disk_usage() 함수를 못 찾았습니다.")
        dumped = self._non_docstring_body(func)
        self.assertIn(
            "_metrics_disk_usage", dumped,
            "disk_usage() 가 metrics 쪽 disk_usage 로 위임하지 않습니다.",
        )
        self.assertNotIn(
            "C:", dumped,
            "disk_usage() 에 C: 드라이브를 먼저 보는 옛 로직이 남아 있습니다.",
        )
        self.assertNotIn(
            "psutil", dumped,
            "disk_usage() 가 psutil 을 직접 불러 metrics 와 다른 값을 낼 "
            "수 있습니다 — metrics.disk_usage() 위임 하나만 남아야 합니다.",
        )

    def test_human_gb_function_delegates_to_metrics(self):
        """옛 ``human_gb()`` 는 ``metrics.human_gb`` 와 계산식이 텍스트로만
        겹칠 뿐이었다(C-2 와 같은 종류의 문제 — 한쪽만 고치면 정보창과
        진단이 다른 숫자를 보여준다). 이제는 위임만 해야 한다.
        """
        func = self._top_level_function("human_gb")
        self.assertIsNotNone(func, "human_gb() 함수를 못 찾았습니다.")
        dumped = self._non_docstring_body(func)
        self.assertIn(
            "_metrics_human_gb", dumped,
            "human_gb() 가 metrics.human_gb 로 위임하지 않습니다.",
        )
        self.assertNotIn(
            "1024", dumped,
            "human_gb() 에 자체 계산식이 남아 있습니다 — metrics.human_gb "
            "위임 하나만 남아야 합니다.",
        )

    def test_migrate_legacy_config_runs_inside_main_before_cat_is_built(self):
        """``ast.walk`` 는 너비 우선이라 소스 순서와 다를 수 있다(바로 아래
        ``test_claim_single_instance_runs_before_qapplication_is_built`` 의
        설명과 같은 이유) — 여기도 소스 위치(``lineno``, ``col_offset``)로
        정렬해서 실제 실행 순서를 본다."""
        main = self._main_function()
        self.assertIsNotNone(main, "main() 함수를 못 찾았습니다.")

        calls = []
        for node in ast.walk(main):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                else:
                    continue
                calls.append((node.lineno, node.col_offset, name))
        calls.sort()
        call_names = [name for _, _, name in calls]

        self.assertIn("migrate_legacy_config", call_names,
                       "main() 안에서 migrate_legacy_config 를 부르지 않습니다.")
        self.assertIn("Cat", call_names,
                       "main() 안에서 Cat(...) 을 만들지 않습니다.")
        self.assertLess(
            call_names.index("migrate_legacy_config"),
            call_names.index("Cat"),
            "migrate_legacy_config 는 Cat() 을 만들기 전에 불러야 합니다 — "
            "안 그러면 옛 설정이 있어도 이번 실행엔 못 씁니다.",
        )

    def test_migrate_legacy_config_is_not_called_at_module_top_level(self):
        """import 시점에 사용자 폴더에 쓰면 WindowsSourceRunTests 스텁 실행이
        실제 %APPDATA% 를 건드릴 수 있다 — 반드시 main() 안에서만 불러야
        한다."""
        top_level_call_names = []
        for node in self.tree.body:
            # 함수·클래스 본문은 "정의"일 뿐 모듈을 import 할 때 실행되지
            # 않는다. ast.walk 로 그 안까지 들어가면 main() 안의 정상 호출을
            # 최상위 호출로 오인한다 — 정의 자체는 건너뛴다.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    if isinstance(func, ast.Name):
                        top_level_call_names.append(func.id)
                    elif isinstance(func, ast.Attribute):
                        top_level_call_names.append(func.attr)
        self.assertNotIn(
            "migrate_legacy_config", top_level_call_names,
            "migrate_legacy_config 가 모듈 최상위(함수 밖)에서 불립니다.",
        )

    def test_claim_single_instance_runs_before_qapplication_is_built(self):
        """``ast.walk`` 는 너비 우선이라, ``if not win_app.claim_single_
        instance(...):`` 처럼 조건문 안에 중첩된 호출은 실제로는 앞줄인데도
        같은 깊이의 다른 statement 보다 늦게 나온다 — 그래서 순서는
        ``ast.walk`` 가 뱉는 순서가 아니라 소스 위치(``lineno``,
        ``col_offset``)로 판단한다."""
        main = self._main_function()
        self.assertIsNotNone(main, "main() 함수를 못 찾았습니다.")

        calls = []
        for node in ast.walk(main):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                else:
                    continue
                calls.append((node.lineno, node.col_offset, name))
        calls.sort()
        call_names = [name for _, _, name in calls]

        self.assertIn(
            "instance_lock_path", call_names,
            "main() 안에서 win_app.instance_lock_path() 를 부르지 않습니다.",
        )
        self.assertIn(
            "claim_single_instance", call_names,
            "main() 안에서 win_app.claim_single_instance 를 부르지 않습니다.",
        )
        self.assertIn(
            "QApplication", call_names,
            "main() 안에서 QApplication(...) 을 만들지 않습니다.",
        )
        self.assertLess(
            call_names.index("instance_lock_path"),
            call_names.index("QApplication"),
            "instance_lock_path 는 QApplication 을 만들기 전에 불러야 합니다.",
        )
        self.assertLess(
            call_names.index("claim_single_instance"),
            call_names.index("QApplication"),
            "claim_single_instance 는 QApplication 을 만들기 전에 불러야 합니다 — "
            "안 그러면 두 번째 인스턴스도 이벤트 루프까지 만들어 버립니다.",
        )

    def test_instance_already_running_is_logged_when_the_lock_is_taken(self):
        """두 번째 인스턴스는 창 하나 없이 조용히 끝난다(``main()`` 의
        ``return``) — ``win_app.log_instance_already_running()`` 을 그 분기
        (``if not win_app.claim_single_instance(...):``) 안에서 불러야
        현장에서 원인을 구분할 수 있다."""
        main = self._main_function()
        self.assertIsNotNone(main, "main() 함수를 못 찾았습니다.")

        target_if = None
        for node in ast.walk(main):
            if isinstance(node, ast.If):
                test = node.test
                if (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                        and isinstance(test.operand, ast.Call)):
                    func = test.operand.func
                    name = (func.id if isinstance(func, ast.Name)
                            else getattr(func, "attr", None))
                    if name == "claim_single_instance":
                        target_if = node
        self.assertIsNotNone(
            target_if,
            "claim_single_instance() 결과를 뒤집은 if 문을 못 찾았습니다.",
        )

        call_names = []
        for node in ast.walk(target_if):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    call_names.append(func.id)
                elif isinstance(func, ast.Attribute):
                    call_names.append(func.attr)
        self.assertIn(
            "log_instance_already_running", call_names,
            "인스턴스가 이미 떠 있을 때 로그를 남기지 않습니다.",
        )

    def test_uses_the_exact_qlockfile_lock_failed_error_enum(self):
        self.assertIn(
            "QtCore.QLockFile.LockError.LockFailedError", self.source,
            "PySide6 6.x 의 정확한 enum 이름"
            "(QtCore.QLockFile.LockError.LockFailedError)을 쓰지 않습니다.",
        )

    def test_instance_lock_object_is_kept_alive_at_module_level(self):
        """지역 변수로만 두면 GC 가 열려 있는 QLockFile 을 거둬 가서 잠금이
        풀린다 — main() 안에서 global 로 선언하고 모듈 최상위에서도
        초기화해야 프로세스가 끝날 때까지 붙잡혀 있다."""
        main = self._main_function()
        self.assertIsNotNone(main, "main() 함수를 못 찾았습니다.")

        declares_global = any(
            isinstance(node, ast.Global) and "_instance_lock" in node.names
            for node in ast.walk(main)
        )
        self.assertTrue(
            declares_global,
            "main() 안에서 `_instance_lock` 을 global 로 선언하지 않습니다 — "
            "지역 변수로 두면 GC 가 QLockFile 을 거둬 가서 잠금이 풀립니다.",
        )

        module_level_declared = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_instance_lock"
                    for t in node.targets)
            for node in self.tree.body
        )
        self.assertTrue(
            module_level_declared,
            "`_instance_lock` 이 모듈 최상위에서 초기화되지 않습니다.",
        )

    def test_instance_lock_is_not_created_at_module_top_level(self):
        """import 시점에 QLockFile 을 만들면 WindowsSourceRunTests 스텁
        실행이 실제 파일 시스템에 잠금 파일을 만들 수 있다 — 반드시 main()
        안에서만 만들어야 한다."""
        top_level_call_names = []
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    if isinstance(func, ast.Name):
                        top_level_call_names.append(func.id)
                    elif isinstance(func, ast.Attribute):
                        top_level_call_names.append(func.attr)
        self.assertNotIn(
            "QLockFile", top_level_call_names,
            "QLockFile 이 모듈 최상위(함수 밖)에서 만들어집니다.",
        )
        self.assertNotIn(
            "claim_single_instance", top_level_call_names,
            "claim_single_instance 가 모듈 최상위(함수 밖)에서 불립니다.",
        )


if __name__ == "__main__":
    unittest.main()
