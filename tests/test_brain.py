import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import brain
from personality import CUSTOM_PERSONALITY


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "disk": {
                "total_bytes": 1000,
                "used_bytes": 920,
                "free_bytes": 80,
                "percent": 92.0,
            },
            "ram": {
                "total_bytes": 1000,
                "available_bytes": 100,
                "used_bytes": 900,
                "percent": 90.0,
                "pressure_score": 84.0,
            },
            "swap": {"total_bytes": 100, "used_bytes": 50, "percent": 50.0},
            "top_memory_apps": [
                {"name": "Example", "rss_bytes": 200, "rss": "0.0 GB"}
            ],
        }
        self.candidates = [
            {
                "category": "browser_cache",
                "label": "브라우저 캐시",
                "estimated_bytes": 4096,
                "estimated_size": "4.0 KB",
                "item_count": 1,
                "items": [],
                "omitted_item_count": 0,
            },
            {
                "category": "trash",
                "label": "휴지통",
                "estimated_bytes": 0,
                "estimated_size": "0 B",
                "item_count": 0,
                "items": [],
                "omitted_item_count": 0,
            },
        ]

    def test_collect_metrics_uses_shared_metrics_module(self):
        disk = SimpleNamespace(total=100, used=70, free=30, percent=70.0)
        vm = SimpleNamespace(total=200, available=80, used=120, percent=60.0)
        swap = SimpleNamespace(total=50, used=10, percent=20.0)
        with (
            patch.object(brain, "disk_usage", return_value=disk),
            patch.object(brain, "pressure_score", return_value=(44.0, vm, swap)),
            patch.object(brain, "top_memory_apps", return_value=[("Safari", 42)]),
        ):
            snapshot = brain.collect_metrics()

        self.assertEqual(snapshot["disk"]["free_bytes"], 30)
        self.assertEqual(snapshot["ram"]["pressure_score"], 44.0)
        self.assertEqual(snapshot["top_memory_apps"][0]["name"], "Safari")

    def test_collect_metrics_tolerates_unavailable_swap(self):
        disk = SimpleNamespace(total=100, used=70, free=30, percent=70.0)
        vm = SimpleNamespace(total=200, available=80, used=120, percent=60.0)
        with (
            patch.object(brain, "disk_usage", return_value=disk),
            patch.object(brain, "pressure_score", side_effect=OSError),
            patch.object(brain.psutil, "virtual_memory", return_value=vm),
            patch.object(brain, "top_memory_apps", return_value=[]),
        ):
            snapshot = brain.collect_metrics()

        self.assertEqual(snapshot["ram"]["pressure_score"], 36.0)
        self.assertEqual(snapshot["swap"]["total_bytes"], 0)
        self.assertEqual(snapshot["measurement_warnings"], ["swap_unavailable"])

    def test_collect_metrics_tolerates_unavailable_process_list(self):
        disk = SimpleNamespace(total=100, used=70, free=30, percent=70.0)
        vm = SimpleNamespace(total=200, available=80, used=120, percent=60.0)
        swap = SimpleNamespace(total=50, used=10, percent=20.0)
        with (
            patch.object(brain, "disk_usage", return_value=disk),
            patch.object(brain, "pressure_score", return_value=(44.0, vm, swap)),
            patch.object(brain, "top_memory_apps", side_effect=PermissionError),
        ):
            snapshot = brain.collect_metrics()

        self.assertEqual(snapshot["top_memory_apps"], [])
        self.assertEqual(
            snapshot["measurement_warnings"], ["top_memory_apps_unavailable"]
        )

    def test_missing_key_fallback_is_deterministic_json(self):
        with (
            patch.object(brain, "_load_api_key", return_value=None),
            patch.object(
                brain, "collect_cleanup_candidates", return_value=self.candidates
            ),
        ):
            first = brain.diagnose(self.snapshot)
            second = brain.diagnose(self.snapshot)

        self.assertEqual(first, second)
        self.assertEqual(first["source"], "fallback")
        self.assertEqual(first["fallback_reason"], "missing_api_key")
        self.assertEqual(first["estimated_reclaimable_bytes"], 4096)
        self.assertIsInstance(json.dumps(first, ensure_ascii=False), str)
        self.assertEqual(
            {item["category"] for item in first["cleanup_recommendations"]},
            {"browser_cache"},
        )

    def test_api_result_cannot_add_non_whitelisted_category(self):
        parsed = brain._AIDiagnosis(
            why_slow=["디스크 여유 공간이 적습니다."],
            recommendations=[
                brain._AIRecommendation(
                    category="browser_cache", reason="캐시가 큽니다."
                )
            ],
            one_line_advice="캐시부터 확인하세요.",
        )
        fake_client = Mock()
        fake_client.responses.parse.return_value = SimpleNamespace(output_parsed=parsed)
        with (
            patch.object(brain, "_load_api_key", return_value="test-key"),
            patch.object(
                brain, "collect_cleanup_candidates", return_value=self.candidates
            ),
            patch.object(brain, "OpenAI", return_value=fake_client),
        ):
            result = brain.diagnose(
                self.snapshot,
                personality=CUSTOM_PERSONALITY,
                custom_personality="말끝에 냥을 붙이고 짧게 말해줘",
            )

        self.assertEqual(result["source"], "openai")
        self.assertEqual(
            [item["category"] for item in result["cleanup_recommendations"]],
            ["browser_cache"],
        )
        sent_payload = json.loads(fake_client.responses.parse.call_args.kwargs["input"])
        self.assertNotIn("path", json.dumps(sent_payload))
        self.assertEqual(
            fake_client.responses.parse.call_args.kwargs["text"],
            {"verbosity": "low"},
        )
        instructions = fake_client.responses.parse.call_args.kwargs["instructions"]
        self.assertIn("말끝에 냥을 붙이고 짧게 말해줘", instructions)
        self.assertIn("삭제 화이트리스트", instructions)

    def test_safe_trash_rejects_non_whitelisted_path(self):
        with tempfile.NamedTemporaryFile() as handle:
            with self.assertRaises(ValueError):
                brain.safe_trash(handle.name)

    def test_safe_trash_rejects_symlinked_whitelist_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            real_root = base / "RealCache"
            real_root.mkdir()
            target = real_root / "important.txt"
            target.write_text("do not move")
            linked_root = base / "BrowserCache"
            linked_root.symlink_to(real_root, target_is_directory=True)
            with (
                patch.object(brain, "BROWSER_CACHE_ROOTS", (linked_root,)),
                patch.object(brain, "_trash_via_foundation") as trash_mock,
            ):
                with self.assertRaises(ValueError):
                    brain.safe_trash(linked_root / target.name)

            trash_mock.assert_not_called()
            self.assertTrue(target.exists())

    def test_safe_trash_accepts_browser_cache_via_foundation_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "BrowserCache"
            root.mkdir()
            target = root / "cache.bin"
            target.write_bytes(b"cache")
            trash_mock = Mock(return_value="/mock/.Trash/cache.bin")
            with (
                patch.object(brain, "BROWSER_CACHE_ROOTS", (root,)),
                patch.object(brain, "_trash_via_foundation", trash_mock),
            ):
                result = brain.safe_trash(target)

            self.assertEqual(result, "/mock/.Trash/cache.bin")
            trash_mock.assert_called_once_with(target.resolve())

    def test_download_must_be_older_than_30_days(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as temp_dir:
            downloads = Path(temp_dir) / "Downloads"
            downloads.mkdir()
            old_file = downloads / "old.zip"
            old_file.write_bytes(b"old")
            old_time = now - 31 * 24 * 60 * 60
            os.utime(old_file, (old_time, old_time))
            recent_file = downloads / "recent.zip"
            recent_file.write_bytes(b"recent")
            with (
                patch.object(brain, "DOWNLOADS_ROOT", downloads),
                patch.object(
                    brain, "_trash_via_foundation", return_value="/mock/.Trash/old.zip"
                ) as trash_mock,
            ):
                self.assertEqual(
                    brain.safe_trash(old_file), "/mock/.Trash/old.zip"
                )
                with self.assertRaises(ValueError):
                    brain.safe_trash(recent_file)

            trash_mock.assert_called_once_with(old_file.resolve())

    def test_item_already_in_trash_is_not_deleted_again(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trash = Path(temp_dir) / ".Trash"
            trash.mkdir()
            target = trash / "review-me.txt"
            target.write_text("keep recoverable")
            with (
                patch.object(brain, "TRASH_ROOT", trash),
                patch.object(brain, "_trash_via_foundation") as trash_mock,
            ):
                self.assertEqual(brain.safe_trash(target), str(target.resolve()))

            trash_mock.assert_not_called()
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
