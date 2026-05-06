// State
let selectedCodes = new Set();
let currentMode = 'full';
let currentStep = null; // {level: 'L1'|'L2'|'L3', parentCode: string}

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

// Event listeners
classifyBtn.addEventListener('click', handleClassify);
exportBtn.addEventListener('click', exportSelectedCodes);
modeInputs.forEach(input => {
    input.addEventListener('change', (e) => {
        currentMode = e.target.value;
        reset();
    });
});

function handleClassify() {
    const text = textInput.value.trim();
    if (!text) {
        showError('Введите текст для классификации');
        return;
    }
    
    hideError();
    
    if (currentMode === 'full') {
        runFullCascade(text);
    } else {
        runStepByStep(text);
    }
}

async function runFullCascade(text) {
    showLoader();
    
    try {
        const response = await fetch('/api/v1/classify/full', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text, top_k: 10}),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        renderFullResults(data.predictions);
    } catch (error) {
        showError(`Ошибка: ${error.message}`);
    } finally {
        hideLoader();
    }
}

async function runStepByStep(text, level = 'L1', parentCode = null) {
    showLoader();
    
    const endpoint = level === 'L1' ? '/api/v1/classify/l1' : 
                     level === 'L2' ? '/api/v1/classify/l2' : 
                     '/api/v1/classify/l3';
    
    const body = level === 'L1' ? 
        {text, top_k: 5} : 
        {text, parent_code: parentCode, top_k: 5};
    
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        currentStep = {level, parentCode};
        renderStepResults(data.predictions, level);
        updateBreadcrumbs();
    } catch (error) {
        showError(`Ошибка: ${error.message}`);
    } finally {
        hideLoader();
    }
}

function renderFullResults(predictions) {
    resultsTitle.textContent = 'Топ-10 кодов ГРНТИ';
    resultsGrid.innerHTML = '';
    resultsSection.style.display = 'block';
    breadcrumbs.style.display = 'none';
    
    predictions.forEach(pred => {
        const card = document.createElement('div');
        card.className = 'result-card';
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

function renderStepResults(predictions, level) {
    resultsTitle.textContent = `Выберите ${level}`;
    resultsGrid.innerHTML = '';
    resultsSection.style.display = 'block';
    
    predictions.forEach(pred => {
        const card = document.createElement('div');
        card.className = 'result-card';
        card.innerHTML = `
            <div class="result-code">${pred.code}</div>
            <div class="result-label">${pred.label}</div>
            <div class="result-score">Score: ${pred.score}</div>
        `;
        
        card.addEventListener('click', () => {
            if (level === 'L3') {
                toggleSelection(pred.code, pred.full_label, card);
            } else {
                // Navigate to next level
                const nextLevel = level === 'L1' ? 'L2' : 'L3';
                runStepByStep(textInput.value.trim(), nextLevel, pred.code);
            }
        });
        
        resultsGrid.appendChild(card);
    });
}

function toggleSelection(code, label, cardElement) {
    if (selectedCodes.has(code)) {
        selectedCodes.delete(code);
        cardElement.classList.remove('selected');
    } else {
        selectedCodes.add(code);
        cardElement.classList.add('selected');
    }
    renderSelectedCodes();
}

function renderSelectedCodes() {
    if (selectedCodes.size === 0) {
        selectedSection.style.display = 'none';
        return;
    }
    
    selectedSection.style.display = 'block';
    selectedCodesDiv.innerHTML = Array.from(selectedCodes)
        .map(code => `<span class="selected-code-badge">${code}</span>`)
        .join('');
}

function updateBreadcrumbs() {
    if (currentMode !== 'step') {
        breadcrumbs.style.display = 'none';
        return;
    }
    
    breadcrumbs.style.display = 'block';
    breadcrumbs.textContent = `Текущий уровень: ${currentStep.level}`;
}

function exportSelectedCodes() {
    const data = {
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

function reset() {
    resultsSection.style.display = 'none';
    breadcrumbs.style.display = 'none';
    selectedCodes.clear();
    renderSelectedCodes();
    currentStep = null;
}
