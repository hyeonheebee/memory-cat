#!/usr/bin/env python3
"""macOS 언어 감지와 Memory Cat의 한국어/영어 문자열."""

from typing import Iterable, Optional


LANGUAGE_AUTO = "auto"
LANGUAGE_KO = "ko"
LANGUAGE_EN = "en"
LANGUAGE_OVERRIDES = (LANGUAGE_AUTO, LANGUAGE_KO, LANGUAGE_EN)

CHONK_STAGES_EN = (
    "A fine boi",
    "He chomnk",
    "A heckin' chonker",
    "HEFTYCHONK",
    "MEGACHONKER",
    "OH LAWD HE COMIN",
)

_STRINGS = {
    "ko": {
        "disk": "디스크",
        "ram": "램",
        "swap": "스왑",
        "free": "여유",
        "mood": "기분",
        "mood_detail": "기분: {mood}  (디스크 {percent}%)",
        "disk_detail": "💾 디스크 {percent:.0f}%  ·  {used} / {total}  (여유 {free})",
        "ram_detail": "🧠 RAM {percent:.0f}%  ·  {used} / {total}",
        "swap_detail": "스왑 {percent:.0f}%  ·  {used} / {total}",
        "memory_apps": "─ 메모리 먹는 앱 ─",
        "diagnosis_empty": "진단 결과를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.",
        "diagnosis_error": "진단 데이터를 읽는 중 문제가 생겼습니다.",
        "retry_later": "잠시 후 다시 시도해 주세요.",
        "personality_changed_title": "뚱냥이 성격 변경",
        "personality_changed_body": "이제 {personality} 말투로 진단할게요.",
        "custom_title": "뚱냥이 성격을 직접 알려 주세요",
        "custom_hint": "예: 다정하지만 핵심만 말하고, 말끝에 냥을 붙여줘",
        "save": "저장",
        "cancel": "취소",
        "custom_empty_title": "성격을 저장하지 않았어요",
        "custom_empty_body": "한 문장 이상 입력해 주세요.",
        "custom_saved_title": "커스텀 성격 저장",
        "diagnosis_already_title": "🧠 이미 진단 중이에요",
        "diagnosis_already_body": "뚱냥이가 숫자를 살펴보고 있습니다.",
        "diagnosis_running_title": "🧠 왜 느린지 보는 중",
        "diagnosis_running_body": "고양이가 디스크와 메모리를 살펴보고 있어요.",
        "diagnosis_result_title": "🧠 뚱냥이 진단",
        "confirm": "확인",
        "cleanup_review_title": "안전한 정리 후보를 볼까요?",
        "cleanup_review_body": (
            "화이트리스트 항목 {count}개를 하나씩 확인합니다. "
            "동의한 항목만 macOS 휴지통으로 이동하며 영구 삭제하지 않습니다."
        ),
        "review_items": "항목별 검토",
        "later": "나중에",
        "unknown_size": "크기 알 수 없음",
        "cleanup_candidate": "정리 후보",
        "trash_review_note": "이미 휴지통 안에 있어 확인만 하며, 영구 삭제하지 않습니다.",
        "move_question": "이 항목을 macOS 휴지통으로 이동할까요?",
        "move_to_trash": "휴지통으로 이동",
        "skip": "건너뛰기",
        "summary_moved": "{count}개를 휴지통으로 이동",
        "summary_in_trash": "휴지통 안 {count}개 확인",
        "summary_skipped": "{count}개 건너뜀",
        "summary_failed": "{count}개 이동 실패",
        "summary_none": "변경한 항목이 없습니다.",
        "summary_reclaim_note": " 공간은 휴지통을 직접 비운 뒤 확보됩니다.",
        "cleanup_result_title": "🧹 정리 결과",
        "menu_diagnosing": "🧠 진단 중…",
        "menu_diagnose": "🧠 왜 느려?",
        "menu_theme": "테마",
        "menu_size": "크기",
        "menu_personality": "성격",
        "menu_custom": "직접 입력…",
        "menu_language": "언어",
        "menu_refresh": "새로고침",
        "menu_quit": "종료",
        "language_auto": "자동 ({language})",
        "language_ko": "한국어",
        "language_en": "English",
        "language_changed_title": "언어 변경",
        "language_changed_body": "표시 언어를 {language}(으)로 바꿨어요.",
        "theme_cute": "귀여운",
        "theme_simple": "단순한",
        "theme_madness": "광기",
        "theme_derpy": "경각심",
        "size_small": "작게",
        "size_medium": "보통",
        "size_large": "크게",
        "size_king": "왕",
    },
    "en": {
        "disk": "Disk",
        "ram": "RAM",
        "swap": "Swap",
        "free": "free",
        "mood": "Chonk",
        "mood_detail": "Chonk: {mood}  (Disk {percent}%)",
        "disk_detail": "💾 Disk {percent:.0f}%  ·  {used} / {total}  ({free} free)",
        "ram_detail": "🧠 RAM {percent:.0f}%  ·  {used} / {total}",
        "swap_detail": "Swap {percent:.0f}%  ·  {used} / {total}",
        "memory_apps": "─ Top memory apps ─",
        "diagnosis_empty": "I couldn't produce a diagnosis. Please try again shortly.",
        "diagnosis_error": "Something went wrong while reading the diagnostic data.",
        "retry_later": "Please try again shortly.",
        "personality_changed_title": "Cat personality changed",
        "personality_changed_body": "Future diagnoses will use the {personality} voice.",
        "custom_title": "Describe your cat's personality",
        "custom_hint": "Example: Be kind, lead with the key point, and end sentences with meow.",
        "save": "Save",
        "cancel": "Cancel",
        "custom_empty_title": "Personality not saved",
        "custom_empty_body": "Please enter at least one sentence.",
        "custom_saved_title": "Custom personality saved",
        "diagnosis_already_title": "🧠 Diagnosis already running",
        "diagnosis_already_body": "The cat is still inspecting the numbers.",
        "diagnosis_running_title": "🧠 Finding the slowdown",
        "diagnosis_running_body": "The cat is checking disk and memory usage.",
        "diagnosis_result_title": "🧠 Memory Cat diagnosis",
        "confirm": "OK",
        "cleanup_review_title": "Review safe cleanup candidates?",
        "cleanup_review_body": (
            "Review {count} allowlisted item(s), one at a time. Only approved items "
            "will move to the macOS Trash; nothing is permanently deleted."
        ),
        "review_items": "Review items",
        "later": "Later",
        "unknown_size": "Unknown size",
        "cleanup_candidate": "Cleanup candidate",
        "trash_review_note": "This item is already in Trash; it will only be reviewed, never permanently deleted.",
        "move_question": "Move this item to the macOS Trash?",
        "move_to_trash": "Move to Trash",
        "skip": "Skip",
        "summary_moved": "Moved {count} item(s) to Trash",
        "summary_in_trash": "Reviewed {count} item(s) already in Trash",
        "summary_skipped": "Skipped {count} item(s)",
        "summary_failed": "Failed to move {count} item(s)",
        "summary_none": "No items were changed.",
        "summary_reclaim_note": " Space is reclaimed only after you empty the Trash yourself.",
        "cleanup_result_title": "🧹 Cleanup result",
        "menu_diagnosing": "🧠 Diagnosing…",
        "menu_diagnose": "🧠 Why is it slow?",
        "menu_theme": "Theme",
        "menu_size": "Size",
        "menu_personality": "Personality",
        "menu_custom": "Custom…",
        "menu_language": "Language",
        "menu_refresh": "Refresh",
        "menu_quit": "Quit",
        "language_auto": "Automatic ({language})",
        "language_ko": "한국어",
        "language_en": "English",
        "language_changed_title": "Language changed",
        "language_changed_body": "Display language changed to {language}.",
        "theme_cute": "Cute",
        "theme_simple": "Simple",
        "theme_madness": "Madness",
        "theme_derpy": "Wake-up call",
        "size_small": "Small",
        "size_medium": "Medium",
        "size_large": "Large",
        "size_king": "King-size",
    },
}


def canonical_language(value: Optional[str], default: str = LANGUAGE_KO) -> str:
    return value if value in (LANGUAGE_KO, LANGUAGE_EN) else default


def detect_system_language(
    preferred_languages: Optional[Iterable[str]] = None,
) -> str:
    """macOS 선호 언어가 한국어로 시작하면 ko, 그 외에는 en을 반환한다."""
    if preferred_languages is None:
        try:
            from Foundation import NSLocale

            preferred_languages = NSLocale.preferredLanguages()
        except Exception:
            preferred_languages = ()
    languages = list(preferred_languages or ())
    if languages and str(languages[0]).lower().replace("_", "-").startswith("ko"):
        return LANGUAGE_KO
    return LANGUAGE_EN


def resolve_language(
    override: Optional[str],
    preferred_languages: Optional[Iterable[str]] = None,
) -> str:
    if override in (LANGUAGE_KO, LANGUAGE_EN):
        return override
    return detect_system_language(preferred_languages)


def tr(language: str, key: str, **values: object) -> str:
    lang = canonical_language(language)
    text = _STRINGS[lang][key]
    return text.format(**values) if values else text


def chonk_stage(percent: float, language: str) -> str:
    """한국어는 기존 4단계를 유지하고 영어만 6단계 chonk chart를 쓴다."""
    if canonical_language(language) == LANGUAGE_KO:
        if percent < 60:
            return "여유 😺"
        if percent < 80:
            return "포동 🐈"
        if percent < 92:
            return "배불러 🍙"
        return "빵빵! 🐷"

    if percent < 60:
        return CHONK_STAGES_EN[0]
    if percent < 70:
        return CHONK_STAGES_EN[1]
    if percent < 80:
        return CHONK_STAGES_EN[2]
    if percent < 90:
        return CHONK_STAGES_EN[3]
    if percent < 96:
        return CHONK_STAGES_EN[4]
    return CHONK_STAGES_EN[5]
