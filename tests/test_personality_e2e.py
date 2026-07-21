import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import brain
import desktop_cat
from personality import config_personality, preset_label


class PersonalityEndToEndTests(unittest.TestCase):
    def test_each_preset_flows_from_menu_selection_to_openai_instructions(self):
        expected_tone_markers = {
            "냉소적 집사냥": "건조한 유머",
            "따뜻한 이모니냥": "공감부터",
            "무뚝뚝한 무사냥": "과묵한 무사",
        }
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
            original_save_config = desktop_cat.save_config

            for preset, tone_marker in expected_tone_markers.items():
                with self.subTest(preset=preset):
                    controller = desktop_cat.CatController.alloc().init()
                    controller.cfg = dict(desktop_cat.DEFAULT)
                    controller.language = "ko"
                    controller._notify = Mock(return_value=True)
                    sender = Mock()
                    sender.representedObject.return_value = preset

                    with patch.object(
                        desktop_cat,
                        "save_config",
                        side_effect=lambda config: original_save_config(
                            config, config_path
                        ),
                    ):
                        controller.setPersonality_(sender)

                    loaded = desktop_cat.load_config(config_path)
                    selected, custom = config_personality(loaded)
                    self.assertEqual(selected, preset)

                    parsed = brain._AIDiagnosis(
                        why_slow=["현재 수치는 안정적입니다."],
                        recommendations=[],
                        one_line_advice="지금 상태를 유지하세요.",
                    )
                    client = Mock()
                    client.responses.parse.return_value = SimpleNamespace(
                        output_parsed=parsed
                    )
                    callback = Mock()
                    main_queue = Mock()
                    main_queue.addOperationWithBlock_.side_effect = lambda block: block()
                    queue_provider = Mock()
                    queue_provider.mainQueue.return_value = main_queue

                    with (
                        patch.object(brain, "_load_api_key", return_value="e2e-key"),
                        patch.object(brain, "collect_metrics", return_value=snapshot),
                        patch.object(
                            brain, "collect_cleanup_candidates", return_value=[]
                        ),
                        patch.object(brain, "OpenAI", return_value=client),
                        patch.object(desktop_cat, "NSOperationQueue", queue_provider),
                    ):
                        desktop_cat._diagnosis_worker(
                            selected, custom, controller.language, callback
                        )

                    request = client.responses.parse.call_args.kwargs
                    self.assertIn(
                        f"성격: {preset_label(preset, 'ko')}",
                        request["instructions"],
                    )
                    self.assertIn(tone_marker, request["instructions"])
                    callback.assert_called_once()
                    self.assertEqual(callback.call_args.args[0]["source"], "openai")


if __name__ == "__main__":
    unittest.main()
