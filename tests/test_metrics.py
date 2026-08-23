import unittest
from collections import namedtuple
from types import SimpleNamespace
from unittest.mock import patch

import metrics


DiskUsage = namedtuple("DiskUsage", "total used free percent")


class MetricsTests(unittest.TestCase):
    def test_demo_disk_percent_recalculates_used_and_free(self):
        measured = DiskUsage(total=1000, used=250, free=750, percent=25.0)
        with (
            patch.dict(
                "os.environ",
                {"MEMORY_CAT_DEMO_DISK_PERCENT": "75.5"},
                clear=False,
            ),
            patch.object(metrics.psutil, "disk_usage", return_value=measured),
        ):
            usage = metrics.disk_usage()

        self.assertEqual(usage.total, 1000)
        self.assertEqual(usage.percent, 75.5)
        self.assertEqual(usage.used, 755)
        self.assertEqual(usage.free, 245)

    def test_disk_usage_is_unchanged_when_demo_override_is_unset(self):
        measured = DiskUsage(total=1000, used=250, free=750, percent=25.0)
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(metrics.psutil, "disk_usage", return_value=measured),
        ):
            usage = metrics.disk_usage()

        self.assertIs(usage, measured)

    def test_demo_disk_percent_is_clamped_to_valid_range(self):
        measured = DiskUsage(total=1000, used=250, free=750, percent=25.0)
        expected = {
            "-12.5": (0.0, 0, 1000),
            "145": (100.0, 1000, 0),
        }
        for raw, values in expected.items():
            with self.subTest(raw=raw):
                with (
                    patch.dict(
                        "os.environ",
                        {"MEMORY_CAT_DEMO_DISK_PERCENT": raw},
                        clear=False,
                    ),
                    patch.object(
                        metrics.psutil, "disk_usage", return_value=measured
                    ),
                ):
                    usage = metrics.disk_usage()
                self.assertEqual(
                    (usage.percent, usage.used, usage.free), values
                )

    def test_invalid_demo_disk_percent_uses_measured_usage(self):
        measured = DiskUsage(total=1000, used=250, free=750, percent=25.0)
        for raw in ("not-a-number", "nan", ""):
            with self.subTest(raw=raw):
                with (
                    patch.dict(
                        "os.environ",
                        {"MEMORY_CAT_DEMO_DISK_PERCENT": raw},
                        clear=False,
                    ),
                    patch.object(
                        metrics.psutil, "disk_usage", return_value=measured
                    ),
                ):
                    usage = metrics.disk_usage()
                self.assertIs(usage, measured)

    def test_safe_pressure_score_keeps_ram_when_swap_lookup_fails(self):
        vm = SimpleNamespace(total=8, used=4, percent=50.0)
        with (
            patch.object(metrics.psutil, "swap_memory", side_effect=OSError("boom")),
            patch.object(metrics.psutil, "virtual_memory", return_value=vm),
        ):
            score, measured_vm, swap = metrics.safe_pressure_score()

        self.assertAlmostEqual(score, 30.0)
        self.assertIs(measured_vm, vm)
        self.assertEqual((swap.total, swap.used, swap.percent), (0, 0, 0.0))

    def test_safe_pressure_score_passes_swap_through_when_available(self):
        vm = SimpleNamespace(total=8, used=4, percent=50.0)
        sw = SimpleNamespace(total=2, used=1, percent=25.0)
        with (
            patch.object(metrics.psutil, "swap_memory", return_value=sw),
            patch.object(metrics.psutil, "virtual_memory", return_value=vm),
        ):
            score, measured_vm, swap = metrics.safe_pressure_score()

        self.assertAlmostEqual(score, 40.0)
        self.assertIs(swap, sw)


if __name__ == "__main__":
    unittest.main()
