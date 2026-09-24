"""``windows/win_ai.py`` — 윈도우 진단의 Qt 없는 부분을 검사한다.

PySide6 는 맥 개발 환경에 없어서, 무엇을 보여줄지 정하는 로직을 Qt 밖으로
빼 두고 여기서 검사한다. ``win_ai`` 는 파일을 지우지 않는다는 것도 함께
확인한다.
"""
import ast
import os
import re
import sys
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_WINDOWS_DIR = str(Path(__file__).resolve().parent.parent / "windows")
if _WINDOWS_DIR not in sys.path:
    sys.path.insert(0, _WINDOWS_DIR)

import apppaths
import i18n
import metrics
import win_ai


class DiagnosisLinesTests(unittest.TestCase):
    FAKE = {
        "why_slow": ["램이 거의 찼습니다.", "크롬이 4GB 를 쓰고 있어요."],
        "one_line_advice": "탭을 좀 닫아 보세요.",
        "cleanup_recommendations": [],
        "estimated_reclaimable_bytes": 0,
        "source": "openai",
    }

    #: R27 리뷰 지적: 이 클래스는 디스크 줄 내용을 검사하지 않는데도
    #: ``diagnosis_lines`` 가 이제 매번 ``brain.disk_usage()`` 를 실제로
    #: 부른다. 값 자체는 관심사가 아니니 고정값으로 패치해 결정적으로
    #: 만든다(진짜 psutil 호출을 없애 테스트를 더 빠르고 안정적으로).
    FAKE_DISK = SimpleNamespace(
        percent=50.0, total=200 * 1024 ** 3, used=100 * 1024 ** 3,
        free=100 * 1024 ** 3,
    )

    def test_it_asks_for_a_diagnosis_without_cleanup(self):
        with patch.object(win_ai.brain, "diagnose", return_value=self.FAKE) as d, \
             patch.object(win_ai.brain, "disk_usage", return_value=self.FAKE_DISK):
            win_ai.diagnosis_lines("ko")
        self.assertEqual(d.call_args.kwargs["include_cleanup"], False)

    def test_the_explanation_and_the_advice_are_both_shown(self):
        with patch.object(win_ai.brain, "diagnose", return_value=self.FAKE), \
             patch.object(win_ai.brain, "disk_usage", return_value=self.FAKE_DISK):
            lines = win_ai.diagnosis_lines("ko")
        joined = "\n".join(lines)
        self.assertIn("램이 거의 찼습니다.", joined)
        self.assertIn("탭을 좀 닫아 보세요.", joined)

    def test_the_delete_warning_is_always_the_last_line(self):
        for language in ("ko", "en"):
            with self.subTest(language=language), \
                 patch.object(win_ai.brain, "diagnose", return_value=self.FAKE), \
                 patch.object(win_ai.brain, "disk_usage", return_value=self.FAKE_DISK):
                lines = win_ai.diagnosis_lines(language)
                self.assertEqual(lines[-1], i18n.tr(language, "windows_delete_warning"))

    def test_it_never_reaches_the_file_deleting_code(self):
        """윈도우판은 지우지 않는다. 정리 코드에 발도 들이면 안 된다."""
        with patch.object(win_ai.brain, "collect_cleanup_candidates") as scan, \
             patch.object(win_ai.brain, "safe_trash") as trash, \
             patch.object(win_ai.brain, "_load_api_key", return_value=None), \
             patch.object(win_ai.brain, "disk_usage", return_value=self.FAKE_DISK):
            win_ai.diagnosis_lines("ko")
        scan.assert_not_called()
        trash.assert_not_called()


class DiagnosisSourceNoticeTests(unittest.TestCase):
    """API 오류로 규칙 기반 결과가 나오면, 진단창이 AI 진단인 척하면 안 된다.

    맥판(``desktop_cat.diagnosis_result_content``)이 하는 것과 같은 매핑을
    쓴다 — ``fallback_reason`` 이 없거나 모르는 값이면 ``fallback_unknown``.

    R33 로 ``diagnosis_lines`` 가 fallback 일 때 로그 한 줄을 남기게 되어,
    이 클래스의 fallback 픽스처를 쓰는 테스트들도 이제 로그를 쓴다 — 실제
    ``~/Library/Logs`` 를 건드리지 않도록 매 테스트에서 임시 폴더로 바꿔 끼운다.
    """

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

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
                    language, "windows_diagnosis_source_fallback", reason=reason)
                self.assertEqual(lines[0], notice)

    def test_fallback_missing_api_key_maps_to_its_own_reason(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self._fallback("missing_api_key")):
            lines = win_ai.diagnosis_lines("ko")
        reason = i18n.tr("ko", "fallback_missing_api_key")
        notice = i18n.tr("ko", "windows_diagnosis_source_fallback", reason=reason)
        self.assertEqual(lines[0], notice)

    def test_unknown_fallback_reason_falls_back_to_the_unknown_string(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self._fallback("something_new")):
            lines = win_ai.diagnosis_lines("ko")
        reason = i18n.tr("ko", "fallback_unknown")
        notice = i18n.tr("ko", "windows_diagnosis_source_fallback", reason=reason)
        self.assertEqual(lines[0], notice)

    def test_windows_fallback_notice_never_mentions_personality(self):
        """윈도우엔 성격 기능이 없다 — 맥 문구를 그대로 쓰면 안 된다."""
        for language in ("ko", "en"):
            with self.subTest(language=language), \
                 patch.object(win_ai.brain, "diagnose",
                              return_value=self._fallback("api_error")):
                lines = win_ai.diagnosis_lines(language)
                self.assertNotIn("성격", lines[0])
                self.assertNotIn("Personality", lines[0])
                reason = i18n.tr(language, "fallback_api_error")
                self.assertIn(reason, lines[0])

    def test_mac_fallback_key_text_is_untouched(self):
        """회귀 방지: 맥판이 쓰는 diagnosis_source_fallback 원문은 한 글자도 안 바뀐다."""
        self.assertEqual(
            i18n._STRINGS["ko"]["diagnosis_source_fallback"],
            "⚠️ 오프라인 진단 · 성격 미적용 · {reason}",
        )
        self.assertEqual(
            i18n._STRINGS["en"]["diagnosis_source_fallback"],
            "⚠️ Offline diagnosis · Personality not applied · {reason}",
        )

    def test_openai_source_has_no_fallback_notice(self):
        # 디스크 줄은 이 검사의 관심사가 아니라 비활성화(읽기 실패)해 둔다 —
        # 그래야 lines[0] 이 여전히 why_slow 그대로다.
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self.FAKE_OPENAI), \
             patch.object(win_ai.brain, "disk_usage", side_effect=OSError):
            lines = win_ai.diagnosis_lines("ko")
        self.assertEqual(lines[0], self.FAKE_OPENAI["why_slow"][0])

    def test_the_delete_warning_is_last_even_with_a_fallback_notice(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self._fallback("api_error")):
            lines = win_ai.diagnosis_lines("ko")
        self.assertEqual(lines[-1], i18n.tr("ko", "windows_delete_warning"))


class DiskDetailLineTests(unittest.TestCase):
    """C-2: 진단 결과에 정보창과 같은 디스크 한 줄을 항상 넣는다.

    ``brain.diagnose`` 결과엔 디스크 수치가 없다(정리 후보만 본다) — 정보창
    (``windows_cat.pyw``)과 똑같이 ``brain.disk_usage()`` 를 직접 불러 같은
    문구를 만든다. ``brain.disk_usage`` 는 ``metrics.disk_usage`` 를 그대로
    가리킨다(``brain.py`` 의 ``from metrics import disk_usage, ...``).

    R33 로 ``diagnosis_lines`` 가 fallback 일 때 로그 한 줄을 남기게 되어,
    ``FAKE_FALLBACK`` 을 쓰는 테스트도 이제 로그를 쓴다 — 실제
    ``~/Library/Logs`` 를 건드리지 않도록 매 테스트에서 임시 폴더로 바꿔 끼운다.
    """

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

    #: total=500GB, used=370GB, free=130GB, percent=74% — 바이트가 1024**3 의
    #: 정수배라 human_gb() 결과가 "370.0 GB" 처럼 딱 떨어진다.
    FAKE_DISK = SimpleNamespace(
        percent=74.0,
        total=500 * 1024 ** 3,
        used=370 * 1024 ** 3,
        free=130 * 1024 ** 3,
    )

    FAKE_NO_FALLBACK = {
        "why_slow": ["램이 거의 찼습니다."],
        "one_line_advice": "탭을 좀 닫아 보세요.",
        "cleanup_recommendations": [],
        "estimated_reclaimable_bytes": 0,
        "source": "openai",
    }

    FAKE_FALLBACK = {
        "why_slow": ["램이 거의 찼습니다."],
        "one_line_advice": "탭을 좀 닫아 보세요.",
        "cleanup_recommendations": [],
        "estimated_reclaimable_bytes": 0,
        "source": "fallback",
        "fallback_reason": "api_error",
    }

    def _expected_line(self, language):
        return i18n.tr(
            language, "disk_detail",
            percent=74.0, used="370.0 GB", total="500.0 GB", free="130.0 GB")

    def test_disk_line_uses_the_same_wording_as_the_info_window(self):
        for language in ("ko", "en"):
            with self.subTest(language=language), \
                 patch.object(win_ai.brain, "diagnose",
                              return_value=self.FAKE_NO_FALLBACK), \
                 patch.object(win_ai.brain, "disk_usage",
                              return_value=self.FAKE_DISK):
                lines = win_ai.diagnosis_lines(language)
                self.assertEqual(lines[0], self._expected_line(language))

    def test_disk_line_is_first_when_there_is_no_offline_notice(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self.FAKE_NO_FALLBACK), \
             patch.object(win_ai.brain, "disk_usage",
                          return_value=self.FAKE_DISK):
            lines = win_ai.diagnosis_lines("ko")
        self.assertEqual(lines[0], self._expected_line("ko"))
        self.assertEqual(lines[1], self.FAKE_NO_FALLBACK["why_slow"][0])
        self.assertEqual(lines[-1], i18n.tr("ko", "windows_delete_warning"))

    def test_disk_line_comes_right_after_the_offline_notice(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self.FAKE_FALLBACK), \
             patch.object(win_ai.brain, "disk_usage",
                          return_value=self.FAKE_DISK):
            lines = win_ai.diagnosis_lines("ko")
        reason = i18n.tr("ko", "fallback_api_error")
        notice = i18n.tr("ko", "windows_diagnosis_source_fallback", reason=reason)
        self.assertEqual(lines[0], notice)
        self.assertEqual(lines[1], self._expected_line("ko"))
        self.assertEqual(lines[2], self.FAKE_FALLBACK["why_slow"][0])
        self.assertEqual(lines[-1], i18n.tr("ko", "windows_delete_warning"))

    def test_missing_disk_data_skips_the_line_without_raising(self):
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self.FAKE_NO_FALLBACK), \
             patch.object(win_ai.brain, "disk_usage", side_effect=OSError("no disk")):
            lines = win_ai.diagnosis_lines("ko")
        self.assertEqual(lines[0], self.FAKE_NO_FALLBACK["why_slow"][0])
        self.assertNotIn("💾", "\n".join(lines))

    def test_odd_disk_values_skip_the_line_without_raising(self):
        """숫자가 아닌 값(속성은 있는데 형식화가 안 되는 경우)도 조용히 뺀다."""
        odd_disk = SimpleNamespace(percent="모름", total=0, used=0, free=0)
        with patch.object(win_ai.brain, "diagnose",
                          return_value=self.FAKE_NO_FALLBACK), \
             patch.object(win_ai.brain, "disk_usage", return_value=odd_disk):
            lines = win_ai.diagnosis_lines("ko")
        self.assertEqual(lines[0], self.FAKE_NO_FALLBACK["why_slow"][0])

    def test_win_ai_reads_the_same_disk_function_windows_cat_delegates_to(self):
        """R27: 진단·정보창·프레임 선택이 서로 다른 값을 보면 안 된다.

        ``windows_cat.pyw`` 는 PySide6 가 없는 맥에서 import 할 수 없어
        직접 호출로는 비교하지 못한다. 대신 ``win_ai`` 가 부르는
        ``brain.disk_usage`` 가 ``metrics.disk_usage`` 그 자체(같은 함수
        객체)임을 확인한다 — ``windows_cat.pyw`` 의 ``disk_usage()`` 도
        이제 같은 ``metrics.disk_usage`` 로 위임하도록 고쳤다(그건
        ``tests/test_win_app.py`` 의 소스 스캔이 본다). 이 identity 가
        성립하는 한 셋(정보창·프레임 선택·진단)은 항상 같은 값을 본다.
        """
        self.assertIs(win_ai.brain.disk_usage, metrics.disk_usage)

    def test_demo_disk_percent_override_reaches_the_diagnosis_line(self):
        """데모 변수(``MEMORY_CAT_DEMO_DISK_PERCENT``)가 진단 줄에도 그대로 반영된다.

        실기에서 실제로 관측된 불일치를 재현해 고정한다: 실측 디스크는
        38.9% 인데 데모 변수로 90% 를 강제한 상황. 예전엔 진단
        (``metrics.disk_usage`` 경유)은 90% 를, 정보창(``windows_cat.pyw``
        의 옛 ``disk_usage()``, 데모 변수를 안 봄)은 38.9% 를 보여줘 서로
        어긋났다. 지금은 정보창도 같은 ``metrics.disk_usage`` 로 위임하므로
        여기서 90% 가 나오면(위 identity 검사와 합쳐) 정보창도 같은 90% 를
        보게 된다.
        """
        # metrics.disk_usage() 가 데모 override 를 적용할 때 psutil 결과의
        # ``_replace`` (namedtuple 메서드) 를 쓴다 — SimpleNamespace 로는
        # 실제 psutil.disk_usage() 를 흉내낼 수 없다.
        DiskUsage = namedtuple("DiskUsage", "total used free percent")
        measured = DiskUsage(
            total=1000 * 1024 ** 3, used=389 * 1024 ** 3,
            free=611 * 1024 ** 3, percent=38.9,
        )
        with patch.dict(os.environ, {"MEMORY_CAT_DEMO_DISK_PERCENT": "90"},
                        clear=False), \
             patch.object(metrics.psutil, "disk_usage", return_value=measured), \
             patch.object(win_ai.brain, "diagnose",
                          return_value=self.FAKE_NO_FALLBACK):
            lines = win_ai.diagnosis_lines("ko")
        expected = i18n.tr(
            "ko", "disk_detail", percent=90.0,
            used="900.0 GB", total="1000.0 GB", free="100.0 GB")
        self.assertEqual(lines[0], expected)


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

    def test_the_folder_it_points_at_is_created(self):
        """안내가 가리키는 %APPDATA%\\Memory Cat 폴더가 실제로 있어야 한다.

        아무도 그 폴더를 안 만들면 안내는 존재하지 않는 곳을 가리킨다.
        """
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "not-yet-created"
            with patch.dict(os.environ, {apppaths.HOME_ENV: str(home)}):
                self.assertFalse(home.exists())
                title, body = win_ai.api_key_missing_message("ko")
            self.assertTrue(home.is_dir())
            self.assertIn(str(home), body)
            self.assertIn(".env", body)


class PhotoCheckTests(unittest.TestCase):
    """I-2: 업로드·동의 전에 내용까지 본다 — 진짜 HEIC 와 그냥 깨진 파일을 나눈다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _path(self, name):
        return Path(self._tmp.name) / name

    def _save_image(self, name, fmt):
        from PIL import Image

        path = self._path(name)
        Image.new("RGB", (2, 2), color=(1, 2, 3)).save(path, format=fmt)
        return path

    def test_heic_extension_is_refused_without_opening_the_file(self):
        """맥은 OS 해독기로 HEIC 를 열지만 윈도우는 못 연다.
        아이폰 사진이 기본 HEIC 라 그냥 실패하면 사용자가 이유를 모른다."""
        for language in ("ko", "en"):
            with self.subTest(language=language):
                message = win_ai.check_photo(self._path("cat.heic"), language)
                self.assertEqual(message, i18n.tr(language, "theme_error_heic"))
                self.assertNotIn("macOS", message)
                self.assertNotIn("맥", message)

    def test_png_jpeg_webp_pass_when_the_content_matches(self):
        cases = [
            ("cat.png", "PNG"),
            ("cat.jpg", "JPEG"),
            ("cat.jpeg", "JPEG"),
            ("cat.webp", "WEBP"),
        ]
        for name, fmt in cases:
            with self.subTest(name=name):
                path = self._save_image(name, fmt)
                self.assertIsNone(win_ai.check_photo(path))

    def test_gif_extension_is_still_refused_as_unsupported_format(self):
        message = win_ai.check_photo(self._path("cat.gif"))
        self.assertEqual(message, i18n.tr("ko", "theme_error_format"))

    def test_a_14_byte_text_file_named_jpg_is_unreadable_not_heic(self):
        """깨진 파일을 전부 HEIC 로 몰면 안 된다 — 실기에서 겪은 오분류다."""
        path = self._path("cat.jpg")
        path.write_bytes(b"not an image!!")  # 14 바이트
        for language in ("ko", "en"):
            with self.subTest(language=language):
                message = win_ai.check_photo(path, language)
                self.assertEqual(message, i18n.tr(language, "theme_error_unreadable"))
                self.assertNotIn("macOS", message)
                self.assertNotIn("맥", message)

    def test_heic_content_named_jpg_is_still_detected_as_heic(self):
        path = self._path("cat.jpg")
        path.write_bytes(
            b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 8
        )
        self.assertEqual(
            win_ai.check_photo(path), i18n.tr("ko", "theme_error_heic"))

    def test_missing_file_is_unreadable(self):
        message = win_ai.check_photo(self._path("missing.png"))
        self.assertEqual(message, i18n.tr("ko", "theme_error_unreadable"))


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
    """``create_theme`` 실패 경로는 이제 로그를 남긴다 — 실제 사용자 로그
    폴더(``~/Library/Logs``)에 쓰지 않도록 매 테스트에서 임시 폴더로 바꿔 끼운다."""

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

        self._photo_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._photo_tmp.cleanup)
        self.photo = _make_fake_photo(self._photo_tmp.name)

    def test_heic_is_blocked_before_calling_build_theme(self):
        with patch.object(win_ai.vision_theme, "build_theme") as build:
            with self.assertRaises(win_ai.ThemeError):
                win_ai.create_theme(Path("cat.heic"), "mypet")
        build.assert_not_called()

    def test_unreadable_content_is_blocked_before_calling_build_theme(self):
        """14바이트 텍스트를 .jpg 로 골라도 업로드(build_theme 호출) 전에 막힌다."""
        text_path = Path(self._photo_tmp.name) / "not_a_photo.jpg"
        text_path.write_bytes(b"not an image!!")
        with patch.object(win_ai.vision_theme, "build_theme") as build:
            with self.assertRaises(win_ai.ThemeError) as ctx:
                win_ai.create_theme(text_path, "mypet")
        build.assert_not_called()
        self.assertEqual(
            str(ctx.exception), i18n.tr("ko", "theme_error_unreadable"))

    def test_build_theme_errors_are_wrapped_with_the_cause_preserved(self):
        original = RuntimeError("네트워크 오류")
        with patch.object(win_ai.vision_theme, "build_theme", side_effect=original):
            with self.assertRaises(win_ai.ThemeError) as ctx:
                win_ai.create_theme(self.photo, "mypet")
        self.assertIs(ctx.exception.__cause__, original)

    def test_success_calls_build_theme_and_returns_the_name(self):
        with patch.object(
            win_ai.vision_theme, "build_theme", return_value={"detected_stages": 6}
        ) as build:
            result = win_ai.create_theme(self.photo, "mypet")
        build.assert_called_once_with(self.photo, "mypet", quality="medium")
        self.assertEqual(result, "mypet")


def _make_fake_photo(directory):
    """진짜(하지만 아주 작은) PNG 를 만든다 — ``vision_theme`` 은 패치하므로
    내용은 안 쓰이지만, 경로가 실제 파일을 가리켜야 자연스럽다."""
    from PIL import Image

    path = Path(directory) / "cat.png"
    Image.new("RGB", (2, 2), color=(1, 2, 3)).save(path)
    return path


class FakeAuthError(Exception):
    """openai 의 ``AuthenticationError`` 흉내 — ``status_code`` 속성만 있으면 된다."""
    status_code = 401


def _raise_401_from_vision_theme(*args, **kwargs):
    """``vision_theme.generate_sheet`` 이 401 을 감싸는 것과 같은 모양으로
    ``ThemeGenerationError`` 를 내되, ``__cause__`` 에 진짜(가짜) openai 예외를 남긴다."""
    cause = FakeAuthError(
        "Error code: 401 - {'error': {'message': "
        "'Incorrect API key provided: sk-proj-FAKE****wxyz', 'type': "
        "'invalid_request_error'}}"
    )
    try:
        raise cause
    except FakeAuthError as exc:
        raise win_ai.vision_theme.ThemeGenerationError(
            f"OpenAI image generation failed: {exc}"
        ) from exc


class ThemeErrorSecretRedactionTests(unittest.TestCase):
    """G-1·F-2: 화면엔 번역 문구만, 원문(키 조각 포함)은 로그로만."""

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

        self._photo_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._photo_tmp.cleanup)
        self.photo = _make_fake_photo(self._photo_tmp.name)

    def _log_text(self):
        log_path = Path(self._log_tmp.name) / "ai-errors.log"
        self.assertTrue(log_path.is_file(), "로그 파일이 생기지 않았습니다")
        return log_path.read_text(encoding="utf-8")

    def test_401_shows_translated_invalid_key_guidance(self):
        env_path = apppaths.ensure_user_data_dir() / ".env"
        for language in ("ko", "en"):
            with self.subTest(language=language), \
                 patch.object(win_ai.vision_theme, "build_theme",
                              side_effect=_raise_401_from_vision_theme):
                with self.assertRaises(win_ai.ThemeError) as ctx:
                    win_ai.create_theme(self.photo, "mypet", language)
                expected = i18n.tr(
                    language, "theme_error_invalid_key", path=str(env_path))
                self.assertEqual(str(ctx.exception), expected)

    def test_401_message_has_none_of_the_raw_fragments(self):
        with patch.object(win_ai.vision_theme, "build_theme",
                           side_effect=_raise_401_from_vision_theme):
            with self.assertRaises(win_ai.ThemeError) as ctx:
                win_ai.create_theme(self.photo, "mypet", "ko")
        message = str(ctx.exception)
        for fragment in ("wxyz", "sk-", "401", "Incorrect"):
            self.assertNotIn(fragment, message)

    def test_401_failure_is_logged_with_the_secret_redacted(self):
        with patch.object(win_ai.vision_theme, "build_theme",
                           side_effect=_raise_401_from_vision_theme):
            with self.assertRaises(win_ai.ThemeError):
                win_ai.create_theme(self.photo, "mypet", "ko")
        log_text = self._log_text()
        self.assertNotIn("wxyz", log_text)
        self.assertNotIn("FAKE", log_text)
        self.assertIn("[REDACTED]", log_text)        # 가림 표시
        self.assertIn("theme", log_text)              # 어떤 작업이었는지

    def test_non_401_failure_gets_the_generic_message(self):
        for error in (ValueError("이상한 응답"), RuntimeError("네트워크 오류")):
            with self.subTest(error=type(error).__name__), \
                 patch.object(win_ai.vision_theme, "build_theme", side_effect=error):
                with self.assertRaises(win_ai.ThemeError) as ctx:
                    win_ai.create_theme(self.photo, "mypet", "ko")
                expected = i18n.tr(
                    "ko", "theme_error_generic", path=str(win_ai._ai_error_log_path()))
                self.assertEqual(str(ctx.exception), expected)
                self.assertNotIn("네트워크 오류", str(ctx.exception))
                self.assertNotIn("이상한 응답", str(ctx.exception))

    def test_non_401_failure_is_still_logged_with_the_raw_text_redacted(self):
        with patch.object(win_ai.vision_theme, "build_theme",
                           side_effect=RuntimeError("token sk-proj-FAKE****zzzz leaked")):
            with self.assertRaises(win_ai.ThemeError):
                win_ai.create_theme(self.photo, "mypet", "ko")
        log_text = self._log_text()
        self.assertIn("token", log_text)
        self.assertNotIn("zzzz", log_text)
        self.assertIn("sk-***", log_text)

    def test_a_status_500_error_is_not_treated_as_an_invalid_key(self):
        class FakeServerError(Exception):
            status_code = 500

        with patch.object(win_ai.vision_theme, "build_theme",
                           side_effect=FakeServerError("boom")):
            with self.assertRaises(win_ai.ThemeError) as ctx:
                win_ai.create_theme(self.photo, "mypet", "ko")
        expected = i18n.tr(
            "ko", "theme_error_generic", path=str(win_ai._ai_error_log_path()))
        self.assertEqual(str(ctx.exception), expected)

    def test_log_write_failure_does_not_leak_into_a_new_exception(self):
        """로그 경로 아래가 사실 파일이면(폴더를 못 만들면) OSError 가 나지만,
        ``create_theme`` 은 여전히 번역된 ``ThemeError`` 로 끝나야 한다."""
        blocked = Path(self._log_tmp.name) / "blocked-as-a-file"
        blocked.write_text("이 자리는 폴더가 아니라 파일입니다")
        with patch.object(win_ai.apppaths, "log_dir",
                           return_value=blocked / "logs"), \
             patch.object(win_ai.vision_theme, "build_theme",
                          side_effect=RuntimeError("boom")):
            with self.assertRaises(win_ai.ThemeError) as ctx:
                win_ai.create_theme(self.photo, "mypet", "ko")
        expected = i18n.tr(
            "ko", "theme_error_generic",
            path=str(blocked / "logs" / "ai-errors.log"))
        self.assertEqual(str(ctx.exception), expected)


class RedactSecretsTests(unittest.TestCase):
    def test_sk_prefixed_tokens_are_redacted_to_the_end(self):
        text = "key=sk-proj-FAKE1234.abcd_efgh-ijkl****wxyz done"
        redacted = win_ai.redact_secrets(text)
        self.assertNotIn("wxyz", redacted)
        self.assertIn("sk-***", redacted)

    def test_sk_token_glued_after_another_letter_is_still_redacted(self):
        """`ssk-proj…` 처럼 앞에 다른 글자가 붙어도 `sk-` 이후는 가려진다."""
        text = "token ssk-proj-FAKE****wxyz end"
        redacted = win_ai.redact_secrets(text)
        self.assertNotIn("wxyz", redacted)
        self.assertIn("sk-***", redacted)

    def test_incorrect_api_key_provided_value_is_redacted_without_sk_prefix(self):
        text = "Incorrect API key provided: abcdefgh12345, please check"
        redacted = win_ai.redact_secrets(text)
        self.assertNotIn("abcdefgh12345", redacted)
        self.assertIn("Incorrect API key provided:", redacted)

    def test_bearer_tokens_are_redacted(self):
        text = "Authorization: Bearer abc123XYZ.def456"
        redacted = win_ai.redact_secrets(text)
        self.assertNotIn("abc123XYZ", redacted)

    def test_plain_sentences_without_secrets_are_untouched(self):
        text = "네트워크 연결이 잠시 끊겼어요. 다시 시도해 주세요."
        self.assertEqual(win_ai.redact_secrets(text), text)

    def test_empty_text_is_returned_as_is(self):
        self.assertEqual(win_ai.redact_secrets(""), "")
        self.assertIsNone(win_ai.redact_secrets(None))


class ThemeFailureMessageTests(unittest.TestCase):
    """``_ThemeWorker`` 가 (있을 수 없지만) ``ThemeError`` 가 아닌 예외를 받았을 때
    쓸 문구를 정하는 판단 — Qt 없는 쪽에 둬서 테스트할 수 있게 한다."""

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

    def test_a_theme_error_is_passed_through_unchanged(self):
        error = win_ai.ThemeError("이미 번역된 안내 문구")
        self.assertEqual(
            win_ai.theme_failure_message(error, "ko"), "이미 번역된 안내 문구")

    def test_any_other_exception_gets_the_generic_message(self):
        error = RuntimeError("boom, 원문 노출 금지")
        for language in ("ko", "en"):
            with self.subTest(language=language):
                message = win_ai.theme_failure_message(error, language)
                expected = i18n.tr(
                    language, "theme_error_generic",
                    path=str(win_ai._ai_error_log_path()))
                self.assertEqual(message, expected)
                self.assertNotIn("boom", message)


class LogAiFailureTests(unittest.TestCase):
    """진단 실패에도 같은 로그 함수를 쓴다(``win_ai_ui`` 의 ``_DiagnosisWorker``).
    Qt 를 거치지 않고 함수 자체를 검사한다."""

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

    def test_it_writes_the_kind_and_a_redacted_message(self):
        try:
            raise ValueError("Incorrect API key provided: sk-proj-FAKE****abcd")
        except ValueError as error:
            win_ai.log_ai_failure("diagnosis", error)
        log_path = Path(self._log_tmp.name) / "ai-errors.log"
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("diagnosis", text)
        self.assertNotIn("abcd", text)

    def test_it_never_raises_when_the_log_folder_cannot_be_created(self):
        blocked = Path(self._log_tmp.name) / "blocked-as-a-file"
        blocked.write_text("파일")
        with patch.object(win_ai.apppaths, "log_dir", return_value=blocked / "logs"):
            try:
                raise RuntimeError("boom")
            except RuntimeError as error:
                win_ai.log_ai_failure("theme", error)          # 예외가 새면 실패


class LogConsentTests(unittest.TestCase):
    """K-1: 동의 3지점(shown·accepted·declined)을 ``log_ai_failure`` 와 같은
    파일에 남긴다. 다음 실기에서 "shown 줄은 있는데 accepted 가 없는데
    업로드가 됐다" 같은 모양이 나오면 버그 위치가 바로 잡힌다."""

    #: ``datetime.isoformat(timespec="seconds")`` 형식. ``log_ai_failure`` 가
    #: 쓰는 것과 같은 타임스탬프 모양이어야 한 파일을 같이 훑어볼 수 있다.
    _TIMESTAMP_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\] ")

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

    def _log_text(self):
        return (Path(self._log_tmp.name) / "ai-errors.log").read_text(
            encoding="utf-8")

    def test_each_stage_writes_one_timestamped_line(self):
        for stage in ("shown", "accepted", "declined"):
            with self.subTest(stage=stage), \
                 tempfile.TemporaryDirectory() as tmp, \
                 patch.object(win_ai.apppaths, "log_dir", return_value=Path(tmp)):
                win_ai.log_consent(stage)

                text = (Path(tmp) / "ai-errors.log").read_text(encoding="utf-8")
                lines = [line for line in text.splitlines() if line]
                self.assertEqual(len(lines), 1)
                self.assertTrue(
                    self._TIMESTAMP_RE.match(lines[0]),
                    f"타임스탬프 형식이 아닙니다: {lines[0]!r}")
                self.assertIn(f"consent {stage}", lines[0])

    def test_it_shares_the_file_with_log_ai_failure(self):
        """같은 파일 하나만 보내면 되게 — 파일 이름을 바꾸지 않는다."""
        win_ai.log_consent("shown")
        try:
            raise RuntimeError("네트워크 오류")
        except RuntimeError as error:
            win_ai.log_ai_failure("theme", error)
        win_ai.log_consent("accepted")

        log_path = Path(self._log_tmp.name) / "ai-errors.log"
        self.assertTrue(log_path.exists())
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("consent shown", text)
        self.assertIn("theme", text)
        self.assertIn("consent accepted", text)

    def test_calling_the_three_stages_appends_three_lines_in_order(self):
        win_ai.log_consent("shown")
        win_ai.log_consent("declined")
        text = self._log_text()
        lines = [line for line in text.splitlines() if line]
        self.assertEqual(len(lines), 2)
        self.assertIn("consent shown", lines[0])
        self.assertIn("consent declined", lines[1])

    def test_unknown_stage_raises_value_error_instead_of_logging_silently(self):
        """세 값 밖은 구현 실수다 — 로그가 아니라 예외로 바로 드러낸다."""
        with self.assertRaises(ValueError):
            win_ai.log_consent("maybe")
        log_path = Path(self._log_tmp.name) / "ai-errors.log"
        self.assertFalse(log_path.exists())

    def test_it_never_raises_when_the_log_folder_cannot_be_created(self):
        blocked = Path(self._log_tmp.name) / "blocked-as-a-file"
        blocked.write_text("파일")
        with patch.object(win_ai.apppaths, "log_dir", return_value=blocked / "logs"):
            win_ai.log_consent("shown")          # 예외가 새면 실패

    def test_no_photo_path_or_key_like_text_is_ever_written(self):
        """단계 이름 말고는 아무것도 남기지 않는다."""
        win_ai.log_consent("shown")
        text = self._log_text()
        self.assertNotIn("sk-", text)
        self.assertNotIn(".png", text)
        self.assertNotIn(".jpg", text)


class DiagnosisFallbackLogTests(unittest.TestCase):
    """R33: 진단이 fallback(API 키 없음·네트워크 오류 등)으로 빠지면 같은
    로그 파일에 사유 한 줄을 남긴다. ``brain.diagnose`` 는 가짜로 패치한다."""

    def setUp(self):
        self._log_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._log_tmp.cleanup)
        self._log_patch = patch.object(
            win_ai.apppaths, "log_dir", return_value=Path(self._log_tmp.name))
        self._log_patch.start()
        self.addCleanup(self._log_patch.stop)

    def _log_path(self):
        return Path(self._log_tmp.name) / "ai-errors.log"

    def test_fallback_result_logs_the_reason(self):
        fallback = {
            "why_slow": ["램이 거의 찼습니다."],
            "one_line_advice": "탭을 좀 닫아 보세요.",
            "cleanup_recommendations": [],
            "estimated_reclaimable_bytes": 0,
            "source": "fallback",
            "fallback_reason": "api_error",
        }
        with patch.object(win_ai.brain, "diagnose", return_value=fallback):
            win_ai.diagnosis_lines("ko")
        text = self._log_path().read_text(encoding="utf-8")
        self.assertIn("diagnosis fallback: api_error", text)

    def test_openai_source_writes_nothing(self):
        openai_result = {
            "why_slow": ["램이 거의 찼습니다."],
            "one_line_advice": "탭을 좀 닫아 보세요.",
            "cleanup_recommendations": [],
            "estimated_reclaimable_bytes": 0,
            "source": "openai",
        }
        with patch.object(win_ai.brain, "diagnose", return_value=openai_result), \
             patch.object(win_ai.brain, "disk_usage", side_effect=OSError):
            win_ai.diagnosis_lines("ko")
        self.assertFalse(self._log_path().exists())


class ConsentButtonLabelsTests(unittest.TestCase):
    """I-3: 동의창 버튼은 맥 동의창과 같은 공용 키(pet_theme_continue·cancel)를 쓴다."""

    def test_labels_match_the_shared_mac_keys(self):
        for language in ("ko", "en"):
            with self.subTest(language=language):
                continue_label, cancel_label = win_ai.consent_button_labels(
                    language)
                self.assertEqual(
                    continue_label, i18n.tr(language, "pet_theme_continue"))
                self.assertEqual(cancel_label, i18n.tr(language, "cancel"))


class ConsentDialogSourceTests(unittest.TestCase):
    """win_ai_ui 는 Qt 라 맥에서 실행/임포트가 안 된다 — 소스 텍스트로만 배선을 본다."""

    @classmethod
    def setUpClass(cls):
        path = Path(_WINDOWS_DIR) / "win_ai_ui.py"
        cls.source = path.read_text(encoding="utf-8")

    def test_default_and_escape_buttons_are_set_on_the_consent_dialog(self):
        self.assertIn("setDefaultButton(", self.source)
        self.assertIn("setEscapeButton(", self.source)

    def test_the_yes_no_question_dialog_is_gone(self):
        self.assertNotIn("QMessageBox.question(", self.source)
        self.assertNotIn("StandardButton.Yes", self.source)

    def test_consent_labels_come_from_win_ai(self):
        self.assertIn("win_ai.consent_button_labels(", self.source)

    def test_the_diagnosis_worker_never_emits_the_raw_error_string(self):
        """R26: 화면엔 번역 문구만 — 워커가 str(error) 를 그대로 emit 하면 안 된다.

        리터럴 문자열(``"self.failed.emit(str(error))"``) 하나만 찾으면 코드
        포맷이 살짝만 바뀌어도(개행·괄호 위치) 놓친다. AST 로
        ``_DiagnosisWorker.run()`` 의 except 블록 안에 ``str(<예외 변수>)``
        호출이 있는지를 직접 본다 — emit 호출 하나만이 아니라 그 블록
        전체를 본다.
        """
        tree = ast.parse(self.source)
        worker_run = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "_DiagnosisWorker":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "run":
                        worker_run = item
        self.assertIsNotNone(worker_run, "_DiagnosisWorker.run() 을 못 찾았습니다.")

        except_handlers = [
            n for n in ast.walk(worker_run) if isinstance(n, ast.ExceptHandler)
        ]
        self.assertTrue(except_handlers, "run() 안에 except 블록이 없습니다.")
        error_names = {h.name for h in except_handlers if h.name}
        self.assertTrue(error_names, "except 블록이 예외를 이름으로 받지 않습니다.")

        for handler in except_handlers:
            for node in ast.walk(handler):
                offending = (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "str"
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in error_names
                )
                self.assertFalse(
                    offending,
                    "except 블록에서 str(error) 를 그대로 쓰고 있습니다 — "
                    "화면엔 번역된 안내만 나가야 합니다.",
                )

    # --- K-1: 동의창을 앞으로 끌어오고, 동의 3지점을 로그로 남긴다 --------

    def _tree(self):
        return ast.parse(self.source)

    def _top_level_function(self, name):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def _sorted_calls(self, func_node):
        """``func_node`` 안의 모든 호출을 소스 위치(줄·컬럼) 순서로.

        ``ast.walk`` 는 너비 우선이라 소스 순서와 다를 수 있다(``tests/
        test_win_app.py`` 의 같은 패턴 참고) — 그래서 ``(lineno,
        col_offset)`` 로 정렬해 실제 실행 순서를 본다.
        """
        calls = []
        for node in ast.walk(func_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            else:
                continue
            calls.append((node.lineno, node.col_offset, name, node))
        calls.sort(key=lambda item: (item[0], item[1]))
        return calls

    def _log_consent_calls_by_stage(self, func_node):
        """``win_ai.log_consent("<stage>")`` 처럼 문자열 리터럴로 부른
        호출들을 stage -> [노드] 로 모은다. 문자열 하나만 보는 검사가 아니라
        실제 호출 인자(AST 상수)를 읽는다."""
        calls_by_stage = {}
        for node in ast.walk(func_node):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "log_consent"):
                continue
            if not (node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                continue
            calls_by_stage.setdefault(node.args[0].value, []).append(node)
        return calls_by_stage

    def test_bring_to_front_helper_sets_the_stay_on_top_flag_and_raises_and_activates(self):
        """헬퍼가 항상-위 플래그를 주고 ``raise_``·``activateWindow`` 를
        부르는지 AST 로 본다 — 이름이 바뀌어도(리터럴 문자열 검사가 아니라)
        실제 호출을 본다."""
        helper = None
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.FunctionDef) and node.name == "_bring_to_front":
                helper = node
                break
        self.assertIsNotNone(
            helper, "_bring_to_front(또는 같은 역할의 헬퍼)를 못 찾았습니다.")

        attr_calls = {
            node.func.attr
            for node in ast.walk(helper)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertIn(
            "raise_", attr_calls, "_bring_to_front 안에 raise_() 호출이 없습니다.")
        self.assertIn(
            "activateWindow", attr_calls,
            "_bring_to_front 안에 activateWindow() 호출이 없습니다.")

        flag_calls = [
            node for node in ast.walk(helper)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("setWindowFlag", "setWindowFlags")
        ]
        self.assertTrue(
            flag_calls, "_bring_to_front 안에 창 플래그를 주는 호출이 없습니다.")
        self.assertTrue(
            any("WindowStaysOnTopHint" in ast.dump(call) for call in flag_calls),
            "_bring_to_front 가 WindowStaysOnTopHint 를 주지 않습니다.",
        )

    def test_bring_to_front_is_applied_to_the_consent_dialog_before_exec(self):
        make_theme = self._top_level_function("make_theme")
        self.assertIsNotNone(make_theme, "make_theme() 를 못 찾았습니다.")

        calls = self._sorted_calls(make_theme)
        call_names = [name for _, _, name, _ in calls]

        self.assertIn(
            "_bring_to_front", call_names,
            "make_theme() 안에서 _bring_to_front(...) 를 부르지 않습니다.")
        self.assertIn("exec", call_names, "make_theme() 안에서 box.exec() 를 부르지 않습니다.")
        self.assertLess(
            call_names.index("_bring_to_front"),
            call_names.index("exec"),
            "_bring_to_front 는 box.exec() 보다 앞에서 불러야 합니다 "
            "(모달 루프가 시작되면 그 뒤엔 이 창을 다시 건드릴 수 없다).",
        )

        # 동의창(box) 에 적용됐는지 — 인자 이름까지 확인한다.
        bring_to_front_call = next(
            node for _, _, name, node in calls if name == "_bring_to_front")
        self.assertTrue(
            bring_to_front_call.args
            and isinstance(bring_to_front_call.args[0], ast.Name)
            and bring_to_front_call.args[0].id == "box",
            "_bring_to_front 가 동의창(box) 이 아닌 다른 인자로 불립니다.",
        )

    def test_consent_shown_is_logged_before_the_dialog_is_executed(self):
        make_theme = self._top_level_function("make_theme")
        self.assertIsNotNone(make_theme, "make_theme() 를 못 찾았습니다.")

        shown_calls = self._log_consent_calls_by_stage(make_theme).get("shown")
        self.assertTrue(
            shown_calls, 'make_theme() 안에서 log_consent("shown") 을 못 찾았습니다.')

        exec_calls = [
            node for node in ast.walk(make_theme)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "exec"
        ]
        self.assertTrue(exec_calls, "make_theme() 안에서 box.exec() 를 못 찾았습니다.")

        shown_pos = min((n.lineno, n.col_offset) for n in shown_calls)
        exec_pos = min((n.lineno, n.col_offset) for n in exec_calls)
        self.assertLess(
            shown_pos, exec_pos,
            'log_consent("shown") 은 box.exec() 보다 앞에서 불러야 합니다.')

    def test_accepted_and_declined_are_logged_in_the_matching_branch_only(self):
        """``accepted`` 는 "진행" 분기 안에서만, ``declined`` 는 그 반대
        분기에서만 불려야 한다 — ``clickedButton()`` 을 검사하는 ``if`` 문을
        찾아 ``body``/``orelse`` 를 각각 본다."""
        make_theme = self._top_level_function("make_theme")
        self.assertIsNotNone(make_theme, "make_theme() 를 못 찾았습니다.")

        consent_if = None
        for node in ast.walk(make_theme):
            if not isinstance(node, ast.If):
                continue
            test_call_names = {
                n.func.attr for n in ast.walk(node.test)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            }
            if "clickedButton" in test_call_names:
                consent_if = node
                break
        self.assertIsNotNone(
            consent_if, "clickedButton() 을 검사하는 if 문을 못 찾았습니다.")

        def _stage_logged_in(stmts, stage):
            for stmt in stmts:
                for node in ast.walk(stmt):
                    if (isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Attribute)
                            and node.func.attr == "log_consent"
                            and node.args
                            and isinstance(node.args[0], ast.Constant)
                            and node.args[0].value == stage):
                        return True
            return False

        self.assertTrue(
            _stage_logged_in(consent_if.body, "accepted"),
            '"진행" 분기 안에서 log_consent("accepted") 를 부르지 않습니다.')
        self.assertTrue(
            _stage_logged_in(consent_if.orelse, "declined"),
            '그 반대 분기에서 log_consent("declined") 를 부르지 않습니다.')
        self.assertFalse(
            _stage_logged_in(consent_if.body, "declined"),
            '"진행" 분기 안에서 declined 를 부르면 안 됩니다.')
        self.assertFalse(
            _stage_logged_in(consent_if.orelse, "accepted"),
            '반대 분기에서 accepted 를 부르면 안 됩니다.')


if __name__ == "__main__":
    unittest.main()
