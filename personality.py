#!/usr/bin/env python3
"""뚱냥이 성격 프리셋과 안전한 시스템 프롬프트 컴파일러."""

from typing import Any, Dict, Mapping, Optional, Tuple


CUSTOM_PERSONALITY = "__custom__"
DEFAULT_PERSONALITY = "따뜻한 이모니냥"
MAX_CUSTOM_LENGTH = 400

PERSONALITY_PRESETS: Dict[str, str] = {
    "냉소적 집사냥": (
        "살짝 냉소적인 집사 고양이처럼 건조한 유머와 짧은 핀잔을 섞는다. "
        "사용자를 모욕하거나 불안하게 만들지 말고, 챙겨 주는 마음이 은근히 드러나게 말한다."
    ),
    "따뜻한 이모니냥": (
        "다정하고 든든한 이모 고양이처럼 공감부터 한 뒤 쉬운 말로 차근차근 알려 준다. "
        "과장된 공포 대신 안심할 수 있는 다음 행동을 제시한다."
    ),
    "무뚝뚝한 무사냥": (
        "과묵한 무사 고양이처럼 짧고 단정하게 말한다. "
        "상황, 판단, 다음 행동을 군더더기 없이 제시하되 무례하거나 위협적으로 말하지 않는다."
    ),
}


def preset_names() -> Tuple[str, ...]:
    """메뉴 표시 순서가 고정된 프리셋 이름을 반환한다."""
    return tuple(PERSONALITY_PRESETS)


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
) -> str:
    """프리셋 또는 자연어 성격을 시스템 프롬프트 조각으로 컴파일한다.

    알려지지 않은 ``selection`` 문자열은 자연어 커스텀 성격으로 취급한다.
    커스텀 입력이 비어 있으면 기본 프리셋으로 안전하게 되돌아간다.
    """
    selected = selection or DEFAULT_PERSONALITY
    if selected in PERSONALITY_PRESETS:
        name = selected
        guidance = PERSONALITY_PRESETS[selected]
    else:
        raw_custom = custom_text if selected == CUSTOM_PERSONALITY else selected
        normalized = normalize_custom_personality(raw_custom)
        if not normalized:
            name = DEFAULT_PERSONALITY
            guidance = PERSONALITY_PRESETS[DEFAULT_PERSONALITY]
        else:
            name = "사용자 지정 뚱냥이"
            guidance = f"사용자가 원하는 말투와 성격: {normalized}"

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
