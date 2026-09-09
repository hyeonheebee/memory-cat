import ast
import pathlib
import string
import unittest

import i18n

_REPO = pathlib.Path(__file__).resolve().parent.parent


class FormatArgumentTests(unittest.TestCase):
    """``tr()`` 을 부르는 모든 곳이 그 문구가 요구하는 인자를 다 넘기는지 본다.

    v0.3.0 에서 공용 문구 ``mood_detail`` 에 ``{source}`` 를 더했는데 맥판만
    고치고 윈도우판(`windows/windows_cat.pyw`)을 놓쳤다. 윈도우의 갱신 루프는
    한 틱이 실패해도 삼키도록 되어 있어서, 앱은 멀쩡히 도는데 우클릭 정보창만
    통째로 비었다. 에러도 안 뜨고 기존 검사도 못 잡았다 — 그 검사는 "키가 두
    언어에 다 있는가" 만 봤기 때문이다.

    문구를 mac/win 이 함께 쓰므로 한쪽만 고치는 실수가 다시 나기 쉽다.
    """

    #: 검사할 소스. 윈도우판은 PySide6 가 없어 import 할 수 없으므로 글로 읽는다.
    SOURCES = (
        "desktop_cat.py",
        "windows/windows_cat.pyw",
        "brain.py",
        "personality.py",
        "vision_theme.py",
        "import_theme.py",
    )

    @staticmethod
    def _placeholders(template):
        """``"{a} {b:.0f}"`` → ``{"a", "b"}``. 형식 지정자는 떼어낸다."""
        return {
            name.split(".")[0].split("[")[0]
            for _, name, _, _ in string.Formatter().parse(template)
            if name
        }

    def _tr_calls(self, path):
        """``tr(language, "키", ...)`` 중 키가 상수인 것만. 동적 키는 못 본다."""
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "tr"):
                continue
            if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
                continue
            if isinstance(node.args[1].value, str):
                yield node

    def test_every_call_passes_the_arguments_its_string_needs(self):
        missing = []
        checked = 0
        for name in self.SOURCES:
            path = _REPO / name
            if not path.is_file():
                continue
            for node in self._tr_calls(path):
                key = node.args[1].value
                given = {kw.arg for kw in node.keywords if kw.arg}
                for language in ("ko", "en"):
                    template = i18n._STRINGS[language].get(key)
                    if template is None:
                        continue
                    checked += 1
                    lack = self._placeholders(template) - given
                    if lack:
                        missing.append(
                            f"{name}:{node.lineno} tr(..., {key!r}) 에 "
                            f"{sorted(lack)} 가 빠졌습니다 [{language}]"
                        )
        self.assertGreater(checked, 0, "tr() 호출을 하나도 못 찾았습니다")
        self.assertEqual(missing, [], "\n" + "\n".join(missing))

    def test_every_literal_key_exists(self):
        """없는 키를 부르면 그 자리에서 KeyError 가 난다."""
        unknown = []
        for name in self.SOURCES:
            path = _REPO / name
            if not path.is_file():
                continue
            for node in self._tr_calls(path):
                key = node.args[1].value
                if key not in i18n._STRINGS["ko"]:
                    unknown.append(f"{name}:{node.lineno} {key!r}")
        self.assertEqual(unknown, [], "\n" + "\n".join(unknown))

    def test_both_languages_carry_the_same_keys(self):
        """한쪽에만 있는 키는 그 언어에서 그 문구를 깨뜨린다."""
        ko = set(i18n._STRINGS["ko"])
        en = set(i18n._STRINGS["en"])
        self.assertEqual(ko - en, set(), f"영어에 없는 키: {sorted(ko - en)}")
        self.assertEqual(en - ko, set(), f"한국어에 없는 키: {sorted(en - ko)}")


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

    def test_korean_growth_stages_carry_no_animal_emoji(self):
        # 사진으로 만든 테마는 고양이가 아닐 수 있다. 고양이 이모지가 붙어
        # 있으면 수달한테 냥이라고 부르는 꼴이 된다.
        stages = [i18n.chonk_stage(value, "ko") for value in (50, 70, 85, 95)]
        self.assertEqual(stages, ["여유", "포동", "배불러", "빵빵!"])
        for stage in stages:
            with self.subTest(stage=stage):
                self.assertTrue(all(ord(ch) < 0x1F300 for ch in stage))

    def test_the_pet_name_falls_back_to_the_default_when_unset(self):
        self.assertEqual(i18n.pet_name("", "ko"), "뚱냥이")
        self.assertEqual(i18n.pet_name(None, "en"), "Memory Cat")
        self.assertEqual(i18n.pet_name("   ", "ko"), "뚱냥이")

    def test_the_pet_name_is_used_when_the_user_named_one(self):
        self.assertEqual(i18n.pet_name("몽이", "ko"), "몽이")
        self.assertEqual(i18n.pet_name("  Mongi  ", "en"), "Mongi")

    def test_translation_can_format_a_language_placeholder(self):
        self.assertEqual(
            i18n.tr("ko", "language_auto", language="한국어"),
            "자동 (한국어)",
        )

    def test_diagnosis_menu_uses_friendly_cat_wording_in_both_languages(self):
        expected = {
            "ko": ("🐾 뭘 먹은 거야?", "🐾 살펴보는 중…", "🐾 다시 살펴보기", "📋 마지막 진단 보기"),
            "en": ("🐾 What did you eat?", "🐾 Checking…", "🐾 Check again", "📋 View last diagnosis"),
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
