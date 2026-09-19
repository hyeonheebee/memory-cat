"""``windows/win_app.py`` — 윈도우 앱 시작 로직 중 Qt 없는 부분을 검사한다.

PySide6 는 맥 개발 환경에 없어서 ``windows_cat.pyw`` 자체는 못 돌린다.
그래서 설정 파일을 옛 위치(exe 옆)에서 새 위치(``%APPDATA%\\Memory Cat``)로
옮기는 판단만 여기 ``win_app.py`` 에 두고 테스트한다. ``windows_cat.pyw``
와의 배선은 소스를 정적으로 검사해서 확인한다(직접 실행은 안 된다).
"""
import ast
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_WINDOWS_DIR = str(_REPO / "windows")
if _WINDOWS_DIR not in sys.path:
    sys.path.insert(0, _WINDOWS_DIR)

import win_app  # noqa: E402


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

    def test_migrate_legacy_config_runs_inside_main_before_cat_is_built(self):
        main = self._main_function()
        self.assertIsNotNone(main, "main() 함수를 못 찾았습니다.")

        call_names = []
        for node in ast.walk(main):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    call_names.append(func.id)
                elif isinstance(func, ast.Attribute):
                    call_names.append(func.attr)

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


if __name__ == "__main__":
    unittest.main()
