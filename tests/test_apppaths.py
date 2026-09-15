import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import apppaths


class UserDataDirTests(unittest.TestCase):
    def setUp(self):
        # MEMORY_CAT_HOME 이 걸려 있으면 플랫폼 분기를 건너뛴다
        self._saved = os.environ.pop(apppaths.HOME_ENV, None)

    def tearDown(self):
        if self._saved is not None:
            os.environ[apppaths.HOME_ENV] = self._saved

    def test_windows_uses_appdata(self):
        with patch.object(apppaths.sys, "platform", "win32"), \
             patch.dict(os.environ, {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            self.assertEqual(
                apppaths.user_data_dir(),
                Path(r"C:\Users\me\AppData\Roaming") / apppaths.APP_NAME)

    def test_windows_without_appdata_falls_back_to_home(self):
        """APPDATA 는 보통 있지만, 없다고 앱이 죽으면 안 된다."""
        with patch.object(apppaths.sys, "platform", "win32"), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPDATA", None)
            self.assertEqual(
                apppaths.user_data_dir(),
                Path.home() / "AppData" / "Roaming" / apppaths.APP_NAME)

    def test_mac_is_unchanged(self):
        with patch.object(apppaths.sys, "platform", "darwin"):
            self.assertEqual(
                apppaths.user_data_dir(),
                Path.home() / "Library" / "Application Support" / apppaths.APP_NAME)

    def test_the_override_still_wins_on_both(self):
        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform), \
                 patch.object(apppaths.sys, "platform", platform), \
                 patch.dict(os.environ, {apppaths.HOME_ENV: "/tmp/cat-home"}):
                self.assertEqual(apppaths.user_data_dir(), Path("/tmp/cat-home"))

    def test_windows_log_dir_sits_under_user_data(self):
        with patch.object(apppaths.sys, "platform", "win32"), \
             patch.dict(os.environ, {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            self.assertEqual(apppaths.log_dir(),
                             apppaths.user_data_dir() / "Logs")


class DotenvEncodingTests(unittest.TestCase):
    """메모장이 저장하는 세 가지 인코딩을 앞 몇 바이트로 구분한다.

    값을 실제로 읽지는 않으므로 진짜 키는 등장하지 않는다 — 파일 내용은
    형태만 흉내 낸 가짜 한 줄이다.
    """

    _LINE = "OPENAI_API_KEY=sk-test-fake-encoding\n"

    def test_utf8_without_bom_reads_as_utf8_sig(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_bytes(self._LINE.encode("utf-8"))
            self.assertEqual(apppaths.dotenv_encoding(path), "utf-8-sig")

    def test_utf8_with_bom_reads_as_utf8_sig(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_bytes(b"\xef\xbb\xbf" + self._LINE.encode("utf-8"))
            self.assertEqual(apppaths.dotenv_encoding(path), "utf-8-sig")

    def test_utf16_with_bom_reads_as_utf16(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            # 메모장 "유니코드" 저장은 파이썬 기본 "utf-16" 인코딩과 같은
            # 바이트 순서(BOM 포함)를 만든다.
            path.write_bytes(self._LINE.encode("utf-16"))
            self.assertEqual(apppaths.dotenv_encoding(path), "utf-16")

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "does-not-exist" / ".env"
            self.assertIsNone(apppaths.dotenv_encoding(path))
