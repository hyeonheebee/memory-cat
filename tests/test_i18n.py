import unittest

import i18n


class I18nTests(unittest.TestCase):
    def test_system_language_is_korean_only_for_korean_primary_language(self):
        self.assertEqual(i18n.detect_system_language(["ko-KR", "en-US"]), "ko")
        self.assertEqual(i18n.detect_system_language(["en-US", "ko-KR"]), "en")
        self.assertEqual(i18n.detect_system_language(["ja-JP"]), "en")

    def test_manual_override_wins_over_system_language(self):
        self.assertEqual(i18n.resolve_language("en", ["ko-KR"]), "en")
        self.assertEqual(i18n.resolve_language("ko", ["en-US"]), "ko")
        self.assertEqual(i18n.resolve_language("auto", ["ko-KR"]), "ko")

    def test_english_chonk_chart_uses_all_six_exact_stage_names(self):
        stages = [i18n.chonk_stage(value, "en") for value in (50, 65, 75, 85, 92, 99)]
        self.assertEqual(tuple(stages), i18n.CHONK_STAGES_EN)

    def test_korean_growth_stages_are_unchanged(self):
        self.assertEqual(
            [i18n.chonk_stage(value, "ko") for value in (50, 70, 85, 95)],
            ["여유 😺", "포동 🐈", "배불러 🍙", "빵빵! 🐷"],
        )

    def test_translation_can_format_a_language_placeholder(self):
        self.assertEqual(
            i18n.tr("ko", "language_auto", language="한국어"),
            "자동 (한국어)",
        )

    def test_diagnosis_menu_uses_friendly_cat_wording_in_both_languages(self):
        expected = {
            "ko": ("🐾 배불러?", "🐾 살펴보는 중…", "🐾 다시 살펴보기", "📋 마지막 진단 보기"),
            "en": ("🐾 Feeling full?", "🐾 Checking…", "🐾 Check again", "📋 View last diagnosis"),
        }
        for language, labels in expected.items():
            with self.subTest(language=language):
                self.assertEqual(
                    (
                        i18n.tr(language, "menu_diagnose"),
                        i18n.tr(language, "menu_diagnosing"),
                        i18n.tr(language, "menu_diagnose_again"),
                        i18n.tr(language, "menu_last_diagnosis"),
                    ),
                    labels,
                )


if __name__ == "__main__":
    unittest.main()
