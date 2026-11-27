#!/usr/bin/env python3
"""메모리/디스크 측정 공유 모듈 (플랫폼 공통, GUI 의존 없음)."""
import math
import os
import sys
from types import SimpleNamespace

import psutil


def human_gb(n):
    return f"{n / 1024 ** 3:.1f} GB"


def disk_usage():
    """하드 용량. macOS APFS는 데이터 볼륨이 사용자가 보는 값.

    윈도우의 ``"/"`` 는 현재 작업 디렉터리가 있는 드라이브의 루트다. exe 를
    D:\\Downloads 에서 띄우면 D: 를 보게 되는데, windows_cat 은 C: 라벨을
    쓰므로 디스크 수치와 진단이 서로 다른 드라이브를 보고 어긋난다.
    ``SystemDrive`` (보통 C:) 를 먼저 본다.
    """
    usage = None
    if sys.platform == "win32":
        paths = (os.environ.get("SystemDrive", "C:") + "\\",
                 "/System/Volumes/Data", "/")
    else:
        paths = ("/System/Volumes/Data", "/")
    for path in paths:
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


#: 고양이 몸집을 무엇으로 정할지.
#:
#: 메모리(책상)와 디스크(창고)는 성격이 다르다. 메모리는 앱을 닫으면 몇 초
#: 안에 내려가고, 디스크는 파일을 지워야 내려간다. 그래서 같은 그림이라도
#: 무엇에 반응하느냐에 따라 전혀 다른 물건이 된다. 사용자가 고른다.
SOURCE_MEMORY = "memory"
SOURCE_DISK = "disk"
SOURCE_MAX = "max"
SIZE_SOURCES = (SOURCE_MEMORY, SOURCE_DISK, SOURCE_MAX)

#: 설정에 값이 없거나 모르는 값일 때. 이름이 Memory Cat 인데 v0.2.0 까지
#: 디스크로 돌고 있었다. 느려짐의 실제 원인도 메모리 쪽이라 메모리로 둔다.
DEFAULT_SIZE_SOURCE = SOURCE_MEMORY


def size_percent(source=None, memory=None, disk=None):
    """고양이 몸집을 정할 0~100 값. 어느 지표를 볼지는 ``source`` 가 정한다.

    ``memory``/``disk`` 를 주면 그 값을 쓰고 다시 재지 않는다. 화면 갱신은
    이미 두 지표를 다 재 놓고 들어오므로, 여기서 또 재면 1초마다 프로세스
    목록을 두 번 훑게 된다.

    측정이 실패해도 예외를 내지 않는다. 숫자를 못 읽었다고 고양이가 화면에서
    사라지면 안 되므로, 못 읽은 지표는 0 으로 두고 남은 것으로 정한다.
    """
    if source not in SIZE_SOURCES:
        source = DEFAULT_SIZE_SOURCE

    def _memory():
        if memory is not None:
            return float(memory)
        try:
            return float(safe_pressure_score()[0])
        except Exception:
            return 0.0

    def _disk():
        if disk is not None:
            return float(disk)
        try:
            return float(disk_usage().percent)
        except Exception:
            return 0.0

    if source == SOURCE_MEMORY:
        return _memory()
    if source == SOURCE_DISK:
        return _disk()
    return max(_memory(), _disk())


#: 사진으로 만든 테마의 그림 여섯 장이 각각 차지하는 프레임 구간. 40개 파일
#: 중 서로 다른 그림은 여섯 장뿐이고 나머지는 복제본이다. 기본 테마
#: `cute`·`simple` 도, `vision_theme` 이 반려동물 사진으로 만드는 테마도
#: 그렇다 — `import_theme.save_theme_frames` 가 `smooth=False` 로 가장 가까운
#: 단계를 그대로 쓴다. 섞으면 귀와 눈이 겹쳐 유령처럼 보이기 때문이다.
_PICTURE_FRAMES = ((0, 3), (4, 11), (12, 19), (20, 27), (28, 35), (36, 39))

#: 그 여섯 장을 어느 메모리 값에서 바꿀지. `i18n.chonk_stage` 의 영어 문턱과
#: **같은 값이다.** 몸과 이름이 같은 지점에서 바뀌어야 "HEFTYCHONK" 이 뜨는
#: 순간 몸이 그 그림이 된다.
_MEMORY_EDGES = (0.0, 60.0, 70.0, 80.0, 90.0, 96.0, 100.0)

#: 프레임 번호를 0~100 으로 되돌릴 때 쓰는 마지막 번호. 사진 테마가 40장
#: 파일로 나오므로 39 다.
_LAST_FRAME = 39.0


def body_percent(percent):
    """잰 값 0~100 을 몸집 0~100 으로 옮긴다. **메모리·디스크가 같은 자를 쓴다.**

    메모리 사용률은 0 근처로 내려가지 않는다 — 도는 맥은 늘 절반쯤 쓰고
    있다. 0~100 을 그대로 옮기면 그림 여섯 장 중 두 장밖에 안 쓰인다.
    실측(18GB, macOS 15.4.1): 관측된 값이 61~80% 였고 재부팅 직후에도 80%
    였다.

    그래서 메모리 구간을 그림 구간에 하나씩 대응시킨다. 구간 경계를 이름
    문턱에 맞춰 두었으므로 몸과 이름이 같은 지점에서 바뀐다. 구간 **안에서는**
    직선이라 `derpy` 처럼 진짜 40장인 테마는 계속 부드럽게 움직인다.

    디스크도 같은 자를 쓴다. 앱은 이미 디스크에도 같은 문턱으로 이름을
    붙인다(`brain.collect_metrics` 가 `chonk_stage(disk.percent)`). 자를
    따로 쓰면 ``max`` 가 깨진다 — 메모리 71.5% 가 디스크 50% 에 지고,
    "둘 중 더 찬 쪽" 이 사실상 디스크 전용이 된다.

    화면에 적히는 숫자는 이 값이 아니다. 정보창의 "RAM 65%" 와 기분 줄은
    잰 그대로를 쓴다 — 몸집을 보기 좋게 만들자고 숫자를 바꾸면 두 개가
    서로 다른 말을 하게 된다.
    """
    percent = min(max(float(percent), 0.0), 100.0)
    last = len(_PICTURE_FRAMES) - 1
    for i, (first_frame, final_frame) in enumerate(_PICTURE_FRAMES):
        lo, hi = _MEMORY_EDGES[i], _MEMORY_EDGES[i + 1]
        # 경계값은 **위쪽** 구간이 가져간다. 이름도 그렇게 바뀐다
        # (`chonk_stage` 가 `percent < 60` 이면 첫 단계다). 여기서 아래쪽이
        # 가져가면 90% 에서 이름은 MEGACHONKER 인데 몸은 그 전 그림이 된다.
        if percent < hi or i == last:
            span = final_frame - first_frame
            t = 0.0 if hi == lo else (percent - lo) / (hi - lo)
            frame = first_frame + span * min(max(t, 0.0), 1.0)
            return frame / _LAST_FRAME * 100.0
    return 100.0


def body_size_percent(source=None, memory=None, disk=None):
    """몸집을 정할 0~100. **눈금을 맞춘 뒤에** 지표를 고른다.

    :func:`size_percent` 와 순서가 다르다. 저쪽은 잰 값끼리 비교해서 "더 찬
    쪽" 을 고르고, 이쪽은 각자 몸집 눈금으로 옮긴 다음 "더 뚱뚱한 쪽" 을
    고른다. 순서를 섞으면 ``max`` 가 깨진다 — 메모리만 눈금을 다시 매긴
    채로 잰 값끼리 비교하면, 고른 결과가 두 선택지 **어느 쪽보다도** 뚱뚱해
    진다. 실측: 메모리 71.5% / 디스크 50% 에서 memory=20, disk=20 인데
    max=28 이 나왔다. 메뉴에서 바꾸기만 했는데 고양이가 8프레임 부푼다.

    화면에 적히는 숫자는 이 값이 아니다. 그건 :func:`size_percent` 가 내는
    잰 값을 쓴다.
    """
    if source not in SIZE_SOURCES:
        source = DEFAULT_SIZE_SOURCE
    mem = body_percent(size_percent(SOURCE_MEMORY, memory=memory, disk=disk))
    dsk = body_percent(size_percent(SOURCE_DISK, memory=memory, disk=disk))
    if source == SOURCE_MEMORY:
        return mem
    if source == SOURCE_DISK:
        return dsk
    return max(mem, dsk)


def size_reading(source, memory, disk):
    """화면 갱신 한 번에 필요한 몸집 판단을 한꺼번에. 맥·윈도우 공용.

    - ``percent``: 기분 줄(이름·퍼센트)에 쓸 **잰 값**. :func:`size_percent`
    - ``body``: 그림을 고를 몸집 0~100. :func:`body_size_percent`
    - ``disk_first``: 첫 줄(큰 글씨)에 디스크를 적을지. 큰 숫자가 몸집을
      설명해야 한다 — 메모리로 부풀었는데 디스크가 크게 적혀 있으면 왜
      뚱뚱한지 읽을 수 없다. 비교는 **몸집을 고른 것과 같은 자로** 한다.
      잰 값끼리 비교하면 디스크가 정한 몸집인데 첫 줄엔 메모리가 적힌다.
    """
    if source not in SIZE_SOURCES:
        source = DEFAULT_SIZE_SOURCE
    disk_first = source == SOURCE_DISK or (
        source == SOURCE_MAX and body_percent(disk) >= body_percent(memory))
    return SimpleNamespace(
        source=source,
        percent=size_percent(source, memory=memory, disk=disk),
        body=body_size_percent(source, memory=memory, disk=disk),
        disk_first=disk_first,
    )
