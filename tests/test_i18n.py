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

    def test_pet_theme_menu_and_consent_are_localized(self):
        expected = {
            "ko": (
                "내 반려동물로 테마 만들기…",
                "테마 만드는 중…",
                "선택한 사진이 테마 생성을 위해 OpenAI로 전송됩니다",
            ),
            "en": (
                "Make a theme from my pet…",
                "Making theme…",
                "Your photo will be sent to OpenAI to generate the theme",
            ),
        }
        for language, labels in expected.items():
            with self.subTest(language=language):
                self.assertEqual(
                    (
                        i18n.tr(language, "menu_pet_theme"),
                        i18n.tr(language, "menu_pet_theme_running"),
                        i18n.tr(language, "pet_theme_consent_body"),
                    ),
                    labels,
                )

    def test_disk_full_prompt_is_friendly_in_both_languages(self):
        self.assertEqual(
            i18n.tr("ko", "disk_full_prompt_body"),
            "배불러… 진단해볼까?",
        )
        self.assertEqual(
            i18n.tr("en", "disk_full_prompt_body"),
            "I'm so full… want a checkup?",
        )


if __name__ == "__main__":
    unittest.main()
