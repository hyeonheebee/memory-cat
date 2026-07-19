import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import vision_theme


@unittest.skipUnless(
    os.getenv("RUN_LIVE_VISION_THEME_E2E") == "1",
    "set RUN_LIVE_VISION_THEME_E2E=1 to call the real OpenAI Images API",
)
class LiveVisionThemeTests(unittest.TestCase):
    def test_one_reference_pet_photo_generates_a_landscape_sheet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "reference-pet.png"
            image = Image.new("RGB", (512, 512), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((126, 110, 386, 400), fill=(125, 80, 45))
            draw.polygon(
                ((160, 150), (195, 55), (235, 150)), fill=(125, 80, 45)
            )
            draw.polygon(
                ((275, 150), (315, 55), (350, 150)), fill=(125, 80, 45)
            )
            draw.ellipse((200, 215, 220, 235), fill="black")
            draw.ellipse((292, 215, 312, 235), fill="black")
            image.save(photo)

            sheet = vision_theme.generate_sheet(photo)

        self.assertEqual(sheet.size, (1536, 1024))


if __name__ == "__main__":
    unittest.main()
