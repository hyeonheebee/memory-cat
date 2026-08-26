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
        "personality_changed_title": "{pet} 성격 변경",
        "personality_changed_body": "이제 {personality} 말투로 진단할게요.",
        "custom_title": "{pet} 성격을 직접 알려 주세요",
        "custom_hint": "예: 다정하지만 핵심만 말하고, 말끝에 냥을 붙여줘",
        "save": "저장",
        "cancel": "취소",
        "custom_empty_title": "성격을 저장하지 않았어요",
        "custom_empty_body": "한 문장 이상 입력해 주세요.",
        "custom_saved_title": "커스텀 성격 저장",
        "personality_custom_label": "직접 입력",
        "diagnosis_already_title": "🧠 이미 진단 중이에요",
        "diagnosis_already_body": "{pet}가 숫자를 살펴보고 있습니다.",
        "diagnosis_running_title": "🐾 살펴보는 중…",
        "diagnosis_running_body": "{pet}가 얼마나 배부른지 살펴보고 있어요.",
        "diagnosis_source_fallback": "⚠️ 오프라인 진단 · 성격 미적용 · {reason}",
        "diagnosis_result_openai_title": "{personality} {pet}가 배부른 이유예요.",
        "diagnosis_result_fallback_title": "{pet}가 배부른 이유예요.",
        "fallback_missing_api_key": "API 키 없음",
        "menu_pet_name": "이름 지어주기…",
        "pet_name_title": "뭐라고 부를까요?",
        "pet_name_hint": "비워 두면 뚱냥이라고 부릅니다.",
        "pet_name_saved_title": "이제 {pet}라고 부를게요",
        "missing_api_key_title": "API 키가 필요해요",
        "missing_api_key_help": (
            "🔑 AI 진단과 반려동물 테마를 켜려면\n"
            "OpenAI API 키를 아래 파일에 넣어 주세요.\n"
            "{path}\n\n"
            "파일에 이렇게 한 줄만 적으면 됩니다.\n"
            "OPENAI_API_KEY=sk-...\n\n"
            "넣은 뒤 뚱냥이를 껐다 켜 주세요."
        ),
        "fallback_api_error": "API 연결 실패",
        "fallback_worker_error": "진단 처리 실패",
        "fallback_unknown": "알 수 없는 오류",
        "diagnosis_advice_heading": "🐾 한 문장 조언",
        "diagnosis_reclaimable": "예상 확보 용량: {size}",
        "close": "닫기",
        "confirm": "확인",
        "cleanup_review_title": "안전한 정리 후보를 볼까요?",
        "cleanup_review_body": (
            "화이트리스트 항목 {count}개를 하나씩 확인합니다. "
            "동의한 항목만 macOS 휴지통으로 이동하며 영구 삭제하지 않습니다."
        ),
        "review_items": "정리 후보 검토",
        "later": "나중에",
        "unknown_size": "크기 알 수 없음",
        "cleanup_candidate": "정리 후보",
        "trash_review_note": "이미 휴지통 안에 있어 확인만 하며, 영구 삭제하지 않습니다.",
        "move_question": "이 항목을 macOS 휴지통으로 이동할까요?",
        "move_to_trash": "휴지통으로 이동",
        "skip": "건너뛰기",
        "stop_cleanup": "정리 중단",
        "summary_moved": "{count}개를 휴지통으로 이동",
        "summary_in_trash": "휴지통 안 {count}개 확인",
        "summary_skipped": "{count}개 건너뜀",
        "summary_failed": "{count}개 이동 실패",
        "summary_none": "변경한 항목이 없습니다.",
        "summary_reclaim_note": " 공간은 휴지통을 직접 비운 뒤 확보됩니다.",
        "cleanup_result_title": "🧹 정리 결과",
        "menu_diagnosing": "🐾 살펴보는 중…",
        "menu_diagnose": "🐾 뭘 먹은 거야?",
        "menu_diagnose_again": "🐾 다시 살펴보기",
        "menu_last_diagnosis": "📋 마지막 진단 보기",
        "menu_theme": "테마",
        "menu_pet_theme": "내 반려동물로 테마 만들기…",
        "menu_pet_theme_running": "테마 만드는 중…",
        "pet_theme_consent_title": "사진 전송 안내",
        "pet_theme_consent_body": "선택한 사진이 테마 생성을 위해 OpenAI로 전송됩니다",
        "pet_theme_continue": "진행",
        "pet_theme_complete_title": "반려동물 테마 완성",
        "pet_theme_complete_body": "{count}단계를 감지해 {theme} 테마를 바로 적용했어요.",
        "pet_theme_error_title": "테마를 만들지 못했어요",
        "disk_full_prompt_title": "🐾 {pet}가 배불러요",
        "disk_full_prompt_body": "배불러… 진단해볼까?",
        "disk_full_prompt_action": "진단하기",
        "already_running_title": "{pet}는 이미 한 마리 있어요",
        "already_running_body": (
            "{pet}를 불러 봤는데 대답이 없네요. 화면 어딘가에 숨어 있거나 "
            "멈춰 있을 수 있어요. 우클릭 메뉴에서 종료한 뒤 다시 열어 주세요."
        ),
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
        "personality_changed_title": "{pet} personality changed",
        "personality_changed_body": "Future diagnoses will use the {personality} voice.",
        "custom_title": "Describe {pet}'s personality",
        "custom_hint": "Example: Be kind, lead with the key point, and end sentences with meow.",
        "save": "Save",
        "cancel": "Cancel",
        "custom_empty_title": "Personality not saved",
        "custom_empty_body": "Please enter at least one sentence.",
        "custom_saved_title": "Custom personality saved",
        "personality_custom_label": "Custom",
        "diagnosis_already_title": "🧠 Diagnosis already running",
        "diagnosis_already_body": "{pet} is still inspecting the numbers.",
        "diagnosis_running_title": "🐾 Checking…",
        "diagnosis_running_body": "{pet} is checking how full things feel.",
        "diagnosis_source_fallback": "⚠️ Offline diagnosis · Personality not applied · {reason}",
        "diagnosis_result_openai_title": "Here’s why your {personality} {pet} feels full.",
        "diagnosis_result_fallback_title": "Here’s why {pet} feels full.",
        "fallback_missing_api_key": "API key missing",
        "menu_pet_name": "Give it a name…",
        "pet_name_title": "What should I call it?",
        "pet_name_hint": "Leave it empty to keep calling it Memory Cat.",
        "pet_name_saved_title": "I'll call it {pet} from now on",
        "missing_api_key_title": "An API key is needed",
        "missing_api_key_help": (
            "🔑 To turn on AI diagnosis and pet themes, put your OpenAI\n"
            "API key in this file.\n"
            "{path}\n\n"
            "One line is all it needs.\n"
            "OPENAI_API_KEY=sk-...\n\n"
            "Then quit and reopen Memory Cat."
        ),
        "fallback_api_error": "API connection failed",
        "fallback_worker_error": "Diagnosis processing failed",
        "fallback_unknown": "Unknown error",
        "diagnosis_advice_heading": "🐾 One-line advice",
        "diagnosis_reclaimable": "Estimated reclaimable space: {size}",
        "close": "Close",
        "confirm": "OK",
        "cleanup_review_title": "Review safe cleanup candidates?",
        "cleanup_review_body": (
            "Review {count} allowlisted item(s), one at a time. Only approved items "
            "will move to the macOS Trash; nothing is permanently deleted."
        ),
        "review_items": "Review cleanup candidates",
        "later": "Later",
        "unknown_size": "Unknown size",
        "cleanup_candidate": "Cleanup candidate",
        "trash_review_note": "This item is already in Trash; it will only be reviewed, never permanently deleted.",
        "move_question": "Move this item to the macOS Trash?",
        "move_to_trash": "Move to Trash",
        "skip": "Skip",
        "stop_cleanup": "Stop review",
        "summary_moved": "Moved {count} item(s) to Trash",
        "summary_in_trash": "Reviewed {count} item(s) already in Trash",
        "summary_skipped": "Skipped {count} item(s)",
        "summary_failed": "Failed to move {count} item(s)",
        "summary_none": "No items were changed.",
        "summary_reclaim_note": " Space is reclaimed only after you empty the Trash yourself.",
        "cleanup_result_title": "🧹 Cleanup result",
        "menu_diagnosing": "🐾 Checking…",
        "menu_diagnose": "🐾 What did you eat?",
        "menu_diagnose_again": "🐾 Check again",
        "menu_last_diagnosis": "📋 View last diagnosis",
        "menu_theme": "Theme",
        "menu_pet_theme": "Make a theme from my pet…",
        "menu_pet_theme_running": "Making theme…",
        "pet_theme_consent_title": "Photo upload notice",
        "pet_theme_consent_body": "Your photo will be sent to OpenAI to generate the theme",
        "pet_theme_continue": "Continue",
        "pet_theme_complete_title": "Pet theme ready",
        "pet_theme_complete_body": "Detected {count} stages and applied the {theme} theme.",
        "pet_theme_error_title": "Couldn't make the theme",
        "disk_full_prompt_title": "🐾 {pet} is full",
        "disk_full_prompt_body": "I'm so full… want a checkup?",
        "disk_full_prompt_action": "Run checkup",
        "already_running_title": "{pet} is already running",
        "already_running_body": (
            "{pet} did not answer. It may be hidden somewhere on "
            "screen, or stuck. Quit it from the right-click menu and open "
            "it again."
        ),
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

_DIAGNOSIS_PERSONALITY_DESCRIPTORS = {
    LANGUAGE_KO: {
        "냉소적": "냉소적인",
        "따뜻함": "따뜻한",
        "무뚝뚝": "무뚝뚝한",
        "직접 입력": "나만의",
    },
    LANGUAGE_EN: {
        "Sassy Butler Cat": "sassy",
        "Warm Auntie Cat": "warm",
        "Stoic Samurai Cat": "stoic",
        "Custom": "custom",
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


def tr(locale: str, key: str, **values: object) -> str:
    lang = canonical_language(locale)
    text = _STRINGS[lang][key]
    return text.format(**values) if values else text


def diagnosis_personality_descriptor(label: str, language: str) -> str:
    """진단 제목에서 성격 이름이 자연스러운 관형어가 되게 한다."""
    lang = canonical_language(language)
    default = "나만의" if lang == LANGUAGE_KO else "custom"
    return _DIAGNOSIS_PERSONALITY_DESCRIPTORS[lang].get(label, default)


#: 이름을 안 지어 줬을 때 쓰는 기본 호칭.
DEFAULT_PET_NAME = {LANGUAGE_KO: "뚱냥이", LANGUAGE_EN: "Memory Cat"}


def pet_name(configured: Optional[str], language: str) -> str:
    """화면에 부를 이름. 안 지었으면 기본 호칭으로 돌아간다.

    사진으로 테마를 만들면 고양이가 아닐 수 있어서, "뚱냥이" 를 그대로 쓰면
    수달한테 냥이라고 부르게 된다.
    """
    name = str(configured or "").strip()
    return name or DEFAULT_PET_NAME[canonical_language(language)]


def chonk_stage(percent: float, language: str) -> str:
    """한국어는 기존 4단계를 유지하고 영어만 6단계 chonk chart를 쓴다."""
    if canonical_language(language) == LANGUAGE_KO:
        if percent < 60:
            return "여유"
        if percent < 80:
            return "포동"
        if percent < 92:
            return "배불러"
        return "빵빵!"

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
