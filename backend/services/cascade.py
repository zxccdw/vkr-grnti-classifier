from __future__ import annotations

import gzip
import logging
import pickle
from pathlib import Path

import numpy as np

from backend.services.embedder import TextEmbedder
from backend.services.ontology import Node, Ontology, build_anchor_texts

logger = logging.getLogger(__name__)


class CascadeClassifier:
    def __init__(self, embedder: TextEmbedder, ontology: Ontology):
        self.embedder = embedder
        self.ontology = ontology
        self._anchor_cache: dict[tuple[str, str], np.ndarray] = {}

    def save_cache(self, path: Path | str) -> int:
        data = {k: v.astype(np.float16) for k, v in self._anchor_cache.items()}
        with gzip.open(str(path), "wb", compresslevel=6) as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        return len(data)

    def load_cache(self, path: Path | str) -> int:
        with gzip.open(str(path), "rb") as f:
            data: dict = pickle.load(f)
        for k, v in data.items():
            if k not in self._anchor_cache:
                self._anchor_cache[k] = np.asarray(v, dtype=np.float32)
        return len(data)

    def clear_cache(self) -> None:
        """Clear embeddings cache when ontology changes."""
        self._anchor_cache.clear()

    def cleanup_cache(self) -> None:
        """Remove embeddings for nodes that no longer exist in ontology."""
        all_node_ids = {node.id for node in self.ontology.all_nodes()}
        to_remove = [
            key
            for key in self._anchor_cache.keys()
            if key[1] not in all_node_ids  # key is (parent_id, node_id)
        ]

        if to_remove:
            for key in to_remove:
                del self._anchor_cache[key]
            logger.info(
                f"Cleaned {len(to_remove)} stale embeddings from cache (cache now has {len(self._anchor_cache)} entries)"
            )
        else:
            logger.debug(
                f"No stale embeddings to clean (cache has {len(self._anchor_cache)} entries)"
            )

    def _anchor_texts(self, parent_id: str, node: Node) -> list[str]:
        anchors = list(build_anchor_texts(node))
        anchors.extend(self.ontology.edge_anchors(parent_id, node.id))
        seen: set[str] = set()
        deduped: list[str] = []
        for a in anchors:
            if a and a not in seen:
                seen.add(a)
                deduped.append(a)
        return deduped or [node.label or node.id]

    def _prefill_cache(self, parent_id: str, nodes: list[Node]) -> None:
        """Batch-encode anchors for all uncached nodes in one API call."""
        missing = [n for n in nodes if (parent_id, n.id) not in self._anchor_cache]
        if not missing:
            return
        per_node = [self._anchor_texts(parent_id, n) for n in missing]
        flat: list[str] = []
        offsets: list[int] = []
        for texts in per_node:
            offsets.append(len(flat))
            flat.extend(texts)
        all_embs = self.embedder.encode(flat)
        for j, node in enumerate(missing):
            start = offsets[j]
            end = offsets[j + 1] if j + 1 < len(offsets) else len(flat)
            self._anchor_cache[(parent_id, node.id)] = all_embs[start:end]

    def _compute_similarities(
        self,
        query_emb: np.ndarray,
        parent_id: str,
        nodes: list[Node],
    ) -> list[tuple[Node, float]]:
        if not nodes:
            return []
        self._prefill_cache(parent_id, nodes)
        similarities = np.empty(len(nodes), dtype=np.float32)
        for i, node in enumerate(nodes):
            anchor_embs = self._anchor_cache[(parent_id, node.id)]
            similarities[i] = float(np.max(anchor_embs @ query_emb))
        sorted_indices = np.argsort(similarities)[::-1]
        return [(nodes[i], float(similarities[i])) for i in sorted_indices]

    def classify_level(
        self,
        text: str,
        parent_node_id: str | None = None,
        top_k: int = 12,
    ) -> list[tuple[Node, float]]:
        query_emb = self.embedder.encode_single(text)
        parent_id = parent_node_id or self.ontology.root_id
        candidates = self.ontology.children(parent_id)
        ranked = self._compute_similarities(query_emb, parent_id, candidates)
        return ranked[:top_k]

    def classify_l1(self, text: str, top_k: int = 12) -> list[tuple[Node, float]]:
        return self.classify_level(text, parent_node_id=None, top_k=top_k)

    def classify_l2(
        self,
        text: str,
        l1_code: str,
        top_k: int = 12,
    ) -> list[tuple[Node, float]]:
        l1_node = self.ontology.code_to_node(l1_code)
        if l1_node is None:
            raise ValueError(f"Invalid L1 code: {l1_code}")
        return self.classify_level(text, parent_node_id=l1_node.id, top_k=top_k)

    def classify_l3(
        self,
        text: str,
        l2_code: str,
        top_k: int = 12,
    ) -> list[tuple[Node, float]]:
        l2_node = self.ontology.code_to_node(l2_code)
        if l2_node is None:
            raise ValueError(f"Invalid L2 code: {l2_code}")
        return self.classify_level(text, parent_node_id=l2_node.id, top_k=top_k)

    def classify_full(
        self,
        text: str,
        top_k: int = 12,
        beam_width: int = 10,
    ) -> list[tuple[list[Node], float]]:
        query_emb = self.embedder.encode_single(text)
        root_id = self.ontology.root_id

        # Start from root
        candidates = self.ontology.children(root_id)
        current_paths: list[tuple[list[Node], float]] = [
            ([node], float(score))
            for node, score in self._compute_similarities(query_emb, root_id, candidates)[
                :beam_width
            ]
        ]

        result_paths: list[tuple[list[Node], float]] = []

        # Expand paths level by level until we have enough leaf paths
        for _ in range(10):  # Max 10 levels to prevent infinite loops
            next_paths: list[tuple[list[Node], float]] = []

            for path, path_score in current_paths:
                last_node = path[-1]
                children = self.ontology.children(last_node.id)

                if not children:
                    # Leaf node - add to results
                    result_paths.append((path, path_score))
                else:
                    # Non-leaf - expand to children
                    ranked = self._compute_similarities(query_emb, last_node.id, children)[
                        :beam_width
                    ]
                    for child_node, child_score in ranked:
                        # Geometric mean of all scores
                        num_levels = len(path) + 1
                        combined_score = np.power(path_score * child_score, 1 / num_levels)
                        next_paths.append((path + [child_node], float(combined_score)))

            if not next_paths:
                # No more paths to expand
                break

            # Keep top beam_width paths for next iteration
            next_paths.sort(key=lambda x: x[1], reverse=True)
            current_paths = next_paths[:beam_width]

            if len(result_paths) >= top_k:
                break

        # Return top_k leaf paths
        result_paths.sort(key=lambda x: x[1], reverse=True)
        return result_paths[:top_k]
