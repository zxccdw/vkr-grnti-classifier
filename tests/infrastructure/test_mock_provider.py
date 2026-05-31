from __future__ import annotations

from backend.infrastructure.llm.mock_provider import MockProvider


async def test_mock_returns_five_non_empty_fragments() -> None:
    provider = MockProvider()
    fragments = await provider.describe(
        label="Геномика",
        code="34.15.23",
        parent_chain=["ГРНТИ", "Биология", "Генетика"],
    )
    assert len(fragments) == 5
    assert all(f.strip() for f in fragments)


async def test_mock_fragments_contain_label_and_path() -> None:
    provider = MockProvider()
    fragments = await provider.describe(
        label="Геномика", code="34.15.23", parent_chain=["Биология", "Генетика"]
    )
    joined = "\n".join(fragments)
    assert "Геномика" in joined
    assert "Биология" in joined


async def test_mock_deterministic_for_same_input() -> None:
    provider = MockProvider()
    a = await provider.describe("X", "0", ["A"])
    b = await provider.describe("X", "0", ["A"])
    assert a == b


async def test_mock_handles_empty_chain() -> None:
    provider = MockProvider()
    fragments = await provider.describe("X", "0", [])
    assert len(fragments) == 5
    assert "общая область" in fragments[0]
