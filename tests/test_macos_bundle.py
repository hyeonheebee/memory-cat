"""`.app` 번들 조립과 LaunchAgent plist 생성에 대한 회귀 테스트.

여기서 지키려는 것 두 가지.

1. plist 를 문자열로 조립하지 않는다. 경로에 ``&``/``<``/``>`` 가 있어도
   깨지지 않아야 한다. (예전 히어독 방식은 `Memory & Cat` 폴더에서
   "Encountered unknown ampersand-escape sequence" 로 죽었다.)
2. 사용자가 만든 테마는 번들로 옮겨가는 과정에서 사라지지 않는다.
"""

import importlib.util
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import apppaths

_BUILD_APP = Path(__file__).resolve().parent.parent / "macos" / "build_app.py"
_spec = importlib.util.spec_from_file_location("build_app", _BUILD_APP)
build_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_app)

# XML 로 그냥 끼워 넣으면 반드시 깨지는 문자들.
NASTY = 'Memory & Cat <v1> "quoted"'


class LaunchAgentPlistTests(unittest.TestCase):
    def test_special_characters_in_paths_round_trip(self):
        app = Path("/Users/me") / NASTY / "Memory Cat.app"
        log = Path("/Users/me") / NASTY / "cat.log"
        payload = build_app.launch_agent_plist(
            app / "Contents" / "MacOS" / "MemoryCat", log, Path("/Users/me") / NASTY
        )

        # plistlib 으로 쓰고 다시 읽었을 때 원래 경로 그대로여야 한다.
        blob = plistlib.dumps(payload)
        parsed = plistlib.loads(blob)

        self.assertEqual(
            parsed["ProgramArguments"][0],
            str(app / "Contents" / "MacOS" / "MemoryCat"),
        )
        self.assertEqual(parsed["StandardOutPath"], str(log))
        self.assertEqual(parsed["StandardErrorPath"], str(log))
        self.assertEqual(parsed["WorkingDirectory"], str(Path("/Users/me") / NASTY))
        # 원문 '&' 가 그대로 새어 나가면 XML 이 깨진 것이다.
        self.assertIn(b"&amp;", blob)
        self.assertNotIn(b"Cat & ", blob)

    def test_label_matches_bundle_identifier(self):
        payload = build_app.launch_agent_plist(
            Path("/a/MemoryCat"), Path("/a/cat.log"), Path("/a")
        )
        self.assertEqual(payload["Label"], apppaths.BUNDLE_ID)

    def test_keep_alive_only_restarts_after_abnormal_exit(self):
        payload = build_app.launch_agent_plist(
            Path("/a/MemoryCat"), Path("/a/cat.log"), Path("/a")
        )
        # 사용자가 메뉴에서 종료하면(정상 종료) 되살아나면 안 된다.
        self.assertEqual(payload["KeepAlive"], {"SuccessfulExit": False})
        # 크래시 루프가 CPU 를 태우지 않게 간격을 둔다.
        self.assertGreaterEqual(payload["ThrottleInterval"], 10)

    def test_written_plist_parses_from_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / NASTY
            plist_path = root / "com.memorycat.desktop.plist"
            build_app.write_launch_agent(
                root / "Memory Cat.app", plist_path, root / "cat.log", root
            )
            with open(plist_path, "rb") as handle:
                parsed = plistlib.load(handle)
            self.assertTrue(
                parsed["ProgramArguments"][0].endswith(
                    "Memory Cat.app/Contents/MacOS/MemoryCat"
                )
            )


class InfoPlistTests(unittest.TestCase):
    def test_carries_identity_and_accessory_flag(self):
        info = build_app.info_plist()
        self.assertEqual(info["CFBundleIdentifier"], apppaths.BUNDLE_ID)
        self.assertEqual(info["CFBundleName"], apppaths.APP_NAME)
        self.assertEqual(info["CFBundleExecutable"], build_app.EXECUTABLE_NAME)
        self.assertEqual(info["CFBundlePackageType"], "APPL")
        # 앱이 NSApplicationActivationPolicyAccessory 를 쓴다. 번들도 같은 말을
        # 해야 Dock 아이콘이 잠깐 튀어나오지 않는다.
        self.assertIs(info["LSUIElement"], True)

    def test_round_trips_through_plistlib(self):
        parsed = plistlib.loads(plistlib.dumps(build_app.info_plist()))
        self.assertEqual(parsed["CFBundleIdentifier"], apppaths.BUNDLE_ID)


class LauncherScriptTests(unittest.TestCase):
    def test_no_placeholder_survives(self):
        script = build_app.launcher_script()
        self.assertNotIn("@@", script)
        self.assertIn(build_app.INTERPRETER_NAME, script)
        self.assertIn(build_app.PYTHON_HOME_FILE, script)

    def test_resolves_paths_from_its_own_location(self):
        # 설치 경로를 스크립트에 박아 넣으면 번들을 옮기는 순간 깨진다.
        script = build_app.launcher_script()
        self.assertIn('HERE="$(cd "$(dirname "$0")" && pwd)"', script)
        self.assertNotIn("/Users/", script)
        self.assertNotIn("$HOME", script)


class MigrationTests(unittest.TestCase):
    def _make_theme(self, root: Path, name: str) -> Path:
        theme = root / "frames" / name
        theme.mkdir(parents=True)
        (theme / "cat_00.png").write_bytes(b"png")
        return theme

    def test_custom_theme_is_copied_and_original_left_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "repo"
            source.mkdir()
            self._make_theme(source, "mypet3")
            self._make_theme(source, "cute")
            home = Path(temp) / "support"

            moved = build_app.migrate_user_data(source, home)

            self.assertEqual(moved["themes"], ["mypet3"])
            self.assertTrue((home / "frames" / "mypet3" / "cat_00.png").is_file())
            # 기본 테마는 번들에서 오므로 사용자 폴더로 옮기지 않는다.
            self.assertFalse((home / "frames" / "cute").exists())
            # 원본은 손대지 않는다. 이전이 실패해도 잃는 게 없어야 한다.
            self.assertTrue((source / "frames" / "mypet3" / "cat_00.png").is_file())

    def test_config_and_dotenv_move_but_never_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "repo"
            source.mkdir()
            (source / "config.json").write_text('{"theme": "mypet3"}', encoding="utf-8")
            (source / ".env").write_text("OPENAI_API_KEY=old\n", encoding="utf-8")
            home = Path(temp) / "support"
            home.mkdir()
            (home / ".env").write_text("OPENAI_API_KEY=already-here\n", encoding="utf-8")

            moved = build_app.migrate_user_data(source, home)

            self.assertTrue(moved["config"])
            self.assertFalse(moved["dotenv"])
            self.assertEqual(
                (home / "config.json").read_text(encoding="utf-8"),
                '{"theme": "mypet3"}',
            )
            self.assertEqual(
                (home / ".env").read_text(encoding="utf-8"),
                "OPENAI_API_KEY=already-here\n",
            )

    def test_existing_user_theme_is_never_clobbered(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "repo"
            source.mkdir()
            self._make_theme(source, "mypet3")
            home = Path(temp) / "support"
            keep = home / "frames" / "mypet3"
            keep.mkdir(parents=True)
            (keep / "cat_00.png").write_bytes(b"newer")

            moved = build_app.migrate_user_data(source, home)

            self.assertEqual(moved["themes"], [])
            self.assertEqual((keep / "cat_00.png").read_bytes(), b"newer")

    def test_symlinked_theme_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "repo"
            (source / "frames").mkdir(parents=True)
            outside = Path(temp) / "outside"
            outside.mkdir()
            (outside / "cat_00.png").write_bytes(b"png")
            os.symlink(outside, source / "frames" / "sneaky")
            home = Path(temp) / "support"

            moved = build_app.migrate_user_data(source, home)

            self.assertEqual(moved["themes"], [])


class AssembleTests(unittest.TestCase):
    def _fake_source(self, root: Path) -> Path:
        source = root / "repo"
        source.mkdir()
        for name in build_app.APP_MODULES:
            (source / name).write_text("# stub\n", encoding="utf-8")
        for theme in apppaths.BUNDLED_THEMES:
            theme_dir = source / "frames" / theme
            theme_dir.mkdir(parents=True)
            (theme_dir / "cat_00.png").write_bytes(b"png")
        (source / "uninstall_mac.command").write_text("#!/bin/bash\n", encoding="utf-8")
        return source

    def test_layout_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._fake_source(root)
            interpreter = root / "FakePython"
            interpreter.write_bytes(b"\xcf\xfa\xed\xfe")
            app = root / NASTY / "Memory Cat.app"

            build_app.assemble(source, app, interpreter=interpreter)

            contents = app / "Contents"
            launcher = contents / "MacOS" / build_app.EXECUTABLE_NAME
            copied = contents / "MacOS" / build_app.INTERPRETER_NAME
            self.assertTrue(launcher.is_file())
            self.assertTrue(os.access(launcher, os.X_OK))
            # 인터프리터가 번들 안에 있어야 CoreFoundation 이 우리 Info.plist 를
            # 메인 번들로 잡는다. 없으면 알림이 "Python" 이름으로 나간다.
            self.assertTrue(copied.is_file())
            self.assertTrue(os.access(copied, os.X_OK))

            with open(contents / "Info.plist", "rb") as handle:
                info = plistlib.load(handle)
            self.assertEqual(info["CFBundleIdentifier"], apppaths.BUNDLE_ID)

            resources = contents / "Resources"
            for name in build_app.APP_MODULES:
                self.assertTrue((resources / name).is_file(), name)
            for theme in apppaths.BUNDLED_THEMES:
                self.assertTrue((resources / "frames" / theme / "cat_00.png").is_file())
            # 저장소가 사라져도 제거할 수 있게 언인스톨러를 함께 넣는다.
            uninstaller = resources / "uninstall_mac.command"
            self.assertTrue(uninstaller.is_file())
            self.assertTrue(os.access(uninstaller, os.X_OK))

    def test_missing_default_theme_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._fake_source(root)
            import shutil

            shutil.rmtree(source / "frames" / "derpy")
            interpreter = root / "FakePython"
            interpreter.write_bytes(b"\xcf\xfa\xed\xfe")

            with self.assertRaises(build_app.BuildError):
                build_app.assemble(source, root / "app.app", interpreter=interpreter)

    def test_framework_interpreter_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(build_app.framework_interpreter(temp))

    def test_framework_interpreter_finds_python_app(self):
        with tempfile.TemporaryDirectory() as temp:
            target = (
                Path(temp) / "Resources" / "Python.app" / "Contents" / "MacOS"
            )
            target.mkdir(parents=True)
            (target / "Python").write_bytes(b"\xcf\xfa\xed\xfe")
            self.assertEqual(
                build_app.framework_interpreter(temp), target / "Python"
            )


class AppPathsTests(unittest.TestCase):
    def test_home_override_moves_every_user_path(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {apppaths.HOME_ENV: temp}, clear=False):
                self.assertEqual(apppaths.user_data_dir(), Path(temp))
                self.assertEqual(apppaths.user_frames_dir(), Path(temp) / "frames")
                self.assertEqual(apppaths.config_file(), Path(temp) / "config.json")

    def test_user_theme_wins_over_bundled_theme_of_the_same_name(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "support"
            (user / "frames" / "cute").mkdir(parents=True)
            with patch.dict(os.environ, {apppaths.HOME_ENV: str(user)}, clear=False):
                self.assertEqual(
                    apppaths.theme_dir("cute"), user / "frames" / "cute"
                )

    def test_unknown_theme_falls_back_to_the_user_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {apppaths.HOME_ENV: temp}, clear=False):
                self.assertEqual(
                    apppaths.theme_dir("nope"), Path(temp) / "frames" / "nope"
                )

    def test_dotenv_is_looked_up_in_user_data_first(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {apppaths.HOME_ENV: temp}, clear=False):
                candidates = apppaths.dotenv_candidates()
            self.assertEqual(candidates[0], Path(temp) / ".env")
            self.assertEqual(candidates[1], apppaths.source_dir() / ".env")


if __name__ == "__main__":
    unittest.main()
