from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT_LABEL = "ГРНТИ"


@dataclass(frozen=True)
class Node:
    id: str
    code: str | None
    depth: int
    label: str
    full_label: str
    description: str
    parent_id: str | None
    children_ids: tuple[str, ...] = field(default_factory=tuple)
    llm_descriptions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_leaf(self) -> bool:
        return len(self.children_ids) == 0


@dataclass
class Ontology:
    nodes_by_id: dict[str, Node]
    root_id: str
    code_index: dict[str, str]

    @classmethod
    def from_json(cls, path: str | Path) -> Ontology:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_payload(raw)

    @classmethod
    def from_payload(cls, payload: dict) -> Ontology:
        raw_nodes: list[dict] = payload["nodes"]
        raw_links: list[dict] = payload["links"]

        predicates = {link["predicate"] for link in raw_links}
        if len(predicates) > 1:
            raise ValueError(f"Multiple predicates found: {predicates}")

        children_map: dict[str, list[str]] = defaultdict(list)
        parents_map: dict[str, str] = {}
        for link in raw_links:
            children_map[link["source"]].append(link["target"])
            if link["target"] in parents_map:
                raise ValueError(f"Node {link['target']} has multiple parents")
            parents_map[link["target"]] = link["source"]

        all_ids = {n["id"] for n in raw_nodes}
        roots = [nid for nid in all_ids if nid not in parents_map]
        if len(roots) != 1:
            raise ValueError(f"Expected exactly one root, found {len(roots)}")
        root_id = roots[0]

        depth_by_id: dict[str, int] = {root_id: 0}
        frontier = [root_id]
        while frontier:
            next_frontier: list[str] = []
            for nid in frontier:
                d = depth_by_id[nid]
                for child in children_map.get(nid, []):
                    depth_by_id[child] = d + 1
                    next_frontier.append(child)
            frontier = next_frontier

        nodes_by_id: dict[str, Node] = {}
        code_index: dict[str, str] = {}
        for raw in raw_nodes:
            nid = raw["id"]
            code = raw.get("code")

            llm_raw = raw.get("llm_descriptions") or raw.get("llm_description")
            llm_descriptions: tuple[str, ...]
            if isinstance(llm_raw, str):
                llm_descriptions = (llm_raw,) if llm_raw.strip() else ()
            elif isinstance(llm_raw, list):
                llm_descriptions = tuple(s for s in llm_raw if isinstance(s, str) and s.strip())
            else:
                llm_descriptions = ()

            node = Node(
                id=nid,
                code=code,
                depth=depth_by_id.get(nid, -1),
                label=raw.get("label", ""),
                full_label=raw.get("full_label", raw.get("label", "")),
                description=raw.get("description", ""),
                parent_id=parents_map.get(nid),
                children_ids=tuple(sorted(children_map.get(nid, []))),
                llm_descriptions=llm_descriptions,
            )
            nodes_by_id[nid] = node
            if code:
                if code in code_index:
                    raise ValueError(f"Duplicate code {code!r}: {code_index[code]} vs {nid}")
                code_index[code] = nid

        if any(n.depth < 0 for n in nodes_by_id.values()):
            disconnected = [n.id for n in nodes_by_id.values() if n.depth < 0]
            raise ValueError(f"Disconnected nodes: {disconnected[:5]}")

        return cls(nodes_by_id=nodes_by_id, root_id=root_id, code_index=code_index)

    def node(self, id_or_code: str) -> Node:
        if id_or_code in self.nodes_by_id:
            return self.nodes_by_id[id_or_code]
        if id_or_code in self.code_index:
            return self.nodes_by_id[self.code_index[id_or_code]]
        raise KeyError(f"No node with id or code {id_or_code!r}")

    def code_to_node(self, code: str) -> Node | None:
        nid = self.code_index.get(code)
        return self.nodes_by_id[nid] if nid else None

    def has_code(self, code: str) -> bool:
        return code in self.code_index

    def root(self) -> Node:
        return self.nodes_by_id[self.root_id]

    def __len__(self) -> int:
        return len(self.nodes_by_id)

    def all_nodes(self) -> list[Node]:
        return list(self.nodes_by_id.values())

    def nodes_at_depth(self, depth: int) -> list[Node]:
        return [n for n in self.nodes_by_id.values() if n.depth == depth]

    def leaves(self) -> list[Node]:
        return [n for n in self.nodes_by_id.values() if n.is_leaf]

    def internal_nodes(self) -> list[Node]:
        return [n for n in self.nodes_by_id.values() if not n.is_leaf]

    def path(self, node_id: str) -> list[Node]:
        chain: list[Node] = []
        cur: str | None = node_id
        while cur is not None:
            n = self.nodes_by_id[cur]
            chain.append(n)
            cur = n.parent_id
        chain.reverse()
        return chain

    def path_codes(self, node_id: str) -> list[str | None]:
        return [n.code for n in self.path(node_id)]

    def children(self, node_id: str) -> list[Node]:
        node = self.nodes_by_id[node_id]
        return [self.nodes_by_id[cid] for cid in node.children_ids]

    def max_depth(self) -> int:
        return max(n.depth for n in self.nodes_by_id.values())


def build_anchor_text(
    node: Node,
    fields: tuple[str, ...] = ("label", "full_label", "description"),
    sep: str = " | ",
) -> str:
    parts = []
    for field_name in fields:
        value = getattr(node, field_name, None)
        if value:
            parts.append(str(value).strip())

    seen: set[str] = set()
    deduped: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    return sep.join(deduped)


def build_anchor_texts(
    node: Node,
    base_fields: tuple[str, ...] = ("label", "full_label", "description"),
    sep: str = " | ",
) -> list[str]:
    """Multi-anchor: один сводный текст из онтологических полей плюс
    каждое LLM-описание как отдельный якорь. Сходство с узлом считается
    через max-pool по этому списку (M3+ из диплома)."""
    anchors: list[str] = []
    base = build_anchor_text(node, fields=base_fields, sep=sep)
    if base:
        anchors.append(base)
    for desc in node.llm_descriptions:
        text = desc.strip()
        if text:
            anchors.append(text)
    return anchors or [node.label or node.id]
