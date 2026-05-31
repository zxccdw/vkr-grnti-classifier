const ROOT_ID = "http://example.org/grnti_root";
const PREDICATE_LABEL = "содержит";

const state = {
    selectedL1: null,
    selectedL2: null,
    currentRoot: null,
    nodesById: new Map(),
    parentsByTarget: new Map(),
    selectedNodeId: null,
    simulation: null,
};

const els = {
    l1: document.getElementById("l1-input"),
    l2: document.getElementById("l2-input"),
    depth: document.getElementById("depth-input"),
    openBtn: document.getElementById("open-btn"),
    backfillBtn: document.getElementById("backfill-btn"),
    mergeBtn: document.getElementById("merge-btn"),
    status: document.getElementById("status-msg"),
    details: document.getElementById("node-details"),
    addBtn: document.getElementById("add-btn"),
    attachBtn: document.getElementById("attach-btn"),
    importInput: document.getElementById("import-input"),
    svg: d3.select("#graph"),

    modalAdd: document.getElementById("modal-add"),
    modalAddParent: document.getElementById("modal-add-parent"),
    newLabel: document.getElementById("new-label"),
    newCode: document.getElementById("new-code"),
    modalAddError: document.getElementById("modal-add-error"),
    modalAddLoader: document.getElementById("modal-add-loader"),
    modalAddSubmit: document.getElementById("modal-add-submit"),
    modalAddCancel: document.getElementById("modal-add-cancel"),

    modalAttach: document.getElementById("modal-attach"),
    modalAttachParent: document.getElementById("modal-attach-parent"),
    attachTarget: document.getElementById("attach-target"),
    modalAttachError: document.getElementById("modal-attach-error"),
    modalAttachLoader: document.getElementById("modal-attach-loader"),
    modalAttachSubmit: document.getElementById("modal-attach-submit"),
    modalAttachCancel: document.getElementById("modal-attach-cancel"),
};

const combos = {
    l1: createCombobox("l1", {
        onSelect: async (node) => {
            state.selectedL1 = node ? node.id : null;
            state.selectedL2 = null;
            combos.l2.clear();
            els.l2.disabled = !node;
            els.openBtn.disabled = !node;
            if (!node) return;
            setStatus("Загружаю подразделы L2…");
            try {
                const sg = await fetchSubgraph(node.id, 1);
                const subs = sg.nodes
                    .filter((n) => n.kind === "SUBSECTION")
                    .sort((a, b) => (a.code || "").localeCompare(b.code || ""));
                combos.l2.setItems(subs);
                setStatus(`${subs.length} подразделов`);
            } catch (e) {
                setStatus(`Ошибка: ${e.message}`, true);
            }
        },
    }),
    l2: createCombobox("l2", {
        onSelect: (node) => {
            state.selectedL2 = node ? node.id : null;
            els.openBtn.disabled = !state.selectedL1;
        },
    }),
    attach: createCombobox("attach", {
        searchEndpoint: "/api/v1/search",
    }),
};

init();

async function init() {
    els.openBtn.addEventListener("click", openScope);
    els.addBtn.addEventListener("click", openAddModal);
    els.attachBtn.addEventListener("click", openAttachModal);
    els.backfillBtn.addEventListener("click", runBackfill);
    els.mergeBtn.addEventListener("click", runMerge);
    els.importInput.addEventListener("change", uploadOntology);
    els.modalAddCancel.addEventListener("click", () => (els.modalAdd.hidden = true));
    els.modalAddSubmit.addEventListener("click", submitAddNode);
    els.modalAttachCancel.addEventListener("click", () => (els.modalAttach.hidden = true));
    els.modalAttachSubmit.addEventListener("click", submitAttachEdge);

    setStatus("Загружаю разделы L1…");
    try {
        const sg = await fetchSubgraph(ROOT_ID, 1);
        const sections = sg.nodes
            .filter((n) => n.kind === "SECTION")
            .sort((a, b) => (a.code || "").localeCompare(b.code || ""));
        combos.l1.setItems(sections);
        setStatus(`${sections.length} разделов загружено`);
    } catch (e) {
        setStatus(`Ошибка загрузки: ${e.message}`, true);
    }
}

function createCombobox(name, { searchEndpoint = null, onSelect } = {}) {
    const container = document.querySelector(`.combobox[data-cb="${name}"]`);
    const input = container.querySelector("input");
    const popup = container.querySelector(".combobox-popup");
    let items = [];
    let selected = null;
    let searchTimer = null;

    function render(list) {
        popup.innerHTML = "";
        if (list.length === 0) {
            const empty = document.createElement("div");
            empty.className = "combobox-empty";
            empty.textContent = "Ничего не найдено";
            popup.appendChild(empty);
            return;
        }
        for (const node of list) {
            const opt = document.createElement("div");
            opt.className = "combobox-option";
            opt.innerHTML = `
                <span class="combobox-option-code">${escapeHtml(node.code || "—")}</span>
                <span class="combobox-option-label">${escapeHtml(node.label)}</span>
            `;
            opt.addEventListener("mousedown", (e) => {
                e.preventDefault();
                pick(node);
            });
            popup.appendChild(opt);
        }
    }

    function filterLocal(q) {
        const lower = q.toLowerCase();
        if (!lower) return items.slice(0, 100);
        return items.filter((n) =>
            (n.label || "").toLowerCase().includes(lower) ||
            (n.code || "").toLowerCase().includes(lower)
        ).slice(0, 100);
    }

    async function fetchRemote(q) {
        clearTimeout(searchTimer);
        if (!searchEndpoint) return;
        if (q.length < 2) {
            render([]);
            return;
        }
        searchTimer = setTimeout(async () => {
            try {
                const resp = await fetch(`${searchEndpoint}?q=${encodeURIComponent(q)}&limit=80`);
                if (!resp.ok) return;
                const remote = await resp.json();
                items = remote;
                render(remote);
            } catch {
                /* ignore */
            }
        }, 180);
    }

    function pick(node) {
        selected = node;
        input.value = `${node.code || "—"} · ${node.label}`;
        popup.hidden = true;
        onSelect && onSelect(node);
    }

    input.addEventListener("focus", () => {
        if (input.disabled) return;
        if (searchEndpoint && input.value.length < 2) {
            render([]);
        } else {
            render(filterLocal(input.value));
        }
        popup.hidden = false;
    });
    input.addEventListener("input", () => {
        selected = null;
        onSelect && onSelect(null);
        if (searchEndpoint) {
            fetchRemote(input.value.trim());
        } else {
            render(filterLocal(input.value));
        }
        popup.hidden = false;
    });
    input.addEventListener("blur", () => {
        setTimeout(() => (popup.hidden = true), 150);
    });

    return {
        setItems(newItems) {
            items = newItems;
            selected = null;
            input.value = "";
        },
        getSelected() {
            return selected;
        },
        clear() {
            items = [];
            selected = null;
            input.value = "";
            popup.innerHTML = "";
        },
    };
}

async function openScope() {
    const rootId = state.selectedL2 || state.selectedL1;
    if (!rootId) return;
    const depthValue = parseInt(els.depth.value, 10);
    const depth = Number.isFinite(depthValue) && depthValue >= 1
        ? Math.min(depthValue, 10)
        : (state.selectedL2 ? 3 : 4);
    state.currentRoot = rootId;
    state.selectedNodeId = null;
    els.addBtn.disabled = true;
    els.attachBtn.disabled = true;
    els.details.innerHTML = '<p class="muted">Кликни по узлу графа.</p>';

    setStatus("Загружаю поддерево…");
    try {
        const sg = await fetchSubgraph(rootId, depth);
        renderGraph(sg);
        setStatus(`${sg.nodes.length} узлов, ${sg.edges.length} рёбер`);
        updateBackfillBtn(sg);
    } catch (e) {
        setStatus(`Ошибка: ${e.message}`, true);
    }
}

function updateBackfillBtn(sg) {
    const pending = sg.edges.filter((e) => e.descriptions.length === 0).length;
    els.backfillBtn.textContent = pending > 0
        ? `Догнать описания (${pending})`
        : "Догнать описания";
    els.backfillBtn.disabled = pending === 0;
}

async function runBackfill() {
    els.backfillBtn.disabled = true;
    setStatus("Догоняю описания через LLM…");
    try {
        const resp = await fetch("/api/v1/backfill", { method: "POST" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body = await resp.json();
        setStatus(`Заполнено: ${body.filled}, осталось: ${body.still_pending}`);
        toast(`Заполнено: ${body.filled} описаний. Осталось: ${body.still_pending}`, "success");
        await openScope();
    } catch (e) {
        setStatus(`Ошибка backfill: ${e.message}`, true);
        els.backfillBtn.disabled = false;
    }
}

async function runMerge() {
    if (!confirm("Объединить семантические дубликаты (один URI на label+суффикс)? Структура изменится.")) {
        return;
    }
    els.mergeBtn.disabled = true;
    setStatus("Объединяю дубликаты…");
    try {
        const resp = await fetch("/api/v1/merge-duplicates", { method: "POST" });
        if (!resp.ok) {
            const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
            throw new Error(detail);
        }
        const body = await resp.json();
        toast(
            `Объединено ${body.groups_merged} групп, удалено ${body.nodes_removed} узлов, перепривязано ${body.edges_redirected} рёбер`,
            "success"
        );
        setTimeout(() => window.location.reload(), 1200);
    } catch (e) {
        setStatus(`Ошибка merge: ${e.message}`, true);
    } finally {
        els.mergeBtn.disabled = false;
    }
}

async function uploadOntology(event) {
    const file = event.target.files[0];
    if (!file) return;
    setStatus(`Загружаю ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    try {
        const resp = await fetch("/api/v1/import/ontology", {
            method: "POST",
            body: form,
        });
        if (!resp.ok) {
            const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
            throw new Error(detail);
        }
        const body = await resp.json();
        setStatus(`Загружено: ${body.nodes} узлов, ${body.links} рёбер`);
        toast(`JSON загружен: ${body.nodes} узлов, ${body.links} рёбер. Перезагружаю…`, "success");
        setTimeout(() => window.location.reload(), 1200);
    } catch (e) {
        setStatus(`Ошибка загрузки: ${e.message}`, true);
    } finally {
        event.target.value = "";
    }
}

async function fetchSubgraph(rootId, maxDepth) {
    const url = `/api/v1/subgraph?root_id=${encodeURIComponent(rootId)}&max_depth=${maxDepth}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

async function fetchParents(nodeId) {
    const url = `/api/v1/parents?node_id=${encodeURIComponent(nodeId)}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

function renderGraph(sg) {
    state.nodesById = new Map(sg.nodes.map((n) => [n.id, n]));
    state.parentsByTarget = new Map();
    for (const e of sg.edges) {
        if (!state.parentsByTarget.has(e.target)) state.parentsByTarget.set(e.target, new Set());
        state.parentsByTarget.get(e.target).add(e.source);
    }
    if (state.simulation) state.simulation.stop();

    const svgEl = els.svg.node();
    const width = svgEl.clientWidth;
    const height = svgEl.clientHeight;

    els.svg.selectAll("*").remove();
    const root = els.svg.append("g");
    els.svg.call(d3.zoom().scaleExtent([0.2, 4]).on("zoom", (e) => root.attr("transform", e.transform)));

    const nodes = sg.nodes.map((n) => ({ ...n }));
    const links = sg.edges.map((e) => ({
        source: e.source,
        target: e.target,
        predicate: e.predicate,
        descriptions: e.descriptions,
    }));

    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id((d) => d.id).distance(80))
        .force("charge", d3.forceManyBody().strength(-220))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collide", d3.forceCollide(28));
    state.simulation = simulation;

    const linkG = root.append("g").attr("class", "links").selectAll("g.link")
        .data(links).enter().append("g").attr("class", "link");
    linkG.append("line").attr("class", "link");
    linkG.append("text").attr("class", "link-label").text(PREDICATE_LABEL);

    const nodeG = root.append("g").attr("class", "nodes").selectAll("g.node")
        .data(nodes, (d) => d.id).enter().append("g")
        .attr("class", (d) => {
            const parents = state.parentsByTarget.get(d.id);
            const multi = parents && parents.size > 1 ? " multi-parent" : "";
            return `node kind-${d.kind}${multi}`;
        })
        .call(d3.drag()
            .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
            .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
            .on("end", (e) => { if (!e.active) simulation.alphaTarget(0); }));

    nodeG.append("circle").attr("r", 14);
    nodeG.append("text").attr("dx", 18).attr("dy", 4).text((d) => truncate(d.label, 32));

    nodeG.on("click", (_, d) => selectNode(d.id));

    simulation.on("tick", () => {
        linkG.select("line")
            .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
            .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
        linkG.select("text")
            .attr("x", (d) => (d.source.x + d.target.x) / 2)
            .attr("y", (d) => (d.source.y + d.target.y) / 2);
        nodeG.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });
}

async function selectNode(id) {
    state.selectedNodeId = id;
    d3.selectAll("g.node").classed("selected", function () {
        return d3.select(this).datum().id === id;
    });
    const node = state.nodesById.get(id);
    if (!node) return;
    els.addBtn.disabled = node.kind === "ROOT";
    els.attachBtn.disabled = node.kind === "ROOT";

    let parents = { parents: [] };
    try {
        parents = await fetchParents(id);
    } catch {
        /* ignore */
    }
    renderDetails(node, parents.parents);
}

function renderDetails(node, parentEdges) {
    const parentBlock = parentEdges.length
        ? `<div class="parents-block">
                <h3>Родители (${parentEdges.length})</h3>
                ${parentEdges.map((edge) => {
                    const parentNode = state.nodesById.get(edge.source);
                    const parentLabel = parentNode
                        ? `${parentNode.code || "—"} · ${escapeHtml(parentNode.label)}`
                        : edge.source;
                    const descs = edge.descriptions.length
                        ? `<div class="descriptions">${edge.descriptions.map((d) => `
                            <div class="description-item">
                                <div class="description-source">${d.source}</div>
                                <div>${escapeHtml(d.text)}</div>
                            </div>`).join("")}</div>`
                        : '<div class="pending-banner">Описание не сгенерировано для этого пути.</div>';
                    return `<details class="parent-edge">
                        <summary>${parentLabel} <span class="muted">(${edge.descriptions.length})</span></summary>
                        ${descs}
                    </details>`;
                }).join("")}
            </div>`
        : '<p class="muted">Узел без родителей (сирота).</p>';

    els.details.innerHTML = `
        <dl class="node-details">
            <dt>Код</dt><dd><code>${node.code || "—"}</code></dd>
            <dt>Название</dt><dd>${escapeHtml(node.label)}</dd>
            <dt>Полный путь</dt><dd>${escapeHtml(node.full_label)}</dd>
            <dt>Уровень</dt><dd>${node.kind}</dd>
        </dl>
        ${parentBlock}
    `;
}

function openAddModal() {
    const parent = state.nodesById.get(state.selectedNodeId);
    if (!parent) {
        setStatus("Сначала кликни по узлу графа", true);
        return;
    }
    els.modalAddParent.textContent = `Родитель: ${parent.code || "—"} · ${parent.label}`;
    els.newLabel.value = "";
    els.newCode.value = parent.code ? `${parent.code}.` : "";
    els.modalAddError.hidden = true;
    els.modalAddLoader.hidden = true;
    els.modalAddSubmit.disabled = false;
    els.modalAdd.hidden = false;
    els.newLabel.focus();
}

async function submitAddNode() {
    const label = els.newLabel.value.trim();
    const code = els.newCode.value.trim();
    if (!label || !code) {
        showError(els.modalAddError, "Заполните оба поля");
        return;
    }
    els.modalAddSubmit.disabled = true;
    els.modalAddLoader.hidden = false;
    els.modalAddError.hidden = true;
    try {
        const resp = await fetch("/api/v1/nodes/with-edge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ parent_id: state.selectedNodeId, label, code }),
        });
        if (!resp.ok) {
            const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
            throw new Error(detail);
        }
        els.modalAdd.hidden = true;
        toast("Узел создан и описание сгенерировано", "success");
        await openScope();
    } catch (e) {
        showError(els.modalAddError, e.message);
        els.modalAddSubmit.disabled = false;
        els.modalAddLoader.hidden = true;
    }
}

function openAttachModal() {
    const parent = state.nodesById.get(state.selectedNodeId);
    if (!parent) {
        setStatus("Сначала кликни по узлу графа", true);
        return;
    }
    els.modalAttachParent.textContent = `Источник: ${parent.code || "—"} · ${parent.label}`;
    combos.attach.clear();
    els.modalAttachError.hidden = true;
    els.modalAttachLoader.hidden = true;
    els.modalAttachSubmit.disabled = false;
    els.modalAttach.hidden = false;
    els.attachTarget.focus();
}

async function submitAttachEdge() {
    const target = combos.attach.getSelected();
    if (!target) {
        showError(els.modalAttachError, "Выбери узел из подсказок");
        return;
    }
    if (target.id === state.selectedNodeId) {
        showError(els.modalAttachError, "Нельзя привязать узел сам к себе");
        return;
    }
    els.modalAttachSubmit.disabled = true;
    els.modalAttachLoader.hidden = false;
    els.modalAttachError.hidden = true;
    try {
        const resp = await fetch("/api/v1/edges", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_id: state.selectedNodeId, target_id: target.id }),
        });
        if (!resp.ok) {
            const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
            throw new Error(detail);
        }
        els.modalAttach.hidden = true;
        toast("Связь создана и описание сгенерировано", "success");
        await openScope();
    } catch (e) {
        showError(els.modalAttachError, e.message);
        els.modalAttachSubmit.disabled = false;
        els.modalAttachLoader.hidden = true;
    }
}

function showError(el, msg) {
    el.textContent = msg;
    el.hidden = false;
    toast(msg, "error");
}

function setStatus(msg, isError = false) {
    els.status.textContent = msg;
    els.status.classList.toggle("error", isError);
    if (isError) toast(msg, "error", "Ошибка");
}

const TOAST_TITLES = {
    error: "Ошибка",
    success: "Готово",
    info: "Инфо",
};

function toast(message, kind = "info", title = null) {
    const container = document.getElementById("toasts");
    if (!container) return;
    const el = document.createElement("div");
    el.className = `toast toast-${kind}`;
    const t = title || TOAST_TITLES[kind] || "";
    el.innerHTML = `
        <div class="toast-body">
            ${t ? `<div class="toast-title">${escapeHtml(t)}</div>` : ""}
            <div>${escapeHtml(message)}</div>
        </div>
        <button class="toast-close" aria-label="Закрыть">×</button>
    `;
    const close = () => {
        if (!el.parentNode) return;
        el.classList.add("toast-leave");
        setTimeout(() => el.remove(), 180);
    };
    el.querySelector(".toast-close").addEventListener("click", close);
    container.appendChild(el);
    setTimeout(close, 5500);
}

function truncate(s, n) {
    return s && s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
}
