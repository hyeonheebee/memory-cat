import os
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
