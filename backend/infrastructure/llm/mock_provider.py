from __future__ import annotations


class MockProvider:
    def __init__(self, name: str = "mock") -> None:
        self.name = name

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        path = " → ".join(parent_chain) if parent_chain else "общая область"
        code_str = code or "—"
        return [
            f"Объектом исследования являются {label} в контексте дисциплины {path}.",
            f"Целью работы является разработка методов изучения темы {label}, "
            f"входящей в раздел {code_str}.",
            f"Получены экспериментальные данные по направлению {label}; "
            f"методология опирается на принципы, принятые в {path}.",
            f"Научная новизна заключается в систематизации подходов к {label} "
            f"с учётом контекста {path}.",
            f"Результаты применимы для решения прикладных задач в области {path} "
            f"и смежных направлений.",
        ]
