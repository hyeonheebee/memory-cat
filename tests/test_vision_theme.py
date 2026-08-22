import base64
import tempfile
import unittest
from io import BytesIO
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from PIL import Image, ImageDraw

import desktop_cat
import vision_theme


def _png_b64(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _synthetic_sheet(stage_count=6):
    sheet = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(sheet)
    spacing = 1200 // stage_count
    for index in range(stage_count):
        radius = 42 + index * 7
        center_x = spacing // 2 + index * spacing
        bottom = 350
        draw.ellipse(
            (
                center_x - radius,
                bottom - radius * 2,
                center_x + radius,
                bottom,
            ),
            fill=(85, 55, 35),
        )
    return sheet


class VisionThemeTests(unittest.TestCase):
    def test_generate_sheet_edits_the_attached_photo_with_required_settings(self):
        generated = Image.new("RGB", (1536, 1024), "white")
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=_png_b64(generated))]
        )
        client = Mock()
        client.images.edit.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "pet.jpg"
            Image.new("RGB", (64, 64), "brown").save(photo)
            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch.object(vision_theme, "OpenAI", return_value=client) as ctor,
            ):
                result = vision_theme.generate_sheet(photo)

        self.assertEqual(result.size, (1536, 1024))
        ctor.assert_called_once_with(
            api_key="test-key", timeout=180.0, max_retries=1
        )
        kwargs = client.images.edit.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-image-2")
        self.assertEqual(kwargs["size"], "1536x1024")
        self.assertEqual(kwargs["quality"], "medium")
        self.assertNotIn("response_format", kwargs)
        self.assertEqual(Path(kwargs["image"].name), photo)
        self.assertIn("THIS exact pet", kwargs["prompt"])
        self.assertIn("no text, no labels, no watermark, no borders", kwargs["prompt"])

    def test_generate_sheet_without_api_key_fails_without_a_local_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "pet.jpg"
            Image.new("RGB", (64, 64), "brown").save(photo)
            with (
                patch.dict("os.environ", {}, clear=True),
                patch.object(vision_theme, "load_dotenv"),
                patch.object(vision_theme, "OpenAI") as client_class,
            ):
                with self.assertRaisesRegex(
                    vision_theme.ThemeGenerationError,
                    "OPENAI_API_KEY is missing",
                ):
                    vision_theme.generate_sheet(photo)

        client_class.assert_not_called()

    def test_generate_sheet_surfaces_api_errors_as_one_line(self):
        client = Mock()
        client.images.edit.side_effect = RuntimeError("network\nunavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "pet.jpg"
            Image.new("RGB", (64, 64), "brown").save(photo)
            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch.object(vision_theme, "OpenAI", return_value=client),
            ):
                with self.assertRaisesRegex(
                    vision_theme.ThemeGenerationError,
                    "OpenAI image generation failed: network unavailable",
                ):
                    vision_theme.generate_sheet(photo)

    def test_build_theme_turns_six_detected_stages_into_a_complete_theme(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames_dir = root / "frames"
            photo = root / "pet.jpg"
            Image.new("RGB", (64, 64), "brown").save(photo)
            with (
                patch.object(vision_theme, "FRAMES_DIR", frames_dir),
                patch.object(
                    vision_theme,
                    "generate_sheet",
                    return_value=_synthetic_sheet(),
                ) as generate,
            ):
                result = vision_theme.build_theme(photo, "mypet", "high")

            output = frames_dir / "mypet"
            self.assertEqual(
                result,
                {"detected_stages": 6, "output_path": str(output)},
            )
            generate.assert_called_once_with(photo, retry_prompt=False)
            self.assertEqual(len(list(output.glob("cat_*.png"))), 40)
            self.assertTrue((output / "cat_00.png").is_file())
            self.assertTrue((output / "cat_39.png").is_file())
            self.assertTrue((output / "_preview.png").is_file())
            self.assertTrue((output / "_raw.png").is_file())
            with patch.object(desktop_cat, "FRAMES_BASE", str(frames_dir)):
                self.assertIn("mypet", desktop_cat.discover_themes())

    def test_build_theme_retries_once_with_a_stronger_separation_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames_dir = root / "frames"
            photo = root / "pet.jpg"
            Image.new("RGB", (64, 64), "brown").save(photo)
            with (
                patch.object(vision_theme, "FRAMES_DIR", frames_dir),
                patch.object(
                    vision_theme,
                    "generate_sheet",
                    side_effect=[_synthetic_sheet(3), _synthetic_sheet(6)],
                ) as generate,
            ):
                result = vision_theme.build_theme(photo, "retry-pet", "low")

            self.assertEqual(result["detected_stages"], 6)
            self.assertEqual(
                generate.call_args_list,
                [
                    call(photo, retry_prompt=False),
                    call(photo, retry_prompt=True),
                ],
            )
            self.assertEqual(
                len(list((frames_dir / "retry-pet").glob("cat_*.png"))),
                40,
            )

    def test_failed_retry_keeps_raw_images_without_partial_theme_frames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames_dir = root / "frames"
            photo = root / "pet.jpg"
            Image.new("RGB", (64, 64), "brown").save(photo)
            with (
                patch.object(vision_theme, "FRAMES_DIR", frames_dir),
                patch.object(
                    vision_theme,
                    "generate_sheet",
                    side_effect=[_synthetic_sheet(3), _synthetic_sheet(3)],
                ),
            ):
                with self.assertRaisesRegex(
                    vision_theme.ThemeGenerationError,
                    "detected 3, 3 stage",
                ):
                    vision_theme.build_theme(photo, "failed-pet", "medium")

            output = frames_dir / "failed-pet"
            self.assertTrue((output / "_raw.png").is_file())
            self.assertTrue((output / "_raw_attempt1.png").is_file())
            self.assertFalse((output / "_preview.png").exists())
            self.assertEqual(list(output.glob("cat_*.png")), [])

    def test_retry_reaches_openai_with_stronger_prompt_and_selected_quality(self):
        responses = [
            SimpleNamespace(
                data=[SimpleNamespace(b64_json=_png_b64(_synthetic_sheet(3)))]
            ),
            SimpleNamespace(
                data=[SimpleNamespace(b64_json=_png_b64(_synthetic_sheet(6)))]
            ),
        ]
        client = Mock()
        client.images.edit.side_effect = responses

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames_dir = root / "frames"
            photo = root / "pet.jpg"
            Image.new("RGB", (64, 64), "brown").save(photo)
            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch.object(vision_theme, "FRAMES_DIR", frames_dir),
                patch.object(vision_theme, "OpenAI", return_value=client),
            ):
                result = vision_theme.build_theme(photo, "api-retry", "high")

        self.assertEqual(result["detected_stages"], 6)
        self.assertEqual(client.images.edit.call_count, 2)
        first, second = client.images.edit.call_args_list
        self.assertEqual(first.kwargs["quality"], "high")
        # 프롬프트 문구를 손봐도 깨지지 않도록 상수를 직접 참조한다.
        # 검증하려는 것은 "재시도할 때만 강화 프롬프트가 덧붙는다" 이지 문구 자체가 아니다.
        retry_text = vision_theme.RETRY_PROMPT.strip()
        self.assertNotIn(retry_text, first.kwargs["prompt"])
        self.assertIn(retry_text, second.kwargs["prompt"])

    def test_cli_reports_generation_errors_as_one_readable_line(self):
        stderr = StringIO()
        with (
            patch.object(
                vision_theme,
                "build_theme",
                side_effect=vision_theme.ThemeGenerationError(
                    "OpenAI request failed:\nnetwork unavailable"
                ),
            ),
            patch("sys.stderr", stderr),
        ):
            exit_code = vision_theme.main(
                ["pet.jpg", "mypet", "--quality", "low"]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            stderr.getvalue(),
            "Error: OpenAI request failed: network unavailable\n",
        )


if __name__ == "__main__":
    unittest.main()
