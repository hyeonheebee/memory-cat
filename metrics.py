#!/usr/bin/env python3
"""메모리/디스크 측정 공유 모듈 (플랫폼 공통, GUI 의존 없음)."""
import math
import os
from types import SimpleNamespace

import psutil


def human_gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


def disk_usage():
    """하드 용량. macOS APFS는 데이터 볼륨이 사용자가 보는 값."""
    usage = None
    for path in ("/System/Volumes/Data", "/"):
        try:
            usage = psutil.disk_usage(path)
            break
        except Exception:
            continue
    if usage is None:
        usage = psutil.disk_usage("/")

    raw_percent = os.environ.get("MEMORY_CAT_DEMO_DISK_PERCENT")
    if raw_percent is None:
        return usage
    try:
        percent = float(raw_percent)
    except (TypeError, ValueError):
        return usage
    if not math.isfinite(percent):
        return usage

    percent = min(100.0, max(0.0, percent))
    used = int(round(usage.total * percent / 100.0))
    return usage._replace(
        used=used,
        free=usage.total - used,
        percent=percent,
    )


def pressure_score():
    """0~100 메모리 압박 점수 = 쓸 수 있는 RAM 이 얼마나 없는가.

    ``0`` 이면 RAM 이 통째로 비어 있고, ``100`` 이면 숨 쉴 곳이 없다.
    ``psutil`` 의 ``vm.percent`` 가 정확히 ``(total - available) / total`` 이고
    macOS 에서 ``available = inactive + free`` 이므로, 압축 메모리는 이미 이
    값에 반영되어 있다.

    **스왑은 점수에 넣지 않는다.** ``swap.percent`` 는 ``used/total`` 인데
    macOS 는 스왑 파일을 수요에 맞춰 만들고 지운다. 분자와 분모가 같이
    움직여서 늘 80~90% 에 붙어 있고, RAM 압박과의 상관이 사실상 없다. 게다가
    **부호가 뒤집힌다** — 압박이 심해져 커널이 스왑 파일을 키우면 분모만
    커져서 percent 가 오히려 내려간다.

    실측(2026-09, 18GB 맥): 재부팅으로 스왑이 6.9GB→0.5GB 로 비워지자 옛
    가중 점수는 80.9→67.9 로 여섯 칸이나 홀쭉해졌다. 그런데 같은 순간 실제
    여유 RAM 은 4.1GB→3.6GB 로 **줄었다**. 사용자에게 거짓을 보여 준 것이다.

    스왑 값 자체는 계속 돌려준다. 진단(:mod:`brain`)은 "왜 느린가" 를
    설명해야 하므로 여전히 필요하다. 다만 **몸집을 정하는 데는 쓰지 않는다.**
    """
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return float(vm.percent), vm, sw


def ram_used_for_display(vm):
    """정보창에 적을 "쓰는 중" 바이트. ``vm.percent`` 와 같은 것을 센다.

    ``vm.used`` 를 쓰면 안 된다. macOS 에서 그건 active+wired 라 압축 메모리를
    빼는데 ``vm.percent`` 는 포함한다. 한 줄에 나란히 두면 "RAM 70% ·
    9.0/18.0 GB"(=50%) 처럼 자기모순이 된다.

    맥판과 윈도우판이 각자 계산하던 것을 여기로 모았다. 이 저장소는 두 판이
    갈라져서 이미 사고를 냈다 — v0.3.0 에서 공용 문구를 맥만 고치는 바람에
    윈도우 정보창이 통째로 비었다.
    """
    return vm.total - vm.available


def safe_pressure_score():
    """스왑 조회가 실패해도 같은 점수를 돌려준다.

    일부 psutil/macOS 조합은 ``swap_memory()`` 만 OSError 를 낸다. 점수가 이미
    RAM 만 보므로 스왑을 못 읽어도 값이 달라지지 않는다 — 예전에는 이때 점수가
    스왑 몫만큼 폭락해서, 메모리는 그대로인데 고양이가 갑자기 홀쭉해졌다.
    ``brain.collect_metrics`` 와 같은 처리를 GUI 타이머에서도 쓰기 위한 것.
    """
    try:
        return pressure_score()
    except OSError:
        vm = psutil.virtual_memory()
        sw = SimpleNamespace(total=0, used=0, percent=0.0)
        return float(vm.percent), vm, sw


def top_memory_apps(limit=5):
    """앱(.app) 단위로 RSS 합산해서 상위 N개."""
    totals = {}
    for p in psutil.process_iter(["name", "memory_info", "exe"]):
        try:
            m = p.info["memory_info"]
            if not m:
                continue
            exe = p.info.get("exe") or ""
            name = p.info.get("name") or "?"
            if ".app/" in exe:
                name = exe.split(".app/")[0].split("/")[-1]
            totals[name] = totals.get(name, 0) + m.rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
