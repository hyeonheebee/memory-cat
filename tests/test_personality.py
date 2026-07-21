import unittest

import personality


class PersonalityTests(unittest.TestCase):
    def test_exactly_three_presets_compile_to_distinct_prompts(self):
        stored_keys = (
            "냉소적 집사냥",
            "따뜻한 이모니냥",
            "무뚝뚝한 무사냥",
        )
        display_names = ("냉소적", "따뜻함", "무뚝뚝")
        self.assertEqual(personality.preset_names(), stored_keys)
        self.assertEqual(
            tuple(personality.preset_label(key) for key in stored_keys),
            display_names,
        )
        prompts = [personality.compile_personality(name) for name in stored_keys]
        self.assertEqual(len(set(prompts)), 3)
        for display_name, prompt in zip(display_names, prompts):
            self.assertIn(f"성격: {display_name}", prompt)
            self.assertIn("삭제 화이트리스트", prompt)

    def test_natural_language_selection_becomes_custom_personality(self):
        prompt = personality.compile_personality(
            "말끝에 냥을 붙이되 핵심부터 두 문장으로 말해줘"
        )
        self.assertIn("사용자 지정 뚱냥이", prompt)
        self.assertIn("말끝에 냥", prompt)
        self.assertIn("표현 방식에만 적용", prompt)

    def test_custom_selection_uses_separate_custom_text(self):
        prompt = personality.compile_personality(
            personality.CUSTOM_PERSONALITY,
            "  차분하게\n   숫자를 먼저 말해줘  ",
        )
        self.assertIn("차분하게 숫자를 먼저 말해줘", prompt)

    def test_empty_custom_falls_back_to_default(self):
        prompt = personality.compile_personality(
            personality.CUSTOM_PERSONALITY, "   "
        )
        self.assertIn(personality.preset_label(personality.DEFAULT_PERSONALITY), prompt)

    def test_custom_text_is_bounded_and_control_characters_removed(self):
        normalized = personality.normalize_custom_personality("냥\x00" + "가" * 500)
        self.assertNotIn("\x00", normalized)
        self.assertLessEqual(len(normalized), personality.MAX_CUSTOM_LENGTH)

    def test_malformed_config_falls_back_to_default(self):
        selection, custom = personality.config_personality(
            {"personality": {"unexpected": True}, "custom_personality": None}
        )
        self.assertEqual(selection, personality.DEFAULT_PERSONALITY)
        self.assertEqual(custom, "")

    def test_english_presets_keep_stable_config_keys_and_english_names(self):
        expected_labels = (
            "Sassy Butler Cat",
            "Warm Auntie Cat",
            "Stoic Samurai Cat",
        )
        labels = tuple(
            personality.preset_label(name, "en")
            for name in personality.preset_names()
        )
        self.assertEqual(labels, expected_labels)
        prompt = personality.compile_personality("냉소적 집사냥", language="en")
        self.assertIn("Sassy Butler Cat", prompt)
        self.assertIn("deletion allowlist", prompt)


if __name__ == "__main__":
    unittest.main()
