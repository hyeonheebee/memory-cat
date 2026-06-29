#!/usr/bin/env python3
"""메모리/디스크 측정 공유 모듈 (플랫폼 공통, GUI 의존 없음)."""
import psutil


def human_gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


def disk_usage():
    """하드 용량. macOS APFS는 데이터 볼륨이 사용자가 보는 값."""
    for path in ("/System/Volumes/Data", "/"):
        try:
            return psutil.disk_usage(path)
        except Exception:
            continue
    return psutil.disk_usage("/")


def pressure_score():
    """0~100 메모리 압박 점수. RAM 60% + 스왑 40% 가중."""
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return 0.6 * vm.percent + 0.4 * sw.percent, vm, sw


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
