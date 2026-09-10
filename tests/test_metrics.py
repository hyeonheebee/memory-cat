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

        # 스왑을 못 읽어도 점수가 흔들리면 안 된다. 예전에는 이 경우 점수가
        # 스왑 몫만큼 폭락해서, 메모리는 그대로인데 고양이가 갑자기 홀쭉해졌다.
        self.assertAlmostEqual(score, 50.0)
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

        self.assertAlmostEqual(score, 50.0)
        self.assertIs(swap, sw)


class PressureScoreTests(unittest.TestCase):
    """압박 점수는 **쓸 수 있는 RAM 이 얼마나 없는가** 만 본다.

    예전에는 ``0.6*RAM + 0.4*스왑`` 이었다. 그런데 macOS 의
    ``swap.percent`` 는 ``used/total`` 인데 커널이 스왑 파일을 수요에 맞춰
    만들고 지우기 때문에 분자와 분모가 같이 움직인다. 늘 80~90% 에 붙어
    있어서 정보가 없고, 게다가 **부호가 뒤집힌다** — 압박이 심해져 스왑
    파일이 커지면 분모만 커져서 percent 가 오히려 내려간다.

    실측(2026-09): 재부팅으로 스왑이 6.9GB→0.5GB 로 비워지자 옛 점수는
    80.9→67.9 로 여섯 칸이나 홀쭉해졌다. 같은 순간 실제 여유 RAM 은
    4.1GB→3.6GB 로 **줄었다**. 고양이가 거짓말을 한 것이다.
    """

    def test_score_is_exactly_the_ram_percentage(self):
        vm = SimpleNamespace(total=8, used=4, percent=63.8)
        sw = SimpleNamespace(total=2, used=1, percent=48.9)
        with (
            patch.object(metrics.psutil, "virtual_memory", return_value=vm),
            patch.object(metrics.psutil, "swap_memory", return_value=sw),
        ):
            score, measured_vm, swap = metrics.pressure_score()
        self.assertAlmostEqual(score, 63.8)
        self.assertIs(measured_vm, vm)
        self.assertIs(swap, sw)

    def test_swap_does_not_move_the_score(self):
        """스왑만 달라지면 점수는 그대로여야 한다."""
        vm = SimpleNamespace(total=8, used=4, percent=70.0)
        scores = []
        for swap_percent in (0.0, 50.0, 100.0):
            sw = SimpleNamespace(total=2, used=1, percent=swap_percent)
            with (
                patch.object(metrics.psutil, "virtual_memory", return_value=vm),
                patch.object(metrics.psutil, "swap_memory", return_value=sw),
            ):
                scores.append(metrics.pressure_score()[0])
        self.assertEqual(scores, [70.0, 70.0, 70.0])

    def test_swap_is_still_reported_for_diagnosis(self):
        """점수에서 뺐다고 스왑을 안 보는 건 아니다. 진단은 계속 쓴다."""
        vm = SimpleNamespace(total=8, used=4, percent=70.0)
        sw = SimpleNamespace(total=2, used=1, percent=99.0)
        with (
            patch.object(metrics.psutil, "virtual_memory", return_value=vm),
            patch.object(metrics.psutil, "swap_memory", return_value=sw),
        ):
            _, _, swap = metrics.pressure_score()
        self.assertEqual(swap.percent, 99.0)


class RamDisplayTests(unittest.TestCase):
    """정보창의 "RAM 70% · 12.6 / 18.0 GB" 가 자기모순이 되지 않는지.

    ``vm.used`` 는 macOS 에서 active+wired 라 압축 메모리를 빼는데,
    ``vm.percent`` 는 포함한다. 둘을 한 줄에 나란히 두면 percent 와 GB 가
    다른 것을 세게 되어 "RAM 70% · 9.0/18.0 GB"(=50%) 처럼 어긋난다.

    맥판과 윈도우판이 이 계산을 각자 하고 있었다. 이 저장소는 맥/윈도우가
    갈라져서 이미 두 번 사고를 냈으므로(v0.3.0 의 빈 정보창) 계산을 한 곳에
    둔다.
    """

    def test_displayed_used_is_total_minus_available(self):
        vm = SimpleNamespace(total=18_000_000_000, available=5_400_000_000,
                             used=9_000_000_000, percent=70.0)
        self.assertEqual(metrics.ram_used_for_display(vm), 12_600_000_000)

    def test_displayed_used_agrees_with_the_percent_beside_it(self):
        """GB 비율과 percent 가 같은 것을 세야 한다.

        이 검사가 깨지면 사용자가 정보창에서 서로 안 맞는 두 숫자를 본다.
        """
        for percent in (12.5, 40.0, 63.7, 70.0, 91.0):
            with self.subTest(percent=percent):
                total = 18_000_000_000
                available = int(total * (1 - percent / 100))
                vm = SimpleNamespace(
                    total=total,
                    available=available,
                    # vm.used 는 일부러 엉뚱한 값. 이걸 쓰면 검사가 깨져야 한다.
                    used=int(total * 0.5),
                    percent=percent,
                )
                shown = metrics.ram_used_for_display(vm)
                self.assertAlmostEqual(shown / total * 100, percent, places=6)


if __name__ == "__main__":
    unittest.main()
