"""`.app` 번들 조립과 LaunchAgent plist 생성에 대한 회귀 테스트.

여기서 지키려는 것 두 가지.

1. plist 를 문자열로 조립하지 않는다. 경로에 ``&``/``<``/``>`` 가 있어도
   깨지지 않아야 한다. (예전 히어독 방식은 `Memory & Cat` 폴더에서
   "Encountered unknown ampersand-escape sequence" 로 죽었다.)
2. 사용자가 만든 테마는 번들로 옮겨가는 과정에서 사라지지 않는다.
3. ``CFBundleIconFile`` 이 가리키는 파일이 번들 안에 실제로 있다. 그리고
   커밋된 ``.icns`` 가 필요한 크기를 다 담고 있다 — 아이콘은 화면으로만
   확인되는 물건이라 회귀가 조용히 지나가기 쉽다.
"""

import importlib.util
import os
import plistlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import apppaths

_BUILD_APP = Path(__file__).resolve().parent.parent / "macos" / "build_app.py"
_spec = importlib.util.spec_from_file_location("build_app", _BUILD_APP)
build_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_app)

_REPO = Path(__file__).resolve().parent.parent

# XML 로 그냥 끼워 넣으면 반드시 깨지는 문자들.
NASTY = 'Memory & Cat <v1> "quoted"'

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: icns 청크 타입 → 그 칸이 담당하는 (논리 크기 pt, 배율).
#: 애플의 `iconutil` 은 16pt·32pt 1x 를 PNG 가 아니라 ARGB 로 넣는다
#: (``ic04``/``ic05``). Pillow 의 ICNS 저장은 이 두 칸을 아예 만들지 않아서
#: 저해상도 화면의 Finder 목록 보기에서 큰 칸을 줄여 쓰게 된다.
ICNS_SLOTS = {
    b"ic04": (16, 1), b"ic05": (32, 1),
    b"ic11": (16, 2), b"ic12": (32, 2),
    b"ic07": (128, 1), b"ic13": (128, 2),
    b"ic08": (256, 1), b"ic14": (256, 2),
    b"ic09": (512, 1), b"ic10": (512, 2),
}


def parse_icns(blob):
    """``.icns`` 를 표준 라이브러리만으로 뜯는다.

    Pillow 로 읽지 않는 이유: Pillow 의 ICNS 리더는 PNG 청크만 세고
    ``ic04``/``ic05``(ARGB)를 무시한다. 그러면 "16pt 칸이 있는가" 를
    검사하려는 이 테스트가 항상 실패한다. 포맷 자체는 단순해서 직접 읽는 게
    낫다 — 헤더 8바이트 뒤로 ``(4바이트 타입, 4바이트 길이, 본문)`` 반복.
    """
    if blob[:4] != b"icns":
        raise ValueError("icns 매직이 아닙니다")
    declared = struct.unpack(">I", blob[4:8])[0]
    chunks = {}
    offset = 8
    while offset + 8 <= len(blob):
        code, size = struct.unpack(">4sI", blob[offset:offset + 8])
        if size < 8 or offset + size > len(blob):
            raise ValueError(f"청크 길이가 이상합니다: {code!r} size={size}")
        body = blob[offset + 8:offset + size]
        pixels = None
        if body[:8] == PNG_MAGIC:
            pixels = struct.unpack(">II", body[16:24])
        chunks[code] = pixels
        offset += size
    return declared, chunks


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

    def test_points_at_the_icon_by_default(self):
        info = build_app.info_plist()
        self.assertEqual(info["CFBundleIconFile"], build_app.ICON_FILE)
        # 에셋 카탈로그가 없으므로 CFBundleIconName 은 쓰지 않는다.
        self.assertNotIn("CFBundleIconName", info)

    def test_icon_key_is_dropped_when_there_is_no_icon(self):
        # 없는 파일을 가리키는 키를 남기면 Launch Services 가 깨진 아이콘을
        # 캐시한다. 키가 아예 없는 편이 낫다.
        info = build_app.info_plist(icon=None)
        self.assertNotIn("CFBundleIconFile", info)


class CommittedIconTests(unittest.TestCase):
    """저장소에 커밋된 ``macos/MemoryCat.icns`` 자체를 검사한다.

    아이콘은 눈으로만 확인되는 물건이라 조용히 망가지기 쉽다. 스프라이트를
    바꾸고 ``make_icon.command`` 돌리는 걸 잊거나, 도구가 칸을 빠뜨리거나,
    파일이 잘려서 커밋되거나. 여기서 형식과 내용물을 둘 다 못 박아 둔다.
    """

    def setUp(self):
        self.path = _REPO.joinpath(*build_app.ICON_SOURCE)
        if not self.path.is_file():
            self.skipTest(f"커밋된 아이콘이 없습니다: {self.path}")
        self.blob = self.path.read_bytes()

    def test_header_length_matches_the_file(self):
        declared, _ = parse_icns(self.blob)
        # 잘린 채 커밋되면 여기서 잡힌다.
        self.assertEqual(declared, len(self.blob))

    def test_carries_every_size_macos_asks_for(self):
        _, chunks = parse_icns(self.blob)
        found = {ICNS_SLOTS[code] for code in chunks if code in ICNS_SLOTS}
        expected = {(pt, scale) for pt in (16, 32, 128, 256, 512)
                    for scale in (1, 2)}
        self.assertEqual(
            found, expected,
            f"빠진 칸: {sorted(expected - found)} / 남는 칸: {sorted(found - expected)}",
        )

    def test_png_chunks_hold_the_pixels_their_slot_promises(self):
        _, chunks = parse_icns(self.blob)
        for code, pixels in chunks.items():
            if code not in ICNS_SLOTS or pixels is None:
                continue  # TOC/info/ARGB 칸은 픽셀을 읽지 않는다
            pt, scale = ICNS_SLOTS[code]
            self.assertEqual(
                pixels, (pt * scale, pt * scale),
                f"{code.decode()} 는 {pt * scale}px 여야 하는데 {pixels} 입니다",
            )

    def test_the_biggest_slot_is_actually_1024(self):
        # 512pt @2x. 이게 없으면 Finder 의 가장 큰 보기에서 흐릿해진다.
        _, chunks = parse_icns(self.blob)
        self.assertEqual(chunks.get(b"ic10"), (1024, 1024))


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
        icon = source.joinpath(*build_app.ICON_SOURCE)
        icon.parent.mkdir(parents=True, exist_ok=True)
        icon.write_bytes(b"icns\x00\x00\x00\x08")
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

    def test_icon_lands_where_the_plist_says_it_does(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._fake_source(root)
            interpreter = root / "FakePython"
            interpreter.write_bytes(b"\xcf\xfa\xed\xfe")
            app = root / NASTY / "Memory Cat.app"

            result = build_app.assemble(source, app, interpreter=interpreter)

            with open(app / "Contents" / "Info.plist", "rb") as handle:
                info = plistlib.load(handle)
            # plist 값을 그대로 파일 이름으로 붙여 찾을 수 있어야 한다.
            # 여기서 한 번 꼬이면 Finder 는 조용히 기본 아이콘을 보여 준다.
            referenced = app / "Contents" / "Resources" / info["CFBundleIconFile"]
            self.assertTrue(referenced.is_file(), referenced)
            self.assertEqual(referenced.read_bytes()[:4], b"icns")
            self.assertEqual(result["icon"], build_app.ICON_FILE)
            self.assertEqual(result["warnings"], [])

    def test_missing_icon_warns_instead_of_leaving_a_dangling_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._fake_source(root)
            source.joinpath(*build_app.ICON_SOURCE).unlink()
            interpreter = root / "FakePython"
            interpreter.write_bytes(b"\xcf\xfa\xed\xfe")
            app = root / "Memory Cat.app"

            result = build_app.assemble(source, app, interpreter=interpreter)

            # 아이콘이 없다고 설치가 실패하면 안 된다. 장식이니까.
            with open(app / "Contents" / "Info.plist", "rb") as handle:
                info = plistlib.load(handle)
            self.assertNotIn("CFBundleIconFile", info)
            self.assertIsNone(result["icon"])
            self.assertTrue(any("아이콘" in w for w in result["warnings"]))

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
