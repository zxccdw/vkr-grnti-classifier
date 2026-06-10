from __future__ import annotations

import json
import os
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from backend.domain.entities import (
    Description,
    Edge,
    Node,
    NodeId,
    NodeKind,
    Subgraph,
)
from backend.domain.errors import (
    ConcurrentModificationError,
    EdgeAlreadyExists,
    EdgeNotFound,
    NodeAlreadyExists,
    NodeNotFound,
)
from backend.services.ontology import Ontology

if TYPE_CHECKING:
    from backend.infrastructure.s3_store import S3Store

PREDICATE_CONTAINS = "http://example.org/competencies#содержит"

EdgeKey = tuple[str, str, str]


class JsonOntologyRepository:
    def __init__(
        self,
        path: Path,
        snapshots_dir: Path,
        s3_store: S3Store | None = None,
        on_s3_write: Callable[[str | None], None] | None = None,
    ) -> None:
        self._path = path
        self._snapshots_dir = snapshots_dir
        self._s3 = s3_store
        self._on_s3_write = on_s3_write
        self._etag: str | None = None
        if self._s3:
            self._s3.download_to(path)
            self._etag = self._s3.get_etag()
        self._raw: dict = json.loads(path.read_text(encoding="utf-8"))
        self._nodes_by_id: dict[str, dict] = {n["id"]: n for n in self._raw["nodes"]}
        self._edges_by_key: dict[EdgeKey, dict] = {}
        self._incoming: dict[str, list[str]] = defaultdict(list)
        self._outgoing: dict[str, list[str]] = defaultdict(list)
        self._reindex_edges()

        self._pending_nodes: list[Node] = []
        self._pending_edges: list[Edge] = []
        self._pending_edge_updates: dict[EdgeKey, tuple[Description, ...]] = {}

        self._ontology = Ontology.from_payload(self._raw)

    @property
    def ontology(self) -> Ontology:
        return self._ontology

    def get_node(self, id: NodeId) -> Node:
        raw = self._nodes_by_id.get(id.value)
        if raw is None:
            for n in self._pending_nodes:
                if n.id == id:
                    return n
            raise NodeNotFound(id.value)
        return _node_from_raw(raw)

    def get_edge(self, source: NodeId, target: NodeId, predicate: str) -> Edge:
        key = (source.value, target.value, predicate)
        raw = self._edges_by_key.get(key)
        if raw is not None:
            descriptions = self._pending_edge_updates.get(key) or _read_descriptions(
                raw, self._nodes_by_id
            )
            return Edge(
                source=source, target=target, predicate=predicate, descriptions=descriptions
            )
        for edge in self._pending_edges:
            if edge.source == source and edge.target == target and edge.predicate == predicate:
                return edge
        raise EdgeNotFound(f"{source.value} -[{predicate}]-> {target.value}")

    def parents_of(self, id: NodeId) -> list[Node]:
        parents: list[Node] = [
            _node_from_raw(self._nodes_by_id[p]) for p in self._incoming.get(id.value, [])
        ]
        for edge in self._pending_edges:
            if edge.target != id:
                continue
            if edge.source.value in self._nodes_by_id:
                parents.append(_node_from_raw(self._nodes_by_id[edge.source.value]))
                continue
            pending_node = self._pending_node_by_id(edge.source)
            if pending_node is not None:
                parents.append(pending_node)
        return parents

    def shortest_path(self, id: NodeId) -> list[Node]:
        if id.value not in self._nodes_by_id and not self._pending_node_by_id(id):
            raise NodeNotFound(id.value)

        start = id.value
        if start not in self._nodes_by_id:
            return [self.get_node(id)]

        came_from: dict[str, str] = {}
        visited = {start}
        frontier: deque[str] = deque([start])
        root_id: str | None = None
        while frontier:
            current = frontier.popleft()
            parents = self._incoming.get(current, [])
            if not parents:
                root_id = current
                break
            for parent in parents:
                if parent in visited:
                    continue
                visited.add(parent)
                came_from[parent] = current
                frontier.append(parent)

        if root_id is None:
            return [self.get_node(id)]

        chain_ids = [root_id]
        cursor = root_id
        while cursor in came_from:
            cursor = came_from[cursor]
            chain_ids.append(cursor)
        return [self.get_node(NodeId(nid)) for nid in chain_ids]

    def subgraph(self, root: NodeId, max_depth: int = 1) -> Subgraph:
        if root.value not in self._nodes_by_id:
            raise NodeNotFound(root.value)

        seen_nodes: set[str] = set()
        nodes: list[Node] = []
        edges: list[Edge] = []
        frontier: deque[tuple[str, int]] = deque([(root.value, 0)])

        while frontier:
            current_id, depth = frontier.popleft()
            if current_id in seen_nodes:
                continue
            seen_nodes.add(current_id)
            nodes.append(_node_from_raw(self._nodes_by_id[current_id]))
            if depth >= max_depth:
                continue
            for child_id in self._outgoing.get(current_id, []):
                key = self._find_edge_key(current_id, child_id)
                if key is None:
                    continue
                raw_link = self._edges_by_key[key]
                descriptions = self._pending_edge_updates.get(key) or _read_descriptions(
                    raw_link, self._nodes_by_id
                )
                edges.append(
                    Edge(
                        source=NodeId(current_id),
                        target=NodeId(child_id),
                        predicate=raw_link["predicate"],
                        descriptions=descriptions,
                    )
                )
                frontier.append((child_id, depth + 1))

        return Subgraph(nodes=tuple(nodes), edges=tuple(edges))

    def add_node(self, node: Node) -> None:
        if node.id.value in self._nodes_by_id:
            raise NodeAlreadyExists(node.id.value)
        if self._pending_node_by_id(node.id) is not None:
            raise NodeAlreadyExists(node.id.value)
        self._pending_nodes.append(node)

    def all_nodes(self) -> list[Node]:
        return [_node_from_raw(raw) for raw in self._raw["nodes"]]

    def all_edges(self) -> list[Edge]:
        edges: list[Edge] = []
        for key, raw_link in self._edges_by_key.items():
            descriptions = self._pending_edge_updates.get(key) or _read_descriptions(
                raw_link, self._nodes_by_id
            )
            edges.append(
                Edge(
                    source=NodeId(key[0]),
                    target=NodeId(key[1]),
                    predicate=key[2],
                    descriptions=descriptions,
                )
            )
        return edges

    def remove_node(self, id: NodeId) -> None:
        if id.value not in self._nodes_by_id:
            raise NodeNotFound(id.value)
        self._snapshot()
        self._raw["nodes"] = [n for n in self._raw["nodes"] if n["id"] != id.value]
        self._raw["links"] = [
            link
            for link in self._raw["links"]
            if link["source"] != id.value and link["target"] != id.value
        ]
        self._atomic_write()
        self._nodes_by_id.pop(id.value, None)
        self._edges_by_key = {
            k: v for k, v in self._edges_by_key.items() if k[0] != id.value and k[1] != id.value
        }
        self._incoming.pop(id.value, None)
        self._outgoing.pop(id.value, None)
        for lst in self._incoming.values():
            lst[:] = [s for s in lst if s != id.value]
        for lst in self._outgoing.values():
            lst[:] = [t for t in lst if t != id.value]
        self._ontology = Ontology.from_payload(self._raw)

    def reload(self) -> None:
        self._raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._nodes_by_id = {n["id"]: n for n in self._raw["nodes"]}
        self._edges_by_key.clear()
        self._incoming.clear()
        self._outgoing.clear()
        self._reindex_edges()
        self._ontology = Ontology.from_payload(self._raw)
        self._pending_nodes.clear()
        self._pending_edges.clear()
        self._pending_edge_updates.clear()
        if self._s3:
            self._etag = self._s3.get_etag()

    def export_path(self) -> Path:
        return self._path

    def export_presigned_url(self, expires_in: int = 3600) -> str | None:
        if self._s3 is None:
            return None
        return self._s3.generate_download_url(expires_in=expires_in)

    def search(self, query: str, limit: int = 50) -> list[Node]:
        q_lower = query.lower()
        out: list[Node] = []
        for raw in self._raw["nodes"]:
            label = (raw.get("label") or "").lower()
            code = (raw.get("code") or "").lower()
            if q_lower not in label and q_lower not in code:
                continue
            out.append(_node_from_raw(raw))
            if len(out) >= limit:
                break
        return out

    def import_payload(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        if not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("links"), list):
            raise ValueError("payload must contain lists 'nodes' and 'links'")
        Ontology.from_payload(payload)
        self._snapshot()
        self._raw = payload
        self._atomic_write()
        self._nodes_by_id = {n["id"]: n for n in self._raw["nodes"]}
        self._edges_by_key.clear()
        self._incoming.clear()
        self._outgoing.clear()
        self._reindex_edges()
        self._ontology = Ontology.from_payload(self._raw)
        self._pending_nodes.clear()
        self._pending_edges.clear()
        self._pending_edge_updates.clear()

    def remove_edge(self, source: NodeId, target: NodeId, predicate: str) -> None:
        key = (source.value, target.value, predicate)
        if key not in self._edges_by_key:
            raise EdgeNotFound(str(key))
        self._snapshot()
        self._raw["links"] = [
            link
            for link in self._raw["links"]
            if (link["source"], link["target"], link["predicate"]) != key
        ]
        self._atomic_write()
        self._edges_by_key.clear()
        self._incoming.clear()
        self._outgoing.clear()
        self._reindex_edges()
        self._ontology = Ontology.from_payload(self._raw)

    def add_edge(self, edge: Edge) -> None:
        if not self._node_exists(edge.source):
            raise NodeNotFound(edge.source.value)
        if not self._node_exists(edge.target):
            raise NodeNotFound(edge.target.value)
        key = (edge.source.value, edge.target.value, edge.predicate)
        if key in self._edges_by_key:
            raise EdgeAlreadyExists(str(key))
        for pending in self._pending_edges:
            if (pending.source.value, pending.target.value, pending.predicate) == key:
                raise EdgeAlreadyExists(str(key))
        self._pending_edges.append(edge)

    def update_edge_descriptions(
        self,
        source: NodeId,
        target: NodeId,
        predicate: str,
        descriptions: tuple[Description, ...],
    ) -> None:
        key = (source.value, target.value, predicate)
        if key in self._edges_by_key:
            self._pending_edge_updates[key] = descriptions
            return
        for i, edge in enumerate(self._pending_edges):
            if (edge.source.value, edge.target.value, edge.predicate) == key:
                self._pending_edges[i] = Edge(
                    source=edge.source,
                    target=edge.target,
                    predicate=edge.predicate,
                    descriptions=descriptions,
                )
                return
        raise EdgeNotFound(str(key))

    def pending_edges(self) -> list[Edge]:
        out: list[Edge] = []
        for key, raw_link in self._edges_by_key.items():
            if key in self._pending_edge_updates:
                continue
            # only generate descriptions for leaf nodes
            target_raw = self._nodes_by_id.get(key[1], {})
            if _kind_by_code(target_raw.get("code")) != NodeKind.LEAF:
                continue
            descriptions = _read_descriptions(raw_link, self._nodes_by_id)
            if descriptions:
                continue
            out.append(
                Edge(
                    source=NodeId(key[0]),
                    target=NodeId(key[1]),
                    predicate=key[2],
                    descriptions=(),
                )
            )
        for edge in self._pending_edges:
            if not edge.descriptions:
                out.append(edge)
        return out

    def commit(self) -> None:
        if not (self._pending_nodes or self._pending_edges or self._pending_edge_updates):
            return
        self._snapshot()

        for node in self._pending_nodes:
            raw = _node_to_raw(node)
            self._raw["nodes"].append(raw)
            self._nodes_by_id[node.id.value] = raw

        for edge in self._pending_edges:
            raw_link = _edge_to_raw(edge)
            self._raw["links"].append(raw_link)

        for key, descriptions in self._pending_edge_updates.items():
            existing_link = self._edges_by_key.get(key)
            if existing_link is None:
                continue
            existing_link["llm_descriptions"] = [
                {"text": d.text, "source": d.source} for d in descriptions
            ]

        self._atomic_write()
        self._raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._nodes_by_id = {n["id"]: n for n in self._raw["nodes"]}
        self._edges_by_key.clear()
        self._incoming.clear()
        self._outgoing.clear()
        self._reindex_edges()
        self._ontology = Ontology.from_payload(self._raw)
        self._pending_nodes.clear()
        self._pending_edges.clear()
        self._pending_edge_updates.clear()

    def _reindex_edges(self) -> None:
        for link in self._raw["links"]:
            key = (link["source"], link["target"], link["predicate"])
            self._edges_by_key[key] = link
            self._incoming[link["target"]].append(link["source"])
            self._outgoing[link["source"]].append(link["target"])

    def _find_edge_key(self, source: str, target: str) -> EdgeKey | None:
        for key in self._edges_by_key:
            if key[0] == source and key[1] == target:
                return key
        return None

    def _node_exists(self, id: NodeId) -> bool:
        return id.value in self._nodes_by_id or self._pending_node_by_id(id) is not None

    def _pending_node_by_id(self, id: NodeId) -> Node | None:
        for n in self._pending_nodes:
            if n.id == id:
                return n
        return None

    def _snapshot(self) -> None:
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        target = self._snapshots_dir / f"{ts}.json"
        target.write_bytes(self._path.read_bytes())

    def _atomic_write(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)
        if self._s3:
            try:
                new_etag = self._s3.upload_from(self._path, if_match=self._etag)
                if self._on_s3_write:
                    self._on_s3_write(new_etag)
            except Exception as e:
                if "PreconditionFailed" in str(e) or "412" in str(e):
                    raise ConcurrentModificationError(
                        "Ontology was modified by another user. Please refresh and try again."
                    ) from e
                raise


def _node_from_raw(raw: dict) -> Node:
    return Node(
        id=NodeId(raw["id"]),
        label=raw.get("label", ""),
        code=raw.get("code"),
        full_label=raw.get("full_label", raw.get("label", "")),
        kind=_kind_by_code(raw.get("code")),
    )


def _kind_by_code(code: str | None) -> NodeKind:
    if not code:
        return NodeKind.ROOT
    dots = code.count(".")
    if dots == 0:
        return NodeKind.SECTION
    if dots == 1:
        return NodeKind.SUBSECTION
    return NodeKind.LEAF


def _node_to_raw(n: Node) -> dict:
    return {
        "id": n.id.value,
        "code": n.code,
        "label": n.label,
        "full_label": n.full_label,
        "description": "",
    }


def _edge_to_raw(edge: Edge) -> dict:
    return {
        "source": edge.source.value,
        "target": edge.target.value,
        "predicate": edge.predicate,
        "llm_descriptions": [{"text": d.text, "source": d.source} for d in edge.descriptions],
    }


def _read_descriptions(raw_link: dict, nodes_by_id: dict[str, dict]) -> tuple[Description, ...]:
    raw = raw_link.get("llm_descriptions")
    if isinstance(raw, list) and raw:
        out: list[Description] = []
        for d in raw:
            if isinstance(d, dict) and "text" in d:
                out.append(Description(text=d["text"], source=d.get("source", "stored")))
            elif isinstance(d, str) and d.strip():
                out.append(Description(text=d.strip(), source="stored"))
        if out:
            return tuple(out)
    target_node = nodes_by_id.get(raw_link["target"], {})
    legacy = target_node.get("llm_descriptions")
    if isinstance(legacy, list):
        return tuple(
            Description(text=s, source="legacy") for s in legacy if isinstance(s, str) and s
        )
    if isinstance(legacy, str) and legacy.strip():
        return (Description(text=legacy.strip(), source="legacy"),)
    return ()
