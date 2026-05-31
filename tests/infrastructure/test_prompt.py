from __future__ import annotations

from backend.infrastructure.llm.prompt import (
    SYSTEM_MESSAGE,
    build_v8_messages,
    split_fragments,
)


def test_messages_include_system_role() -> None:
    messages = build_v8_messages(
        label="Геномика", code="34.15.23", parent_chain=["ГРНТИ", "Биология", "Генетика"]
    )
    assert messages[0] == {"role": "system", "content": SYSTEM_MESSAGE}
    assert messages[1]["role"] == "user"


def test_user_prompt_contains_label_code_and_full_label() -> None:
    messages = build_v8_messages(
        label="Геномика", code="34.15.23", parent_chain=["ГРНТИ", "Биология", "Генетика"]
    )
    user = messages[1]["content"]
    assert "Геномика" in user
    assert "34.15.23" in user
    assert "ГРНТИ → Биология → Генетика → Геномика" in user


def test_user_prompt_uses_yaml_indented_chain() -> None:
    messages = build_v8_messages(label="C", code="0", parent_chain=["A", "B"])
    user = messages[1]["content"]
    assert "- A\n  - B\n    - C" in user


def test_missing_code_falls_back_to_dash() -> None:
    messages = build_v8_messages(label="L", code="", parent_chain=["A"])
    assert "(ГРНТИ —)" in messages[1]["content"]


def test_split_fragments_strips_and_drops_blanks() -> None:
    raw = "  one  \n\n  two\nthree\n   "
    assert split_fragments(raw) == ["one", "two", "three"]


def test_split_fragments_handles_empty_string() -> None:
    assert split_fragments("") == []
    assert split_fragments("\n\n  \n") == []
