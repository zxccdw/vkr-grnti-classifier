from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.nodes import router
from backend.application.add_node import AddNode
from backend.application.attach_edge import AttachEdge
from backend.application.backfill_descriptions import BackfillDescriptions
from backend.application.create_node import CreateNode
from backend.core.dependencies import (
    get_add_node_use_case,
    get_attach_edge_use_case,
    get_backfill_use_case,
    get_create_node_use_case,
    get_ontology_repository,
)
from backend.infrastructure.json_ontology import (
    PREDICATE_CONTAINS,
    JsonOntologyRepository,
)

ROOT_ID = "http://example.org/grnti_root"
L1_ID = "http://example.org/competencies#GRNTI_34"
L2_ID = "http://example.org/competencies#GRNTI_34_15"
L2_OTHER_ID = "http://example.org/competencies#GRNTI_34_16"
L3_ID = "http://example.org/competencies#GRNTI_34_15_23"


def _seed_ontology(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": ROOT_ID, "label": "ГРНТИ", "code": None, "full_label": "ГРНТИ"},
                    {"id": L1_ID, "label": "Биология", "code": "34", "full_label": "Биология"},
                    {
                        "id": L2_ID,
                        "label": "Генетика",
                        "code": "34.15",
                        "full_label": "Биология → Генетика",
                    },
                    {
                        "id": L2_OTHER_ID,
                        "label": "Мол.био",
                        "code": "34.16",
                        "full_label": "Биология → Мол.био",
                    },
                    {
                        "id": L3_ID,
                        "label": "Геномика",
                        "code": "34.15.23",
                        "full_label": "Биология → Генетика → Геномика",
                    },
                ],
                "links": [
                    {"source": ROOT_ID, "target": L1_ID, "predicate": PREDICATE_CONTAINS},
                    {"source": L1_ID, "target": L2_ID, "predicate": PREDICATE_CONTAINS},
                    {"source": L1_ID, "target": L2_OTHER_ID, "predicate": PREDICATE_CONTAINS},
                    {
                        "source": L2_ID,
                        "target": L3_ID,
                        "predicate": PREDICATE_CONTAINS,
                        "llm_descriptions": [{"text": "stored", "source": "gigachat"}],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class FakeProvider:
    def __init__(self, name: str, returns: list[str]) -> None:
        self.name = name
        self._returns = returns

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        return list(self._returns)


class FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        raise RuntimeError("down")


@pytest.fixture
def repo(tmp_path: Path) -> JsonOntologyRepository:
    onto = tmp_path / "ontology.json"
    snaps = tmp_path / "snapshots"
    _seed_ontology(onto)
    return JsonOntologyRepository(onto, snaps)


def _client(repo: JsonOntologyRepository, providers: list) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_ontology_repository] = lambda: repo
    app.dependency_overrides[get_create_node_use_case] = lambda: CreateNode(repo)
    app.dependency_overrides[get_attach_edge_use_case] = lambda: AttachEdge(repo, providers)
    app.dependency_overrides[get_add_node_use_case] = lambda: AddNode(repo, providers)
    app.dependency_overrides[get_backfill_use_case] = lambda: BackfillDescriptions(repo, providers)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client_ok(repo: JsonOntologyRepository) -> Iterator[TestClient]:
    yield from _client(
        repo,
        [
            FakeProvider("gigachat", ["g1", "g2"]),
            FakeProvider("yagpt", ["y1"]),
        ],
    )


@pytest.fixture
def client_no_llm(repo: JsonOntologyRepository) -> Iterator[TestClient]:
    yield from _client(repo, [FailingProvider("gigachat")])


def test_create_node_returns_201_orphan_without_descriptions(client_ok: TestClient) -> None:
    response = client_ok.post("/api/v1/nodes", json={"label": "Сирота", "code": "34.99.99"})
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Сирота"
    assert data["kind"] == "LEAF"


def test_create_node_with_edge_returns_node_and_edge(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/nodes/with-edge",
        json={"parent_id": L2_ID, "label": "Протеомика", "code": "34.15.55"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["node"]["label"] == "Протеомика"
    assert data["edge"]["source"] == L2_ID
    assert {d["source"] for d in data["edge"]["descriptions"]} == {"gigachat", "yagpt"}


def test_attach_orphan_with_matching_prefix_succeeds(client_ok: TestClient) -> None:
    client_ok.post(
        "/api/v1/nodes",
        json={"label": "Sub leaf", "code": "34.15.23.1"},
    )
    response = client_ok.post(
        "/api/v1/edges",
        json={
            "source_id": L3_ID,
            "target_id": "http://example.org/competencies#GRNTI_34_15_23_1",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert {d["source"] for d in data["descriptions"]} == {"gigachat", "yagpt"}


def test_attach_with_mismatched_code_prefix_returns_422(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/edges",
        json={"source_id": L2_OTHER_ID, "target_id": L3_ID},
    )
    assert response.status_code == 422


def test_attach_edge_duplicate_returns_409(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/edges",
        json={"source_id": L2_ID, "target_id": L3_ID},
    )
    assert response.status_code == 409


def test_attach_edge_invalid_depth_returns_422(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/edges",
        json={"source_id": ROOT_ID, "target_id": L3_ID},
    )
    assert response.status_code == 422


def test_attach_edge_missing_node_returns_404(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/edges",
        json={"source_id": "urn:nope", "target_id": L3_ID},
    )
    assert response.status_code == 404


def test_attach_edge_without_llm_creates_pending_edge(client_no_llm: TestClient) -> None:
    client_no_llm.post(
        "/api/v1/nodes",
        json={"label": "Sub", "code": "34.15.23.9"},
    )
    response = client_no_llm.post(
        "/api/v1/edges",
        json={
            "source_id": L3_ID,
            "target_id": "http://example.org/competencies#GRNTI_34_15_23_9",
        },
    )
    assert response.status_code == 201
    assert response.json()["descriptions"] == []


def test_subgraph_returns_edges_with_descriptions(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/subgraph", params={"root_id": L1_ID, "max_depth": 2})
    assert response.status_code == 200
    data = response.json()
    edge_to_leaf = next(e for e in data["edges"] if e["target"] == L3_ID)
    assert edge_to_leaf["descriptions"][0]["text"] == "stored"


def test_parents_endpoint_returns_incoming_edges(
    client_ok: TestClient, repo: JsonOntologyRepository
) -> None:
    response = client_ok.get("/api/v1/parents", params={"node_id": L3_ID})
    assert response.status_code == 200
    data = response.json()
    assert {e["source"] for e in data["parents"]} == {L2_ID}


def test_backfill_returns_filled_and_pending_counts(client_ok: TestClient) -> None:
    response = client_ok.post("/api/v1/backfill")
    assert response.status_code == 200
    body = response.json()
    assert body["filled"] >= 1
    assert body["still_pending"] == 0


def test_search_finds_by_label_substring(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/search", params={"q": "генет"})
    assert response.status_code == 200
    data = response.json()
    assert any(n["id"] == L2_ID for n in data)


def test_search_finds_by_code_substring(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/search", params={"q": "34.16"})
    assert response.status_code == 200
    data = response.json()
    assert any(n["id"] == L2_OTHER_ID for n in data)


def test_search_respects_limit(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/search", params={"q": "34", "limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_search_empty_query_rejected(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/search", params={"q": ""})
    assert response.status_code == 422


def test_search_no_match_returns_empty(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/search", params={"q": "вообщенетлейбла"})
    assert response.status_code == 200
    assert response.json() == []


def test_import_replaces_ontology(client_ok: TestClient) -> None:
    new_payload = {
        "nodes": [
            {"id": "urn:imported:root", "label": "Root", "code": None},
            {"id": "urn:imported:a", "label": "A", "code": "01"},
        ],
        "links": [
            {
                "source": "urn:imported:root",
                "target": "urn:imported:a",
                "predicate": PREDICATE_CONTAINS,
            },
        ],
    }
    response = client_ok.post(
        "/api/v1/import/ontology",
        files={"file": ("o.json", json.dumps(new_payload), "application/json")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"nodes": 2, "links": 1}

    exported = client_ok.get("/api/v1/export/ontology.json").json()
    assert {n["id"] for n in exported["nodes"]} == {"urn:imported:root", "urn:imported:a"}


def test_import_rejects_invalid_json(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/import/ontology",
        files={"file": ("o.json", b"{not json", "application/json")},
    )
    assert response.status_code == 400


def test_import_rejects_wrong_shape(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/import/ontology",
        files={"file": ("o.json", json.dumps({"foo": "bar"}), "application/json")},
    )
    assert response.status_code == 400


def test_export_returns_full_json(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/export/ontology.json")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "links" in data
    assert any(n["id"] == ROOT_ID for n in data["nodes"])


def test_subgraph_supports_deep_max_depth(client_ok: TestClient) -> None:
    client_ok.post(
        "/api/v1/nodes/with-edge",
        json={"parent_id": L3_ID, "label": "L4 node", "code": "34.15.23.1"},
    )
    client_ok.post(
        "/api/v1/nodes/with-edge",
        json={
            "parent_id": "http://example.org/competencies#GRNTI_34_15_23_1",
            "label": "L5 node",
            "code": "34.15.23.1.1",
        },
    )
    response = client_ok.get(
        "/api/v1/subgraph",
        params={"root_id": L1_ID, "max_depth": 5},
    )
    assert response.status_code == 200
    ids = {n["id"] for n in response.json()["nodes"]}
    assert "http://example.org/competencies#GRNTI_34_15_23_1" in ids
    assert "http://example.org/competencies#GRNTI_34_15_23_1_1" in ids


def test_subgraph_max_depth_above_10_rejected(client_ok: TestClient) -> None:
    response = client_ok.get("/api/v1/subgraph", params={"root_id": L1_ID, "max_depth": 99})
    assert response.status_code == 422


def test_create_node_under_leaf_returns_201(client_ok: TestClient) -> None:
    response = client_ok.post(
        "/api/v1/nodes/with-edge",
        json={"parent_id": L3_ID, "label": "L4", "code": "34.15.23.1"},
    )
    assert response.status_code == 201, response.text


def test_attach_deep_leaf_under_l3_returns_201(client_ok: TestClient) -> None:
    client_ok.post("/api/v1/nodes", json={"label": "Sub leaf", "code": "34.15.23.5"})
    response = client_ok.post(
        "/api/v1/edges",
        json={
            "source_id": L3_ID,
            "target_id": "http://example.org/competencies#GRNTI_34_15_23_5",
        },
    )
    assert response.status_code == 201, response.text


def test_delete_edge_removes_the_link(client_ok: TestClient) -> None:
    response = client_ok.delete(
        "/api/v1/edges",
        params={
            "source": L2_ID,
            "target": L3_ID,
            "predicate": PREDICATE_CONTAINS,
        },
    )
    assert response.status_code == 204
    parents_response = client_ok.get("/api/v1/parents", params={"node_id": L3_ID})
    assert {e["source"] for e in parents_response.json()["parents"]} == set()


def test_delete_edge_missing_returns_404(client_ok: TestClient) -> None:
    response = client_ok.delete(
        "/api/v1/edges",
        params={"source": "urn:nope", "target": L3_ID, "predicate": PREDICATE_CONTAINS},
    )
    assert response.status_code == 404
