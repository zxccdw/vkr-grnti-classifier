from __future__ import annotations

from pathlib import Path

SYSTEM_MESSAGE = "Ты эксперт-классификатор по ГРНТИ. Отвечай по-русски."

_TEMPLATE_PATH = Path(__file__).parent / "prompts" / "v8_project.txt"
_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")


def build_v8_messages(*, label: str, code: str, parent_chain: list[str]) -> list[dict[str, str]]:
    full_chain = parent_chain + [label]
    full_label = " → ".join(full_chain)
    user = _TEMPLATE.format(
        path_text=_linearize_yaml(full_chain),
        label=label,
        code=code or "—",
        full_label=full_label,
    )
    return [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": user},
    ]


def split_fragments(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _linearize_yaml(chain: list[str]) -> str:
    return "\n".join("  " * i + "- " + label for i, label in enumerate(chain))
