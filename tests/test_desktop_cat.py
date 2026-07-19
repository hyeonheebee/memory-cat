import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import desktop_cat
from personality import CUSTOM_PERSONALITY, DEFAULT_PERSONALITY


class DesktopCatTests(unittest.TestCase):
    def test_old_config_gets_default_personality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps({"theme": "cute", "size": "작게"}), encoding="utf-8"
            )
            config = desktop_cat.load_config(path)

        self.assertEqual(config["personality"], DEFAULT_PERSONALITY)
        self.assertEqual(config["custom_personality"], "")

    def test_custom_personality_round_trips_through_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            config = dict(desktop_cat.DEFAULT)
            config["personality"] = CUSTOM_PERSONALITY
            config["custom_personality"] = "차분하게 숫자부터 말해줘"
            self.assertTrue(desktop_cat.save_config(config, path))
            loaded = desktop_cat.load_config(path)

        self.assertEqual(loaded["personality"], CUSTOM_PERSONALITY)
        self.assertEqual(loaded["custom_personality"], "차분하게 숫자부터 말해줘")

    def test_diagnose_action_starts_daemon_background_thread(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT)
        controller._diagnosis_running = False
        controller._diagnosis_thread = None
        controller._notify = Mock(return_value=True)
        thread = Mock()
        with patch.object(desktop_cat.threading, "Thread", return_value=thread) as ctor:
            controller.diagnose_(None)

        self.assertTrue(controller._diagnosis_running)
        ctor.assert_called_once()
        kwargs = ctor.call_args.kwargs
        self.assertIs(kwargs["target"], desktop_cat._diagnosis_worker)
        self.assertTrue(kwargs["daemon"])
        self.assertEqual(kwargs["name"], "memory-cat-diagnosis")
        thread.start.assert_called_once_with()

    def test_worker_dispatches_result_on_main_queue(self):
        result = {
            "why_slow": ["디스크가 찼습니다."],
            "one_line_advice": "캐시부터 확인하세요.",
            "cleanup_recommendations": [],
        }
        callback = Mock()
        queue = Mock()
        queue.addOperationWithBlock_.side_effect = lambda block: block()
        queue_provider = Mock()
        queue_provider.mainQueue.return_value = queue
        with (
            patch.object(desktop_cat, "run_diagnosis", return_value=result) as diagnose,
            patch.object(desktop_cat, "NSOperationQueue", queue_provider),
        ):
            desktop_cat._diagnosis_worker(
                "무뚝뚝한 무사냥", "", callback
            )

        diagnose.assert_called_once_with(
            personality="무뚝뚝한 무사냥", custom_personality=""
        )
        queue.addOperationWithBlock_.assert_called_once()
        callback.assert_called_once_with(result)

    def test_notification_contains_causes_and_one_line_advice(self):
        text = desktop_cat.diagnosis_notification_text(
            {
                "why_slow": ["디스크가 찼습니다.", "RAM 압박이 높습니다."],
                "one_line_advice": "오래된 다운로드부터 확인하세요.",
            }
        )
        self.assertIn("디스크가 찼습니다.", text)
        self.assertIn("RAM 압박이 높습니다.", text)
        self.assertIn("오래된 다운로드부터 확인하세요.", text)

    def test_only_confirmed_cleanup_items_reach_safe_trash(self):
        recommendations = [
            {
                "category": "old_downloads",
                "items": [
                    {"path": "/Downloads/keep.zip"},
                    {"path": "/Downloads/trash.zip"},
                ],
            },
            {
                "category": "trash",
                "items": [{"path": "/.Trash/already.txt"}],
            },
        ]
        trash = Mock()
        summary = desktop_cat.process_cleanup_recommendations(
            recommendations,
            lambda recommendation, item: not item["path"].endswith("keep.zip"),
            trash_func=trash,
        )

        self.assertEqual(
            [call.args[0] for call in trash.call_args_list],
            ["/Downloads/trash.zip", "/.Trash/already.txt"],
        )
        self.assertEqual(
            summary,
            {"moved": 1, "already_in_trash": 1, "skipped": 1, "failed": 0},
        )


if __name__ == "__main__":
    unittest.main()
