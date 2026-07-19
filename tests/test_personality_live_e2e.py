import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import brain
import desktop_cat
from personality import CUSTOM_PERSONALITY, config_personality


RUN_LIVE_E2E = os.getenv("RUN_LIVE_PERSONALITY_E2E") == "1"


@unittest.skipUnless(
    RUN_LIVE_E2E,
    "set RUN_LIVE_PERSONALITY_E2E=1 to call the real OpenAI API",
)
class LivePersonalityEndToEndTests(unittest.TestCase):
    def test_custom_personality_marker_appears_in_live_model_advice(self):
        marker = "냥도장"
        snapshot = {
            "disk": {
                "total_bytes": 1000,
                "used_bytes": 500,
                "free_bytes": 500,
                "percent": 50.0,
            },
            "ram": {
                "total_bytes": 1000,
                "available_bytes": 600,
                "used_bytes": 400,
                "percent": 40.0,
                "pressure_score": 30.0,
            },
            "swap": {"total_bytes": 0, "used_bytes": 0, "percent": 0.0},
            "top_memory_apps": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config = dict(desktop_cat.DEFAULT)
            config["personality"] = CUSTOM_PERSONALITY
            config["custom_personality"] = (
                f"따뜻한 고양이 말투로 말하고 one_line_advice에 정확히 '{marker}'을 포함해줘"
            )
            self.assertTrue(desktop_cat.save_config(config, config_path))
            selected, custom = config_personality(
                desktop_cat.load_config(config_path)
            )

            with patch.object(brain, "collect_cleanup_candidates", return_value=[]):
                result = brain.diagnose(
                    snapshot,
                    personality=selected,
                    custom_personality=custom,
                    language="ko",
                )

        self.assertEqual(result["source"], "openai", result["fallback_reason"])
        self.assertIn(marker, result["one_line_advice"])


if __name__ == "__main__":
    unittest.main()
