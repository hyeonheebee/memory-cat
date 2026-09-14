"""``windows/win_ai.py`` — 윈도우 진단의 Qt 없는 부분을 검사한다.

PySide6 는 맥 개발 환경에 없어서, 무엇을 보여줄지 정하는 로직을 Qt 밖으로
빼 두고 여기서 검사한다. ``win_ai`` 는 파일을 지우지 않는다는 것도 함께
확인한다.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "windows"))

import i18n
import win_ai


class DiagnosisLinesTests(unittest.TestCase):
    FAKE = {
        "why_slow": ["램이 거의 찼습니다.", "크롬이 4GB 를 쓰고 있어요."],
        "one_line_advice": "탭을 좀 닫아 보세요.",
        "recommendations": [],
        "estimated_bytes": 0,
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


class ApiKeyMessageTests(unittest.TestCase):
    def test_the_message_names_the_env_file(self):
        for language in ("ko", "en"):
            with self.subTest(language=language):
                title, body = win_ai.api_key_missing_message(language)
                self.assertTrue(title.strip())
                self.assertIn(".env", body)


if __name__ == "__main__":
    unittest.main()
