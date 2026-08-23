"""윈도우 빌드는 이 저장소의 테스트로 실행해 볼 수 없다(PySide6/Windows 필요).

그래서 최소한 "문자열이 빠져 있어 KeyError 로 죽는" 경우만은 정적으로 막는다.
i18n 에 키를 추가하면서 한쪽 언어만 넣거나, 윈도우 쪽에서 없는 키를 쓰면
여기서 잡힌다.
"""
import ast
import re
import unittest
from pathlib import Path

import i18n

SOURCE = Path(__file__).resolve().parent.parent / "windows" / "windows_cat.pyw"


class WindowsStringTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")

    def test_the_windows_app_still_parses(self):
        ast.parse(self.source)

    def test_every_translated_key_exists_in_both_languages(self):
        keys = set(re.findall(r"tr\(\s*language\s*,\s*[\"']([a-z_]+)[\"']", self.source))
        keys |= set(re.findall(r"[\"'](theme_[a-z]+|size_[a-z]+)[\"']", self.source))
        self.assertTrue(keys, "번역 키를 하나도 찾지 못했다면 정규식이 낡은 것이다")
        for key in sorted(keys):
            with self.subTest(key=key):
                for language in ("ko", "en"):
                    self.assertIn(key, i18n._STRINGS[language])

    def test_the_language_menu_can_label_every_choice(self):
        for choice in i18n.LANGUAGE_OVERRIDES:
            with self.subTest(choice=choice):
                for language in ("ko", "en"):
                    i18n.tr(language, f"language_{choice}")

    def test_no_korean_is_hardcoded_in_the_interface(self):
        # 주석과 독스트링은 한국어로 두되, 화면에 나가는 문자열은 i18n 을 거쳐야 한다.
        tree = ast.parse(self.source)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
        # 크기 키는 config.json 에 저장되는 식별자라 번역 대상이 아니다.
        allowed = set(i18n._STRINGS["ko"]) | {"작게", "보통", "크게", "왕"}
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if text in docstrings or text in allowed:
                    continue
                if re.search(r"[가-힣]", text):
                    offenders.append(text)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
