"""``windows/win_ai.py`` — 윈도우 진단의 Qt 없는 부분을 검사한다.

PySide6 는 맥 개발 환경에 없어서, 무엇을 보여줄지 정하는 로직을 Qt 밖으로
빼 두고 여기서 검사한다. ``win_ai`` 는 파일을 지우지 않는다는 것도 함께
확인한다.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_WINDOWS_DIR = str(Path(__file__).resolve().parent.parent / "windows")
if _WINDOWS_DIR not in sys.path:
    sys.path.insert(0, _WINDOWS_DIR)

import apppaths
import i18n
import win_ai


class DiagnosisLinesTests(unittest.TestCase):
    FAKE = {
        "why_slow": ["램이 거의 찼습니다.", "크롬이 4GB 를 쓰고 있어요."],
        "one_line_advice": "탭을 좀 닫아 보세요.",
        "cleanup_recommendations": [],
        "estimated_reclaimable_bytes": 0,
        "source": "openai",
    }

    def test_it_asks_for_a_diagnosis_without_cleanup(self):
        with patch.object(win_ai.brain, "diagnose", return_value=self.FAKE) as d:
            win_ai.diagnosis_lines("ko")
        self.assertEqual(d.call_args.kwargs["include_cleanup"], False)

    def test_the_explanation_and_the_advice_are_both_shown(self):
        with patch.object(win_ai.brain, "diagnose", return_value=self.FAKE):
            lines = win_ai.diagnosis_lines("ko")
        joined = "\n".join(lines)
        self.assertIn("램이 거의 찼습니다.", joined)
        self.assertIn("탭을 좀 닫아 보세요.", joined)

    def test_the_delete_warning_is_always_the_last_line(self):
        for language in ("ko", "en"):
            with self.subTest(language=language), \
                 patch.object(win_ai.brain, "diagnose", return_value=self.FAKE):
                lines = win_ai.diagnosis_lines(language)
            self.assertEqual(lines[-1], i18n.tr(language, "windows_delete_warning"))

    def test_it_never_reaches_the_file_deleting_code(self):
        """윈도우판은 지우지 않는다. 정리 코드에 발도 들이면 안 된다."""
        with patch.object(win_ai.brain, "collect_cleanup_candidates") as scan, \
             patch.object(win_ai.brain, "safe_trash") as trash, \
             patch.object(win_ai.brain, "_load_api_key", return_value=None):
            win_ai.diagnosis_lines("ko")
        scan.assert_not_called()
        trash.assert_not_called()


class DiagnosisSourceNoticeTests(unittest.TestCase):
    """API 오류로 규칙 기반 결과가 나오면, 진단창이 AI 진단인 척하면 안 된다.

    맥판(``desktop_cat.diagnosis_result_content``)이 하는 것과 같은 매핑을
    쓴다 — ``fallback_reason`` 이 없거나 모르는 값이면 ``fallback_unknown``.
    """

    FAKE_OPENAI = {
        "why_slow": ["램이 거의 찼습니다."],
        "one_line_advice": "탭을 좀 닫아 보세요.",
        "cleanup_recommendations": [],
        "estimated_reclaimable_bytes": 0,
        "source": "openai",
    }

    def _fallback(self, reason):
        return {
            "why_slow": ["램이 거의 찼습니다."],
            "one_line_advice": "탭을 좀 닫아 보세요.",
            "cleanup_recommendations": [],
            "estimated_reclaimable_bytes": 0,
            "source": "fallback",
            "fallback_reason": reason,
        }

    def test_fallback_api_error_shows_the_reason_first(self):
        for language in ("ko", "en"):
            with self.subTest(language=language), \
                 patch.object(win_ai.brain, "diagnose",
                              return_value=self._fallback("api_error")):
                lines = win_ai.diagnosis_lines(language)
            reason = i18n.tr(language, "fallback_api_error")
            notice = i18n.tr(
                language, "diagnosis_source_fallback", reason=reason)
            self.assertEqual(lines[0], notice)

    def test_fallback_missing_api_key_maps_to_its_own_reason(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self._fallback("missing_api_key")):
            lines = win_ai.diagnosis_lines("ko")
        reason = i18n.tr("ko", "fallback_missing_api_key")
        notice = i18n.tr("ko", "diagnosis_source_fallback", reason=reason)
        self.assertEqual(lines[0], notice)

    def test_unknown_fallback_reason_falls_back_to_the_unknown_string(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self._fallback("something_new")):
            lines = win_ai.diagnosis_lines("ko")
        reason = i18n.tr("ko", "fallback_unknown")
        notice = i18n.tr("ko", "diagnosis_source_fallback", reason=reason)
        self.assertEqual(lines[0], notice)

    def test_openai_source_has_no_fallback_notice(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self.FAKE_OPENAI):
            lines = win_ai.diagnosis_lines("ko")
        self.assertEqual(lines[0], self.FAKE_OPENAI["why_slow"][0])

    def test_the_delete_warning_is_last_even_with_a_fallback_notice(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self._fallback("api_error")):
            lines = win_ai.diagnosis_lines("ko")
        self.assertEqual(lines[-1], i18n.tr("ko", "windows_delete_warning"))


class HasApiKeyTests(unittest.TestCase):
    def test_true_when_a_key_is_loaded(self):
        with patch.object(win_ai.brain, "_load_api_key", return_value="sk-abc"):
            self.assertTrue(win_ai.has_api_key())

    def test_false_when_no_key_is_loaded(self):
        with patch.object(win_ai.brain, "_load_api_key", return_value=None):
            self.assertFalse(win_ai.has_api_key())


class ApiKeyMessageTests(unittest.TestCase):
    def test_the_message_names_the_env_file(self):
        for language in ("ko", "en"):
            with self.subTest(language=language):
                title, body = win_ai.api_key_missing_message(language)
                self.assertTrue(title.strip())
                self.assertIn(".env", body)


class PhotoCheckTests(unittest.TestCase):
    def test_heic_is_refused_with_a_clear_message(self):
        """맥은 OS 해독기로 HEIC 를 열지만 윈도우는 못 연다.
        아이폰 사진이 기본 HEIC 라 그냥 실패하면 사용자가 이유를 모른다."""
        message = win_ai.check_photo(Path("cat.heic"))
        self.assertIsNotNone(message)
        self.assertIn("PNG", message)

    def test_png_jpeg_webp_pass(self):
        for name in ("cat.png", "cat.jpg", "cat.jpeg", "cat.webp"):
            with self.subTest(name=name):
                self.assertIsNone(win_ai.check_photo(Path(name)))


class ThemeTargetTests(unittest.TestCase):
    def test_new_themes_go_to_user_data_not_next_to_the_exe(self):
        """exe 옆에 쓰면 Program Files 에 깔렸을 때 권한이 없어 실패한다."""
        self.assertEqual(win_ai.theme_target_dir(), apppaths.user_frames_dir())


class NextThemeNameTests(unittest.TestCase):
    """맥의 ``desktop_cat.next_pet_theme_name`` 과 같은 규칙.

    번들 폴더와 사용자 폴더(``MEMORY_CAT_HOME`` 으로 옮긴다) 를 모두 비운
    임시 폴더로 갈아 끼워서, 실제 사용자 데이터를 건드리지 않고 검사한다.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.bundled_dir = Path(self._tmp.name) / "bundled_frames"
        self.home_dir = Path(self._tmp.name) / "home"
        self._env_patch = patch.dict(
            os.environ, {apppaths.HOME_ENV: str(self.home_dir)}
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    def test_both_empty_gives_mypet(self):
        self.bundled_dir.mkdir(parents=True)
        (win_ai.theme_target_dir()).mkdir(parents=True)
        self.assertEqual(win_ai.next_theme_name(self.bundled_dir), "mypet")

    def test_mypet_taken_in_user_folder_gives_mypet2(self):
        self.bundled_dir.mkdir(parents=True)
        user_dir = win_ai.theme_target_dir()
        (user_dir / "mypet").mkdir(parents=True)
        self.assertEqual(win_ai.next_theme_name(self.bundled_dir), "mypet2")

    def test_mypet2_in_bundled_and_mypet_in_user_gives_mypet3(self):
        (self.bundled_dir / "mypet2").mkdir(parents=True)
        user_dir = win_ai.theme_target_dir()
        (user_dir / "mypet").mkdir(parents=True)
        self.assertEqual(win_ai.next_theme_name(self.bundled_dir), "mypet3")

    def test_missing_folders_still_give_mypet(self):
        """폴더 자체가 없어도 예외 없이 첫 이름을 돌려준다."""
        self.assertEqual(win_ai.next_theme_name(self.bundled_dir), "mypet")


class CreateThemeTests(unittest.TestCase):
    def test_heic_is_blocked_before_calling_build_theme(self):
        with patch.object(win_ai.vision_theme, "build_theme") as build:
            with self.assertRaises(win_ai.ThemeError):
                win_ai.create_theme(Path("cat.heic"), "mypet")
        build.assert_not_called()

    def test_build_theme_errors_are_wrapped_with_the_cause_preserved(self):
        original = RuntimeError("네트워크 오류")
        with patch.object(win_ai.vision_theme, "build_theme", side_effect=original):
            with self.assertRaises(win_ai.ThemeError) as ctx:
                win_ai.create_theme(Path("cat.png"), "mypet")
        self.assertIs(ctx.exception.__cause__, original)

    def test_success_calls_build_theme_and_returns_the_name(self):
        with patch.object(
            win_ai.vision_theme, "build_theme", return_value={"detected_stages": 6}
        ) as build:
            result = win_ai.create_theme(Path("cat.png"), "mypet")
        build.assert_called_once_with(Path("cat.png"), "mypet", quality="medium")
        self.assertEqual(result, "mypet")


if __name__ == "__main__":
    unittest.main()
