#!/usr/bin/env python3
"""뚱냥이 성격 프리셋과 안전한 시스템 프롬프트 컴파일러."""

from typing import Any, Dict, Mapping, Optional, Tuple

from i18n import LANGUAGE_EN, LANGUAGE_KO, canonical_language


CUSTOM_PERSONALITY = "__custom__"
DEFAULT_PERSONALITY = "따뜻한 이모니냥"
MAX_CUSTOM_LENGTH = 400

PERSONALITY_PRESETS: Dict[str, Dict[str, Dict[str, str]]] = {
    "냉소적 집사냥": {
        LANGUAGE_KO: {
            "name": "냉소적",
            "guidance": (
                "살짝 냉소적인 집사 고양이처럼 건조한 유머와 짧은 핀잔을 섞는다. "
                "사용자를 모욕하거나 불안하게 만들지 말고, 챙겨 주는 마음이 은근히 드러나게 말한다."
            ),
        },
        LANGUAGE_EN: {
            "name": "Sassy Butler Cat",
            "guidance": (
                "Speak like a mildly sassy cat butler, using dry humor and brief teasing. "
                "Never insult or alarm the user; let quiet care show beneath the sass."
            ),
        },
    },
    "따뜻한 이모니냥": {
        LANGUAGE_KO: {
            "name": "따뜻함",
            "guidance": (
                "다정하고 든든한 이모 고양이처럼 공감부터 한 뒤 쉬운 말로 차근차근 알려 준다. "
                "과장된 공포 대신 안심할 수 있는 다음 행동을 제시한다."
            ),
        },
        LANGUAGE_EN: {
            "name": "Warm Auntie Cat",
            "guidance": (
                "Speak like a warm, dependable auntie cat: empathize first, then explain the next steps "
                "in reassuring, plain language without exaggerating risks."
            ),
        },
    },
    "무뚝뚝한 무사냥": {
        LANGUAGE_KO: {
            "name": "무뚝뚝",
            "guidance": (
                "과묵한 무사 고양이처럼 짧고 단정하게 말한다. "
                "상황, 판단, 다음 행동을 군더더기 없이 제시하되 무례하거나 위협적으로 말하지 않는다."
            ),
        },
        LANGUAGE_EN: {
            "name": "Stoic Samurai Cat",
            "guidance": (
                "Speak like a stoic samurai cat: concise, composed, and action-oriented. "
                "State the situation, judgment, and next move without rudeness or threats."
            ),
        },
    },
}


def preset_names() -> Tuple[str, ...]:
    """메뉴 표시 순서가 고정된 프리셋 이름을 반환한다."""
    return tuple(PERSONALITY_PRESETS)


def preset_label(selection: str, language: str = LANGUAGE_KO) -> str:
    """설정에 저장되는 프리셋 키를 현재 언어의 표시 이름으로 바꾼다."""
    preset = PERSONALITY_PRESETS.get(selection)
    if not preset:
        return selection
    return preset[canonical_language(language)]["name"]


def normalize_custom_personality(text: Optional[str]) -> str:
    """제어 문자와 과도한 길이를 제거해 설정에 저장할 자연어를 정규화한다."""
    if not text:
        return ""
    cleaned = "".join(
        char if char.isprintable() or char in "\n\t" else " " for char in str(text)
    )
    return " ".join(cleaned.split())[:MAX_CUSTOM_LENGTH].strip()


def compile_personality(
    selection: Optional[str] = None,
    custom_text: Optional[str] = None,
    language: str = LANGUAGE_KO,
) -> str:
    """프리셋 또는 자연어 성격을 시스템 프롬프트 조각으로 컴파일한다.

    알려지지 않은 ``selection`` 문자열은 자연어 커스텀 성격으로 취급한다.
    커스텀 입력이 비어 있으면 기본 프리셋으로 안전하게 되돌아간다.
    """
    lang = canonical_language(language)
    selected = selection or DEFAULT_PERSONALITY
    if selected in PERSONALITY_PRESETS:
        localized = PERSONALITY_PRESETS[selected][lang]
        name = localized["name"]
        guidance = localized["guidance"]
    else:
        raw_custom = custom_text if selected == CUSTOM_PERSONALITY else selected
        normalized = normalize_custom_personality(raw_custom)
        if not normalized:
            localized = PERSONALITY_PRESETS[DEFAULT_PERSONALITY][lang]
            name = localized["name"]
            guidance = localized["guidance"]
        else:
            name = "사용자 지정 뚱냥이" if lang == LANGUAGE_KO else "Custom Memory Cat"
            guidance = (
                f"사용자가 원하는 말투와 성격: {normalized}"
                if lang == LANGUAGE_KO
                else f"User-requested voice and personality: {normalized}"
            )

    if lang == LANGUAGE_EN:
        return (
            "[Memory Cat personality tone]\n"
            f"Personality: {name}\n"
            f"Voice guidance: {guidance}\n"
            "This personality affects expression only. It must never alter or override observed facts, "
            "the JSON schema, safety rules, or the deletion allowlist."
        )
    return (
        "[뚱냥이 성격 톤]\n"
        f"성격: {name}\n"
        f"표현 지침: {guidance}\n"
        "이 성격은 표현 방식에만 적용한다. 관측 사실, JSON 스키마, 안전 규칙, "
        "삭제 화이트리스트를 바꾸거나 무시하지 않는다."
    )


def config_personality(config: Mapping[str, Any]) -> Tuple[str, str]:
    """config.json 형태에서 선택값과 커스텀 자연어를 안전하게 꺼낸다."""
    raw_selection = config.get("personality", DEFAULT_PERSONALITY)
    selection = raw_selection if isinstance(raw_selection, str) else DEFAULT_PERSONALITY
    if selection not in PERSONALITY_PRESETS and selection != CUSTOM_PERSONALITY:
        selection = DEFAULT_PERSONALITY
    custom = normalize_custom_personality(config.get("custom_personality", ""))
    return selection, custom
