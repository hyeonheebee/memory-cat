#!/usr/bin/env python3
"""GPT 기반 macOS 성능 진단과 보수적인 휴지통 이동 도우미."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple, Union

import psutil
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

import apppaths
from i18n import LANGUAGE_EN, LANGUAGE_KO, canonical_language, chonk_stage
from metrics import disk_usage, human_gb, pressure_score, top_memory_apps
from personality import DEFAULT_PERSONALITY, compile_personality


MODEL = "gpt-5.6-luna"
DOWNLOAD_MAX_AGE_DAYS = 30
MAX_RETURNED_ITEMS_PER_CATEGORY = 20

_HOME = Path.home()
BROWSER_CACHE_ROOTS = (
    _HOME / "Library/Caches/Google/Chrome",
    _HOME / "Library/Caches/com.apple.Safari",
    _HOME / "Library/Caches/Firefox",
    _HOME / "Library/Caches/Microsoft Edge",
    _HOME / "Library/Caches/BraveSoftware/Brave-Browser",
    _HOME / "Library/Caches/company.thebrowser.Browser",
)
TRASH_ROOT = _HOME / ".Trash"
DOWNLOADS_ROOT = _HOME / "Downloads"
DERIVED_DATA_ROOT = _HOME / "Library/Developer/Xcode/DerivedData"

CleanupCategory = Literal[
    "browser_cache", "trash", "old_downloads", "xcode_derived_data"
]

_CATEGORY_INFO: Dict[str, Dict[str, Dict[str, str]]] = {
    "browser_cache": {
        LANGUAGE_KO: {
            "label": "브라우저 캐시",
            "action": "선택한 브라우저 캐시를 macOS 휴지통으로 이동",
            "reason": "브라우저가 다시 만들 수 있는 캐시만 정리합니다.",
        },
        LANGUAGE_EN: {
            "label": "Browser cache",
            "action": "Move the selected browser cache to the macOS Trash",
            "reason": "Only cache data that the browser can recreate is considered.",
        },
    },
    "trash": {
        LANGUAGE_KO: {
            "label": "휴지통",
            "action": "휴지통 항목을 검토(이 모듈은 영구 삭제하거나 비우지 않음)",
            "reason": "이미 휴지통에 있는 항목은 사용자가 직접 확인할 수 있습니다.",
        },
        LANGUAGE_EN: {
            "label": "Trash",
            "action": "Review Trash items (this module never empties Trash or permanently deletes them)",
            "reason": "Items already in Trash remain available for the user to review.",
        },
    },
    "old_downloads": {
        LANGUAGE_KO: {
            "label": "30일 지난 다운로드",
            "action": "30일 동안 변경되지 않은 다운로드 항목을 macOS 휴지통으로 이동",
            "reason": "최근 파일은 건드리지 않고 오래된 다운로드만 후보로 삼습니다.",
        },
        LANGUAGE_EN: {
            "label": "Downloads older than 30 days",
            "action": "Move Downloads items unchanged for 30 days to the macOS Trash",
            "reason": "Recent downloads are left alone; only older items are considered.",
        },
    },
    "xcode_derived_data": {
        LANGUAGE_KO: {
            "label": "Xcode DerivedData",
            "action": "Xcode가 다시 생성할 수 있는 DerivedData를 macOS 휴지통으로 이동",
            "reason": "빌드 산출물은 필요할 때 Xcode가 다시 생성할 수 있습니다.",
        },
        LANGUAGE_EN: {
            "label": "Xcode DerivedData",
            "action": "Move Xcode-recreatable DerivedData to the macOS Trash",
            "reason": "Xcode can regenerate these build artifacts when needed.",
        },
    },
}

_BASE_SYSTEM_PROMPTS = {
    LANGUAGE_KO: """\
당신은 macOS 성능 진단 도우미입니다. 입력으로 주어진 디스크, RAM, 스왑,
상위 메모리 앱 수치만 근거로 한국어로 간결하게 진단하세요.

규칙:
- 모든 자연어 필드를 한국어로 씁니다.
- why_slow에는 관측된 수치에서 설명 가능한 원인만 최대 3개 적습니다.
- recommendations에는 입력 cleanup_candidates에 있고 estimated_bytes가 0보다 큰
  category만 사용합니다.
- 삭제나 정리 제안은 browser_cache, trash, old_downloads,
  xcode_derived_data 네 category 밖으로 절대 확장하지 않습니다.
- 앱 삭제, 문서 삭제, 시스템 파일 삭제, 임의 경로 삭제를 제안하지 않습니다.
- one_line_advice는 한 문장으로 씁니다.
- 용량 숫자는 로컬 코드가 계산하므로 추측하지 않습니다.
""",
    LANGUAGE_EN: """\
You are a macOS performance diagnostic assistant. Diagnose concisely using only the
provided disk, RAM, swap, and top-memory-app measurements.

Rules:
- Write every natural-language field in English.
- Put at most three causes supported by observed measurements in why_slow.
- Mention the exact provided chonk_stage naturally in the diagnosis.
- In recommendations, use only categories present in cleanup_candidates with
  estimated_bytes greater than zero.
- Never expand cleanup suggestions beyond browser_cache, trash, old_downloads,
  and xcode_derived_data.
- Never suggest deleting apps, documents, system files, or arbitrary paths.
- Write one_line_advice as one sentence.
- Local code calculates sizes; do not invent size estimates.
""",
}

# 기본 호출도 항상 명시적인 성격 톤을 가진다. 개별 호출은 아래 함수에서
# 같은 베이스 프롬프트에 선택된 성격을 다시 컴파일한다.
_SYSTEM_PROMPT = (
    f"{_BASE_SYSTEM_PROMPTS[LANGUAGE_KO]}\n\n"
    f"{compile_personality(DEFAULT_PERSONALITY, language=LANGUAGE_KO)}"
)


def system_prompt_for(
    personality: Optional[str] = None,
    custom_personality: Optional[str] = None,
    language: str = LANGUAGE_KO,
) -> str:
    """진단 안전 규칙과 선택한 뚱냥이 성격을 하나의 시스템 프롬프트로 만든다."""
    lang = canonical_language(language)
    if lang == LANGUAGE_KO and personality is None and custom_personality is None:
        return _SYSTEM_PROMPT
    return (
        f"{_BASE_SYSTEM_PROMPTS[lang]}\n\n"
        f"{compile_personality(personality, custom_personality, language=lang)}"
    )


def _category_info(category: str, language: str) -> Dict[str, str]:
    return _CATEGORY_INFO[category][canonical_language(language)]


class _AIRecommendation(BaseModel):
    category: CleanupCategory
    reason: str


class _AIDiagnosis(BaseModel):
    why_slow: List[str]
    recommendations: List[_AIRecommendation]
    one_line_advice: str


def collect_metrics(language: str = LANGUAGE_KO) -> Dict[str, Any]:
    """``metrics.py``의 디스크/RAM/상위 앱 데이터를 JSON 형태로 수집한다."""
    measurement_warnings: List[str] = []
    disk = disk_usage()
    try:
        score, vm, swap = pressure_score()
    except OSError:
        # 일부 psutil/macOS 조합은 swap_memory()만 OSError를 낸다. RAM 측정은
        # 유지하되 알 수 없는 스왑을 사용 중이라고 추측하지 않는다.
        vm = psutil.virtual_memory()
        swap = SimpleNamespace(total=0, used=0, percent=0.0)
        score = 0.6 * vm.percent
        measurement_warnings.append("swap_unavailable")
    try:
        apps = top_memory_apps()
    except (OSError, PermissionError):
        apps = []
        measurement_warnings.append("top_memory_apps_unavailable")
    return {
        "disk": {
            "total_bytes": int(disk.total),
            "used_bytes": int(disk.used),
            "free_bytes": int(disk.free),
            "percent": float(disk.percent),
            "chonk_stage": chonk_stage(float(disk.percent), language),
        },
        "ram": {
            "total_bytes": int(vm.total),
            "available_bytes": int(vm.available),
            "used_bytes": int(vm.used),
            "percent": float(vm.percent),
            "pressure_score": round(float(score), 1),
        },
        "swap": {
            "total_bytes": int(swap.total),
            "used_bytes": int(swap.used),
            "percent": float(swap.percent),
        },
        "top_memory_apps": [
            {
                "name": name,
                "rss_bytes": int(rss),
                "rss": human_gb(rss),
            }
            for name, rss in apps
        ],
        "measurement_warnings": measurement_warnings,
    }


def _display_size(size_bytes: int) -> str:
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.1f} GB"
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def _scan_path(path: Path) -> Tuple[int, float, int, bool]:
    """심볼릭 링크를 따라가지 않고 크기/최신 mtime/파일 수를 센다."""
    size_bytes = 0
    newest_mtime = 0.0
    file_count = 0
    complete = True
    pending = [path]

    while pending:
        current = pending.pop()
        try:
            stat = current.lstat()
        except OSError:
            complete = False
            continue

        newest_mtime = max(newest_mtime, stat.st_mtime)
        if current.is_symlink() or not current.is_dir():
            size_bytes += stat.st_size
            file_count += 1
            continue

        try:
            with os.scandir(current) as entries:
                pending.extend(Path(entry.path) for entry in entries)
        except OSError:
            complete = False

    return size_bytes, newest_mtime, file_count, complete


def _candidate_item(path: Path) -> Optional[Dict[str, Any]]:
    if path.is_symlink():
        return None
    size, newest_mtime, file_count, complete = _scan_path(path)
    if not complete or size <= 0:
        return None
    return {
        "path": str(path),
        "bytes": size,
        "size": _display_size(size),
        "file_count": file_count,
        "newest_mtime": newest_mtime,
    }


def _children(path: Path) -> List[Path]:
    try:
        return sorted(path.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return []


def collect_cleanup_candidates(
    now: Optional[float] = None,
    language: str = LANGUAGE_KO,
) -> List[Dict[str, Any]]:
    """화이트리스트 네 종류만 스캔하고 실제 바이트 수를 계산한다."""
    now = time.time() if now is None else now
    cutoff = now - DOWNLOAD_MAX_AGE_DAYS * 24 * 60 * 60
    grouped: Dict[str, List[Dict[str, Any]]] = {
        category: [] for category in _CATEGORY_INFO
    }

    for root in BROWSER_CACHE_ROOTS:
        if root.exists():
            item = _candidate_item(root)
            if item:
                grouped["browser_cache"].append(item)

    for path in _children(TRASH_ROOT):
        item = _candidate_item(path)
        if item:
            grouped["trash"].append(item)

    for path in _children(DOWNLOADS_ROOT):
        item = _candidate_item(path)
        if item and item["newest_mtime"] <= cutoff:
            grouped["old_downloads"].append(item)

    if DERIVED_DATA_ROOT.exists():
        item = _candidate_item(DERIVED_DATA_ROOT)
        if item:
            grouped["xcode_derived_data"].append(item)

    candidates: List[Dict[str, Any]] = []
    for category in _CATEGORY_INFO:
        info = _category_info(category, language)
        items = sorted(
            grouped[category], key=lambda item: (-item["bytes"], item["path"])
        )
        total = sum(item["bytes"] for item in items)
        candidates.append(
            {
                "category": category,
                "label": info["label"],
                "estimated_bytes": total,
                "estimated_size": _display_size(total),
                "item_count": len(items),
                "items": items[:MAX_RETURNED_ITEMS_PER_CATEGORY],
                "omitted_item_count": max(
                    0, len(items) - MAX_RETURNED_ITEMS_PER_CATEGORY
                ),
            }
        )
    return candidates


def _candidate_prompt(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """API에는 로컬 경로를 빼고 카테고리별 합계만 보낸다."""
    return [
        {
            "category": candidate["category"],
            "label": candidate["label"],
            "estimated_bytes": candidate["estimated_bytes"],
            "estimated_size": candidate["estimated_size"],
            "item_count": candidate["item_count"],
        }
        for candidate in candidates
    ]


def _fallback_ai(
    snapshot: Mapping[str, Any],
    candidates: List[Dict[str, Any]],
    language: str = LANGUAGE_KO,
) -> _AIDiagnosis:
    lang = canonical_language(language)
    disk = snapshot.get("disk", {})
    ram = snapshot.get("ram", {})
    apps = snapshot.get("top_memory_apps", [])
    disk_percent = float(disk.get("percent", 0))
    pressure = float(ram.get("pressure_score", ram.get("percent", 0)))
    ram_total = int(ram.get("total_bytes", 0))
    why: List[str] = []

    if lang == LANGUAGE_EN:
        if disk_percent >= 90:
            why.append(
                f"Disk usage is {disk_percent:.0f}%, so limited free space may be slowing work down."
            )
        elif disk_percent >= 80:
            why.append(
                f"Disk usage is high at {disk_percent:.0f}%, which can constrain temporary files and swap space."
            )
        if pressure >= 80:
            why.append(
                f"Memory pressure is {pressure:.0f}, so swapping may be adding latency."
            )
        elif pressure >= 65:
            why.append(f"Memory pressure is somewhat high at {pressure:.0f}.")
    else:
        if disk_percent >= 90:
            why.append(
                f"디스크 사용률이 {disk_percent:.0f}%라 여유 공간 부족이 작업 속도를 떨어뜨릴 수 있습니다."
            )
        elif disk_percent >= 80:
            why.append(
                f"디스크 사용률이 {disk_percent:.0f}%로 높아 임시 파일과 스왑 공간이 빠듯할 수 있습니다."
            )
        if pressure >= 80:
            why.append(
                f"메모리 압박 점수가 {pressure:.0f}점이라 스왑 사용으로 지연이 생길 수 있습니다."
            )
        elif pressure >= 65:
            why.append(f"메모리 압박 점수가 {pressure:.0f}점으로 다소 높습니다.")

    if apps:
        top = apps[0]
        rss = int(top.get("rss_bytes", 0))
        if rss > 0 and (ram_total == 0 or rss >= ram_total * 0.1):
            if lang == LANGUAGE_EN:
                why.append(
                    f"{top.get('name', 'The top app')} is using {_display_size(rss)} of memory."
                )
            else:
                why.append(
                    f"{top.get('name', '상위 앱')}이(가) {_display_size(rss)}의 메모리를 사용 중입니다."
                )

    if not why:
        why.append(
            "No clear disk or memory bottleneck is visible in the current measurements."
            if lang == LANGUAGE_EN
            else "현재 수치만으로는 뚜렷한 디스크나 메모리 병목이 보이지 않습니다."
        )

    recommendations = [
        _AIRecommendation(
            category=candidate["category"],
            reason=_category_info(candidate["category"], lang)["reason"],
        )
        for candidate in sorted(
            candidates,
            key=lambda candidate: (-candidate["estimated_bytes"], candidate["category"]),
        )
        if candidate["estimated_bytes"] > 0
    ]

    if lang == LANGUAGE_EN:
        if disk_percent >= 80:
            advice = "Review the largest allowlisted items first, move approved ones to Trash, then empty it yourself."
        elif pressure >= 65:
            advice = "Save your work, then close unneeded apps starting with the largest memory users."
        else:
            advice = "Avoid unnecessary cleanup for now and keep watching disk and memory trends."
    elif disk_percent >= 80:
        advice = "큰 화이트리스트 항목부터 휴지통으로 옮긴 뒤 직접 확인하고 비우세요."
    elif pressure >= 65:
        advice = "메모리를 많이 쓰는 앱의 작업을 저장한 뒤 필요 없는 앱부터 종료해 보세요."
    else:
        advice = "지금은 무리하게 지우지 말고 용량과 메모리 추이만 지켜보세요."

    return _AIDiagnosis(
        why_slow=why[:3],
        recommendations=recommendations,
        one_line_advice=advice,
    )


def _assemble_result(
    diagnosis: _AIDiagnosis,
    candidates: List[Dict[str, Any]],
    source: str,
    fallback_reason: Optional[str] = None,
    language: str = LANGUAGE_KO,
    stage: Optional[str] = None,
) -> Dict[str, Any]:
    lang = canonical_language(language)
    by_category = {
        candidate["category"]: candidate
        for candidate in candidates
        if candidate["estimated_bytes"] > 0
    }
    recommendations: List[Dict[str, Any]] = []
    seen = set()
    for recommendation in diagnosis.recommendations:
        category = recommendation.category
        if category in seen or category not in by_category:
            continue
        seen.add(category)
        candidate = by_category[category]
        info = _category_info(category, lang)
        recommendations.append(
            {
                **candidate,
                "reason": recommendation.reason.strip() or info["reason"],
                "action": info["action"],
            }
        )

    estimated_bytes = sum(
        recommendation["estimated_bytes"] for recommendation in recommendations
    )
    why_slow = list(diagnosis.why_slow)
    if lang == LANGUAGE_EN and stage:
        all_text = " ".join(why_slow + [diagnosis.one_line_advice])
        if stage not in all_text:
            marker = f"Chonk stage: {stage}."
            if why_slow:
                why_slow[0] = f"{why_slow[0]} {marker}"
            else:
                why_slow = [marker]
    return {
        "why_slow": why_slow,
        "cleanup_recommendations": recommendations,
        "estimated_reclaimable_bytes": estimated_bytes,
        "estimated_reclaimable": _display_size(estimated_bytes),
        "reclaim_requires_emptying_trash": estimated_bytes > 0,
        "one_line_advice": diagnosis.one_line_advice.strip(),
        "source": source,
        "model": MODEL,
        "fallback_reason": fallback_reason,
    }


def _load_api_key() -> Optional[str]:
    # 설치된 앱은 사용자 폴더의 .env 를, 저장소에서 바로 돌릴 때는 소스 옆의
    # .env 를 읽는다. override=False 라서 먼저 읽힌 쪽이 이긴다.
    for candidate in apppaths.dotenv_candidates():
        load_dotenv(candidate, override=False)
    return os.getenv("OPENAI_API_KEY")


def diagnose(
    metrics_snapshot: Optional[Mapping[str, Any]] = None,
    personality: Optional[str] = None,
    custom_personality: Optional[str] = None,
    language: str = LANGUAGE_KO,
) -> Dict[str, Any]:
    """성능 원인과 안전한 정리 추천을 JSON 직렬화 가능한 dict로 반환한다.

    API 키 누락, 네트워크 오류, 모델/스키마 오류는 모두 같은 입력에 같은
    결과를 내는 로컬 fallback으로 처리한다.
    """
    lang = canonical_language(language)
    snapshot = (
        dict(metrics_snapshot)
        if metrics_snapshot is not None
        else collect_metrics(language=lang)
    )
    disk = dict(snapshot.get("disk", {}))
    stage = chonk_stage(float(disk.get("percent", 0)), lang)
    disk["chonk_stage"] = stage
    snapshot["disk"] = disk
    candidates = collect_cleanup_candidates(language=lang)
    api_key = _load_api_key()
    if not api_key:
        fallback = _fallback_ai(snapshot, candidates, language=lang)
        return _assemble_result(
            fallback,
            candidates,
            "fallback",
            fallback_reason="missing_api_key",
            language=lang,
            stage=stage,
        )

    try:
        client = OpenAI(api_key=api_key, timeout=20.0, max_retries=1)
        response = client.responses.parse(
            model=MODEL,
            instructions=system_prompt_for(
                personality, custom_personality, language=lang
            ),
            input=json.dumps(
                {
                    "metrics": snapshot,
                    "cleanup_candidates": _candidate_prompt(candidates),
                },
                ensure_ascii=False,
                default=str,
            ),
            text_format=_AIDiagnosis,
            text={"verbosity": "low"},
            reasoning={"effort": "low"},
            max_output_tokens=800,
            store=False,
        )
        if response.output_parsed is None:
            raise ValueError("구조화된 진단 결과가 없습니다.")
        return _assemble_result(
            response.output_parsed,
            candidates,
            "openai",
            language=lang,
            stage=stage,
        )
    except Exception:
        fallback = _fallback_ai(snapshot, candidates, language=lang)
        return _assemble_result(
            fallback,
            candidates,
            "fallback",
            fallback_reason="api_error",
            language=lang,
            stage=stage,
        )


def _normalized_existing_path(path: Union[str, os.PathLike[str]]) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    if not target.exists() and not target.is_symlink():
        raise FileNotFoundError(str(target))
    if target.is_symlink():
        raise ValueError("심볼릭 링크는 안전한 정리 대상이 아닙니다.")
    return target.resolve(strict=True)


def _is_within(path: Path, root: Path, allow_root: bool = True) -> bool:
    # 화이트리스트 루트 자체가 다른 위치로 바뀐 경우에는 보수적으로 거부한다.
    if root.is_symlink():
        return False
    try:
        relative = path.relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return allow_root or bool(relative.parts)


def _whitelisted_category(path: Path, now: Optional[float] = None) -> Optional[str]:
    for root in BROWSER_CACHE_ROOTS:
        if _is_within(path, root):
            return "browser_cache"

    if _is_within(path, TRASH_ROOT, allow_root=False):
        return "trash"

    if _is_within(path, DERIVED_DATA_ROOT):
        return "xcode_derived_data"

    if _is_within(path, DOWNLOADS_ROOT, allow_root=False):
        _, newest_mtime, _, complete = _scan_path(path)
        current_time = time.time() if now is None else now
        cutoff = current_time - DOWNLOAD_MAX_AGE_DAYS * 24 * 60 * 60
        if complete and newest_mtime <= cutoff:
            return "old_downloads"
    return None


def _trash_via_foundation(path: Path) -> str:
    if sys.platform != "darwin":
        raise RuntimeError("safe_trash는 macOS에서만 사용할 수 있습니다.")

    from Foundation import NSFileManager, NSURL

    manager = NSFileManager.defaultManager()
    url = NSURL.fileURLWithPath_(str(path))
    success, resulting_url, error = (
        manager.trashItemAtURL_resultingItemURL_error_(url, None, None)
    )
    if not success:
        detail = error.localizedDescription() if error is not None else "알 수 없는 오류"
        raise OSError(f"macOS 휴지통 이동 실패: {detail}")
    return resulting_url.path() if resulting_url is not None else str(TRASH_ROOT)


def safe_trash(path: Union[str, os.PathLike[str]]) -> str:
    """화이트리스트 경로를 macOS 휴지통으로만 이동한다.

    영구 삭제 API는 사용하지 않는다. 이미 ``~/.Trash`` 안에 있는 항목은
    다시 삭제하지 않고 현재 경로를 그대로 반환한다.
    """
    target = _normalized_existing_path(path)
    category = _whitelisted_category(target)
    if category is None:
        raise ValueError(
            "허용된 정리 대상이 아닙니다: 브라우저 캐시, 휴지통, "
            "30일 지난 다운로드, Xcode DerivedData만 가능합니다."
        )
    if category == "trash":
        return str(target)
    return _trash_via_foundation(target)


if __name__ == "__main__":
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2))
