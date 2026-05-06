from __future__ import annotations

import numpy as np

from backend.services.embedder import TextEmbedder
from backend.services.ontology import Node, Ontology, build_anchor_texts


class CascadeClassifier:
    def __init__(self, embedder: TextEmbedder, ontology: Ontology):
        self.embedder = embedder
        self.ontology = ontology
        self._anchor_cache: dict[str, np.ndarray] = {}

    def _get_node_embeddings(self, node: Node) -> np.ndarray:
        if node.id not in self._anchor_cache:
            anchors = build_anchor_texts(node)
            embs = np.stack([self.embedder.encode_single(a) for a in anchors])
            self._anchor_cache[node.id] = embs
        return self._anchor_cache[node.id]

    def _compute_similarities(
        self,
        query_emb: np.ndarray,
        nodes: list[Node],
    ) -> list[tuple[Node, float]]:
        if not nodes:
            return []

        similarities = np.empty(len(nodes), dtype=np.float32)
        for i, node in enumerate(nodes):
            anchor_embs = self._get_node_embeddings(node)
            similarities[i] = float(np.max(anchor_embs @ query_emb))
        sorted_indices = np.argsort(similarities)[::-1]

        return [(nodes[i], float(similarities[i])) for i in sorted_indices]

    def classify_level(
        self,
        text: str,
        parent_node_id: str | None = None,
        top_k: int = 5,
    ) -> list[tuple[Node, float]]:
        query_emb = self.embedder.encode_single(text)

        if parent_node_id is None:
            candidates = self.ontology.children(self.ontology.root_id)
        else:
            candidates = self.ontology.children(parent_node_id)

        ranked = self._compute_similarities(query_emb, candidates)
        return ranked[:top_k]

    def classify_l1(self, text: str, top_k: int = 5) -> list[tuple[Node, float]]:
        return self.classify_level(text, parent_node_id=None, top_k=top_k)

    def classify_l2(
        self,
        text: str,
        l1_code: str,
        top_k: int = 5,
    ) -> list[tuple[Node, float]]:
        l1_node = self.ontology.code_to_node(l1_code)
        if l1_node is None:
            raise ValueError(f"Invalid L1 code: {l1_code}")
        return self.classify_level(text, parent_node_id=l1_node.id, top_k=top_k)

    def classify_l3(
        self,
        text: str,
        l2_code: str,
        top_k: int = 5,
    ) -> list[tuple[Node, float]]:
        l2_node = self.ontology.code_to_node(l2_code)
        if l2_node is None:
            raise ValueError(f"Invalid L2 code: {l2_code}")
        return self.classify_level(text, parent_node_id=l2_node.id, top_k=top_k)

    def classify_full(
        self,
        text: str,
        top_k: int = 10,
        beam_width: int = 5,
    ) -> list[tuple[list[Node], float]]:
        query_emb = self.embedder.encode_single(text)

        l1_candidates = self.ontology.children(self.ontology.root_id)
        l1_ranked = self._compute_similarities(query_emb, l1_candidates)[:beam_width]

        l2_beams: list[tuple[list[Node], float]] = []

        for l1_node, l1_score in l1_ranked:
            l2_candidates = self.ontology.children(l1_node.id)
            if not l2_candidates:
                continue
            l2_ranked = self._compute_similarities(query_emb, l2_candidates)[:beam_width]

            for l2_node, l2_score in l2_ranked:
                agg_score = np.sqrt(l1_score * l2_score)
                l2_beams.append(([l1_node, l2_node], float(agg_score)))

        l2_beams.sort(key=lambda x: x[1], reverse=True)
        l2_beams = l2_beams[:beam_width]

        l3_results: list[tuple[list[Node], float]] = []

        for path, l2_agg_score in l2_beams:
            l2_node = path[-1]
            l3_candidates = self.ontology.children(l2_node.id)
            if not l3_candidates:
                continue
            l3_ranked = self._compute_similarities(query_emb, l3_candidates)[:beam_width]

            for l3_node, l3_score in l3_ranked:
                l1_score = l1_ranked[0][1] if l1_ranked else 1.0
                final_score = np.power(l1_score * l2_agg_score * l3_score, 1/3)
                full_path = path + [l3_node]
                l3_results.append((full_path, float(final_score)))

        l3_results.sort(key=lambda x: x[1], reverse=True)
        return l3_results[:top_k]
