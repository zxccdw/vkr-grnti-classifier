// State
let selectedCodes = new Set();
let currentMode = 'full';
let currentStep = null; // {depth, parentCode, code, label}
let stepHistory = []; // [{depth, parentCode, code, label}] — for back navigation

// Cache for classification results
let lastClassifiedText = null;
let lastFullResults = null;
let lastStepResults = null;

// Load selected codes and text from localStorage on startup
function loadSelectedCodes() {
    const saved = localStorage.getItem('grnti_selected_codes');
    console.log('[GRNTI] loadSelectedCodes() - saved:', saved);
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            console.log('[GRNTI] Parsed:', parsed);
            selectedCodes = new Set(parsed);
            console.log('[GRNTI] Set created, size:', selectedCodes.size);
        } catch (e) {
            console.error('[GRNTI] Parse error:', e);
            selectedCodes = new Set();
        }
    } else {
        console.log('[GRNTI] No saved codes in localStorage');
    }
}

function loadTextInput() {
    const saved = localStorage.getItem('grnti_text_input');
    if (saved) {
        textInput.value = saved;
        lastClassifiedText = saved;  // Remember this was already classified
        console.log('[GRNTI] Restored text from localStorage:', saved.substring(0, 50));
    } else {
        console.log('[GRNTI] No saved text in localStorage');
    }
}

// Save selected codes to localStorage
function saveSelectedCodes() {
    const data = JSON.stringify(Array.from(selectedCodes));
    localStorage.setItem('grnti_selected_codes', data);
    console.log('[GRNTI] Saved codes:', Array.from(selectedCodes));
}

function saveTextInput() {
    const text = textInput.value.trim();
    localStorage.setItem('grnti_text_input', text);
    console.log('[GRNTI] Saved text:', text.substring(0, 50) + (text.length > 50 ? '...' : ''));
}

// DOM elements
const textInput = document.getElementById('text-input');
const classifyBtn = document.getElementById('classify-btn');
const loader = document.getElementById('loader');
const errorMsg = document.getElementById('error-msg');
const resultsSection = document.getElementById('results-section');
const resultsGrid = document.getElementById('results-grid');
const resultsTitle = document.getElementById('results-title');
const breadcrumbs = document.getElementById('breadcrumbs');
const selectedSection = document.getElementById('selected-section');
const selectedCodesDiv = document.getElementById('selected-codes');
const exportBtn = document.getElementById('export-btn');
const modeInputs = document.querySelectorAll('input[name="mode"]');

// Initialize localStorage on page load
loadSelectedCodes();
loadTextInput();
renderSelectedCodes();
console.log('[GRNTI] Loaded codes:', Array.from(selectedCodes), 'Text:', textInput.value);

// Event listeners
classifyBtn.addEventListener('click', handleClassify);
exportBtn.addEventListener('click', exportSelectedCodes);
textInput.addEventListener('input', saveTextInput);
modeInputs.forEach(input => {
    input.addEventListener('change', (e) => {
        currentMode = e.target.value;
        resetResults();
    });
});

// Clear cache when user returns from browse (detects page focus)
window.addEventListener('focus', () => {
    lastFullResults = null;
    lastStepResults = null;
});

function handleClassify() {
    const text = textInput.value.trim();
    console.log('[GRNTI] handleClassify:', {
        text: text.substring(0, 30),
        lastClassifiedText: lastClassifiedText ? lastClassifiedText.substring(0, 30) : null,
        selectedCodesCount: selectedCodes.size,
        textChanged: text !== lastClassifiedText,
    });
    if (!text) {
        showError('Введите текст для классификации');
        return;
    }
    hideError();
    saveTextInput();

    // Reset constructor state for fresh start
    stepHistory = [];
    currentStep = null;
    breadcrumbs.style.display = 'none';

    // Only clear and reclassify if text is different
    if (text !== lastClassifiedText) {
        console.log('[GRNTI] Text changed, clearing codes');
        lastClassifiedText = text;
        lastFullResults = null;
        lastStepResults = null;
        selectedCodes.clear();
        renderSelectedCodes();
    } else {
        console.log('[GRNTI] Text same, keeping codes');
    }

    if (currentMode === 'full') {
        if (lastFullResults) {
            renderFullResults(lastFullResults);
        } else {
            runFullCascade(text);
        }
    } else {
        if (lastStepResults) {
            currentStep = {depth: 1, parentCode: null, code: null, label: null};
            renderStepResults(lastStepResults, 1);
            updateBreadcrumbs();
        } else {
            stepHistory = [];
            runStepByStep(text, 1, null);
        }
    }
}

async function runFullCascade(text) {
    showLoader();
    try {
        const response = await fetch('/api/v1/classify/full', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text, top_k: 12}),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        lastFullResults = data.predictions;
        renderFullResults(data.predictions);
    } catch (error) {
        showError(`Ошибка: ${error.message}`);
    } finally {
        hideLoader();
    }
}

async function runStepByStep(text, depth = 1, parentCode = null, code = null, label = null) {
    showLoader();
    const endpoint = !parentCode ? '/api/v1/classify/l1' : '/api/v1/classify/by-parent';
    const body = !parentCode
        ? {text, top_k: 12}
        : {text, parent_code: parentCode, top_k: 12};
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        // Cache L1 results only
        if (depth === 1 && !parentCode) {
            lastStepResults = data.predictions;
        }
        currentStep = {depth, parentCode, code, label};
        renderStepResults(data.predictions, depth);
        updateBreadcrumbs();
    } catch (error) {
        showError(`Ошибка: ${error.message}`);
    } finally {
        hideLoader();
    }
}

function renderFullResults(predictions) {
    console.log('[GRNTI] renderFullResults() - predictions:', predictions.length, 'selectedCodes:', selectedCodes.size);
    resultsTitle.textContent = 'Топ-12 кодов ГРНТИ';
    resultsGrid.innerHTML = '';
    resultsSection.style.display = 'block';
    breadcrumbs.style.display = 'none';

    predictions.forEach(pred => {
        const card = document.createElement('div');
        card.className = 'result-card';
        card.dataset.code = pred.code;
        const isSelected = selectedCodes.has(pred.code);
        if (isSelected) {
            card.classList.add('selected');
            console.log('[GRNTI] Card marked as selected:', pred.code);
        }
        card.innerHTML = `
            <div class="result-code">${pred.code}</div>
            <div class="result-label">${pred.label}</div>
            <div class="result-path">${pred.full_path_label}</div>
            <div class="result-score">Score: ${pred.score}</div>
        `;
        card.addEventListener('click', () => toggleSelection(pred.code, pred.full_path_label, card));
        resultsGrid.appendChild(card);
    });
}

function renderStepResults(predictions, depth) {
    console.log('[GRNTI] renderStepResults(depth=' + depth + ') - predictions:', predictions.length, 'selectedCodes:', selectedCodes.size);
    resultsTitle.textContent = `Выберите уровень ${depth}`;
    resultsGrid.innerHTML = '';
    resultsSection.style.display = 'block';

    predictions.forEach(pred => {
        const card = document.createElement('div');
        card.className = 'result-card';
        card.dataset.code = pred.code;
        const isSelected = selectedCodes.has(pred.code);
        if (isSelected) {
            card.classList.add('selected');
            console.log('[GRNTI] Card marked as selected (step):', pred.code);
        }
        card.innerHTML = `
            <div class="result-code">${pred.code}</div>
            <div class="result-label">${pred.label}</div>
            <div class="result-score">Score: ${pred.score}</div>
        `;

        card.addEventListener('click', async () => {
            const text = textInput.value.trim();
            const resp = await fetch('/api/v1/classify/by-parent', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text, parent_code: pred.code, top_k: 1}),
            });
            const data = resp.ok ? await resp.json() : {predictions: []};
            if (data.predictions.length > 0 && depth < 10) {
                // Drill down — save current selection to history
                stepHistory.push({depth, code: pred.code, label: pred.label, parentCode: currentStep.parentCode});
                runStepByStep(text, depth + 1, pred.code, pred.code, pred.label);
            } else {
                // Leaf — toggle selection
                toggleSelection(pred.code, pred.full_label, card);
            }
        });

        resultsGrid.appendChild(card);
    });
}

function toggleSelection(code, _label, cardElement) {
    console.log('[GRNTI] toggleSelection:', code, 'has?', selectedCodes.has(code));
    if (selectedCodes.has(code)) {
        selectedCodes.delete(code);
        cardElement.classList.remove('selected');
        console.log('[GRNTI] Removed code, size now:', selectedCodes.size);
    } else {
        selectedCodes.add(code);
        cardElement.classList.add('selected');
        console.log('[GRNTI] Added code, size now:', selectedCodes.size);
    }
    renderSelectedCodes();
    saveSelectedCodes();
}

function renderSelectedCodes() {
    console.log('[GRNTI] renderSelectedCodes() called, selectedCodes.size =', selectedCodes.size);
    if (selectedCodes.size === 0) {
        console.log('[GRNTI] No selected codes, hiding section');
        selectedSection.style.display = 'none';
        return;
    }
    console.log('[GRNTI] Showing selected section with', selectedCodes.size, 'codes:', Array.from(selectedCodes));
    selectedSection.style.display = 'block';
    selectedSection.classList.add('selected-section-sticky');

    // Clear and rebuild the section
    selectedCodesDiv.innerHTML = Array.from(selectedCodes)
        .map(code => `<span class="selected-code-badge" data-code="${code}">${code} ✕</span>`)
        .join('');

    selectedCodesDiv.querySelectorAll('.selected-code-badge').forEach(badge => {
        badge.addEventListener('click', () => {
            const code = badge.dataset.code;
            selectedCodes.delete(code);
            document.querySelectorAll(`.result-card[data-code="${code}"]`).forEach(card => {
                card.classList.remove('selected');
            });
            renderSelectedCodes();
            saveSelectedCodes();
        });
    });
}

function updateBreadcrumbs() {
    if (currentMode !== 'step') {
        breadcrumbs.style.display = 'none';
        return;
    }

    breadcrumbs.style.display = 'block';
    breadcrumbs.innerHTML = '';

    // Build breadcrumb chain
    const chain = [];
    for (const step of stepHistory) {
        chain.push({code: step.code, label: step.label});
    }
    if (currentStep.code) {
        chain.push({code: currentStep.code, label: currentStep.label});
    }

    if (chain.length === 0) {
        breadcrumbs.innerHTML = '<span class="breadcrumb-empty">Уровень 1</span>';
    } else {
        chain.forEach((item, idx) => {
            const link = document.createElement('a');
            link.className = 'breadcrumb-link';
            link.textContent = `${item.code}${item.label ? ` (${item.label})` : ''}`;
            link.href = '#';
            link.addEventListener('click', (e) => {
                e.preventDefault();
                // Find which step to restore
                const targetSteps = stepHistory.slice(0, idx);
                stepHistory = targetSteps;
                if (targetSteps.length === 0) {
                    runStepByStep(textInput.value.trim(), 1, null);
                } else {
                    const prev = targetSteps[targetSteps.length - 1];
                    runStepByStep(textInput.value.trim(), prev.depth + 1, prev.code, prev.code, prev.label);
                }
            });
            breadcrumbs.appendChild(link);

            if (idx < chain.length - 1) {
                const sep = document.createElement('span');
                sep.className = 'breadcrumb-sep';
                sep.textContent = ' > ';
                breadcrumbs.appendChild(sep);
            }
        });
    }
}

function exportSelectedCodes() {
    const data = {
        text: lastClassifiedText,
        codes: Array.from(selectedCodes),
        timestamp: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'grnti_codes.json';
    a.click();
    URL.revokeObjectURL(url);
}

function showLoader() {
    classifyBtn.disabled = true;
    loader.style.display = 'inline';
}

function hideLoader() {
    classifyBtn.disabled = false;
    loader.style.display = 'none';
}

function showError(message) {
    errorMsg.textContent = message;
    errorMsg.style.display = 'block';
}

function hideError() {
    errorMsg.style.display = 'none';
}

// Clears only results/nav state, keeps selections
function resetResults() {
    resultsSection.style.display = 'none';
    breadcrumbs.style.display = 'none';
    currentStep = null;
    stepHistory = [];
}
