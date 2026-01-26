/**
 * TERE4AI Frontend Application
 *
 * Handles:
 * - Form submission and validation
 * - Example loading
 * - Progress tracking with polling
 * - Results display
 * - Export functionality
 */

// API base URL
const API_BASE = '';

// Configuration
const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 600000; // 10 minute timeout (high-risk cases take ~5 min)
const MAX_POLL_RETRIES = 3;

// State
let currentJobId = null;
let pollInterval = null;
let pollStartTime = null;
let pollRetryCount = 0;

// DOM Elements
const elements = {
    // Sections
    inputSection: document.getElementById('input-section'),
    progressSection: document.getElementById('progress-section'),
    errorSection: document.getElementById('error-section'),
    resultsSection: document.getElementById('results-section'),

    // Input
    description: document.getElementById('system-description'),
    context: document.getElementById('additional-context'),
    exampleSelect: document.getElementById('example-select'),
    analyzeBtn: document.getElementById('analyze-btn'),
    clearBtn: document.getElementById('clear-btn'),

    // Progress
    progressFill: document.getElementById('progress-fill'),
    progressPercent: document.getElementById('progress-percent'),
    progressPhase: document.getElementById('progress-phase'),
    progressMessage: document.getElementById('progress-message'),

    // Error
    errorMessage: document.getElementById('error-message'),
    retryBtn: document.getElementById('retry-btn'),

    // Results
    riskBanner: document.getElementById('risk-banner'),
    riskLevel: document.getElementById('risk-level'),
    riskBasis: document.getElementById('risk-basis'),
    systemSummary: document.getElementById('system-summary'),
    prohibitedWarning: document.getElementById('prohibited-warning'),
    prohibitionDetails: document.getElementById('prohibition-details'),
    requirementsCard: document.getElementById('requirements-card'),
    requirementsStats: document.getElementById('requirements-stats'),
    requirementsList: document.getElementById('requirements-list'),
    coverageGrid: document.getElementById('coverage-grid'),
    validationResults: document.getElementById('validation-results'),
    metricsGrid: document.getElementById('metrics-grid'),

    // Actions
    exportJsonBtn: document.getElementById('export-json-btn'),
    exportMdBtn: document.getElementById('export-md-btn'),
    newAnalysisBtn: document.getElementById('new-analysis-btn'),
};

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    loadExamples();
    setupEventListeners();
});

function setupEventListeners() {
    elements.analyzeBtn.addEventListener('click', startAnalysis);
    elements.clearBtn.addEventListener('click', clearForm);
    elements.exampleSelect.addEventListener('change', loadSelectedExample);
    elements.retryBtn.addEventListener('click', showInput);
    elements.newAnalysisBtn.addEventListener('click', showInput);
    elements.exportJsonBtn.addEventListener('click', () => exportReport('json'));
    elements.exportMdBtn.addEventListener('click', () => exportReport('markdown'));
}

// ============================================================================
// Examples
// ============================================================================

async function loadExamples() {
    try {
        const response = await fetch(`${API_BASE}/api/examples`);
        if (!response.ok) throw new Error('Failed to load examples');

        const data = await response.json();
        populateExamples(data.examples);
    } catch (error) {
        console.error('Error loading examples:', error);
    }
}

function populateExamples(examples) {
    elements.exampleSelect.innerHTML = '<option value="">-- Select an example --</option>';

    examples.forEach(example => {
        const option = document.createElement('option');
        option.value = example.id;
        option.textContent = `${example.name} (${example.category})`;
        option.dataset.description = example.description;
        option.dataset.expected = example.expected_risk_level;
        elements.exampleSelect.appendChild(option);
    });
}

function loadSelectedExample() {
    const selected = elements.exampleSelect.selectedOptions[0];
    if (selected && selected.dataset.description) {
        elements.description.value = selected.dataset.description;
        elements.context.value = '';
    }
}

function clearForm() {
    elements.description.value = '';
    elements.context.value = '';
    elements.exampleSelect.value = '';
}

// ============================================================================
// Analysis
// ============================================================================

async function startAnalysis() {
    const description = elements.description.value.trim();

    // Validate input with inline error
    if (description.length < 10) {
        showInputError('Please enter a more detailed system description (at least 10 characters).');
        return;
    }

    clearInputError();
    const context = elements.context.value.trim() || null;

    try {
        elements.analyzeBtn.disabled = true;

        // Submit analysis request
        const response = await fetch(`${API_BASE}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description, context }),
        });

        if (!response.ok) {
            let errorDetail = 'Failed to start analysis';
            try {
                const error = await response.json();
                errorDetail = error.detail || errorDetail;
            } catch (e) {
                errorDetail = `Server error: ${response.status} ${response.statusText}`;
            }
            throw new Error(errorDetail);
        }

        const data = await response.json();
        currentJobId = data.job_id;

        // Show progress and start polling
        showProgress();
        startPolling();

    } catch (error) {
        showError(error.message);
    } finally {
        elements.analyzeBtn.disabled = false;
    }
}

/**
 * Show inline validation error on input form
 */
function showInputError(message) {
    let errorEl = document.getElementById('input-error');
    if (!errorEl) {
        errorEl = document.createElement('div');
        errorEl.id = 'input-error';
        errorEl.className = 'input-error';
        errorEl.style.cssText = 'color: #e53e3e; font-size: 0.875rem; margin-top: 0.5rem; padding: 0.5rem; background: #fff5f5; border-radius: 4px; border: 1px solid #feb2b2;';
        elements.description.parentNode.appendChild(errorEl);
    }
    errorEl.textContent = message;
    elements.description.style.borderColor = '#e53e3e';
}

/**
 * Clear inline validation error
 */
function clearInputError() {
    const errorEl = document.getElementById('input-error');
    if (errorEl) {
        errorEl.remove();
    }
    elements.description.style.borderColor = '';
}

// ============================================================================
// Progress Polling
// ============================================================================

function startPolling() {
    pollStartTime = Date.now();
    pollRetryCount = 0;
    pollInterval = setInterval(pollStatus, POLL_INTERVAL_MS);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    pollStartTime = null;
    pollRetryCount = 0;
}

async function pollStatus() {
    if (!currentJobId) return;

    // Check for timeout
    if (pollStartTime && (Date.now() - pollStartTime) > POLL_TIMEOUT_MS) {
        stopPolling();
        showError('Analysis timed out after 10 minutes. High-risk systems typically take 4-5 minutes. Please check your server logs or try again.');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/status/${currentJobId}`);
        if (!response.ok) throw new Error('Failed to get status');

        const status = await response.json();
        updateProgress(status);

        // Reset retry count on success
        pollRetryCount = 0;

        if (status.status === 'completed') {
            stopPolling();
            await loadResults();
        } else if (status.status === 'failed') {
            stopPolling();
            showError(status.error || 'Analysis failed');
        }

    } catch (error) {
        console.error('Polling error:', error);
        pollRetryCount++;

        if (pollRetryCount >= MAX_POLL_RETRIES) {
            stopPolling();
            showError('Lost connection to server. Please check your network and try again.');
        }
        // Otherwise, let the interval continue and retry
    }
}

function updateProgress(status) {
    // Update progress bar
    elements.progressFill.style.width = `${status.progress}%`;
    elements.progressPercent.textContent = `${Math.round(status.progress)}%`;

    // Update ARIA attributes for accessibility
    const progressBar = document.getElementById('progress-bar-container');
    if (progressBar) {
        progressBar.setAttribute('aria-valuenow', Math.round(status.progress));
    }

    // Update phase display
    const phaseNames = {
        queued: 'Queued',
        elicitation: 'Elicitation',
        analysis: 'Analysis',
        specification: 'Specification',
        validation: 'Validation',
        finalizing: 'Finalizing',
        complete: 'Complete',
    };
    elements.progressPhase.textContent = phaseNames[status.phase] || status.phase;
    elements.progressMessage.textContent = status.message;

    // Update phase indicators
    const phases = ['elicitation', 'analysis', 'specification', 'validation'];
    const currentPhaseIndex = phases.indexOf(status.phase);

    document.querySelectorAll('.phase').forEach((el, index) => {
        el.classList.remove('active', 'complete');
        if (index < currentPhaseIndex) {
            el.classList.add('complete');
        } else if (index === currentPhaseIndex) {
            el.classList.add('active');
        }
    });

    // If complete or finalizing, mark all as complete
    if (status.phase === 'complete' || status.phase === 'finalizing') {
        document.querySelectorAll('.phase').forEach(el => {
            el.classList.remove('active');
            el.classList.add('complete');
        });
    }
}

// ============================================================================
// Results Display
// ============================================================================

async function loadResults() {
    try {
        const response = await fetch(`${API_BASE}/api/report/${currentJobId}`);
        if (!response.ok) throw new Error('Failed to load results');

        const report = await response.json();
        displayResults(report);
        showResults();

    } catch (error) {
        showError(error.message);
    }
}

function displayResults(report) {
    // Risk Classification
    displayRiskClassification(report.risk_classification);

    // System Summary
    displaySystemSummary(report.system_description);

    // Handle prohibited systems
    if (report.risk_classification?.level === 'unacceptable') {
        displayProhibitedWarning(report.risk_classification);
        elements.requirementsCard.classList.add('hidden');
        elements.coverageGrid.parentElement.classList.add('hidden');
        elements.validationResults.parentElement.classList.add('hidden');
    } else {
        elements.prohibitedWarning.classList.add('hidden');
        elements.requirementsCard.classList.remove('hidden');
        elements.coverageGrid.parentElement.classList.remove('hidden');
        elements.validationResults.parentElement.classList.remove('hidden');

        // Requirements
        displayRequirements(report.requirements);

        // Coverage
        displayCoverage(report.coverage_matrix, report.validation);

        // Validation
        displayValidation(report.validation);
    }

    // Metrics
    displayMetrics(report.metrics);
}

function displayRiskClassification(risk) {
    if (!risk) return;

    const level = risk.level;
    elements.riskBanner.className = `risk-banner ${level}`;
    elements.riskLevel.textContent = level.toUpperCase();

    // Legal basis
    let basisText = '';
    if (risk.legal_basis?.primary) {
        basisText = risk.legal_basis.primary.reference_text || '';
    }
    if (risk.annex_iii_category) {
        basisText += ` | Annex III: ${risk.annex_iii_category}`;
    }
    elements.riskBasis.textContent = basisText;
}

function displaySystemSummary(sys) {
    if (!sys) return;

    const items = [
        { label: 'Domain', value: formatValue(sys.domain) },
        { label: 'Purpose', value: sys.purpose || 'N/A' },
        { label: 'Autonomy Level', value: formatValue(sys.autonomy_level) },
        { label: 'Deployment', value: formatValue(sys.deployment_context) },
        { label: 'Safety Critical', value: sys.safety_critical ? 'Yes' : 'No' },
        { label: 'Affects Rights', value: sys.affects_fundamental_rights ? 'Yes' : 'No' },
    ];

    elements.systemSummary.innerHTML = items.map(item => `
        <div class="summary-item">
            <div class="label">${item.label}</div>
            <div class="value">${item.value}</div>
        </div>
    `).join('');
}

function displayProhibitedWarning(risk) {
    elements.prohibitedWarning.classList.remove('hidden');

    let details = '';
    if (risk.prohibition_details) {
        details += `<p><strong>Reason:</strong> ${escapeHtml(risk.prohibition_details)}</p>`;
    }
    if (risk.legal_basis?.primary) {
        const cite = risk.legal_basis.primary;
        details += `<p><strong>Legal Reference:</strong> ${escapeHtml(cite.reference_text)}</p>`;
        if (cite.quoted_text) {
            details += `<blockquote>"${escapeHtml(cite.quoted_text)}"</blockquote>`;
        }
    }
    elements.prohibitionDetails.innerHTML = details;
}

function displayRequirements(requirements) {
    if (!requirements || requirements.length === 0) {
        elements.requirementsList.innerHTML = '<p class="no-requirements">No requirements generated.</p>';
        elements.requirementsStats.innerHTML = '';
        return;
    }

    // Stats
    const stats = {
        critical: requirements.filter(r => r.priority === 'critical').length,
        high: requirements.filter(r => r.priority === 'high').length,
        medium: requirements.filter(r => r.priority === 'medium').length,
        low: requirements.filter(r => r.priority === 'low').length,
    };

    elements.requirementsStats.innerHTML = `
        <div class="stat-item">
            <span class="stat-badge critical">${stats.critical}</span>
            <span>Critical</span>
        </div>
        <div class="stat-item">
            <span class="stat-badge high">${stats.high}</span>
            <span>High</span>
        </div>
        <div class="stat-item">
            <span class="stat-badge medium">${stats.medium}</span>
            <span>Medium</span>
        </div>
    `;

    // Requirement cards (with XSS protection via escapeHtml)
    elements.requirementsList.innerHTML = requirements.map(req => `
        <div class="requirement-card" data-id="${escapeHtml(req.id)}">
            <div class="requirement-header" onclick="toggleRequirement('${escapeHtml(req.id)}')">
                <div class="requirement-title">
                    <span class="requirement-id">${escapeHtml(req.id)}</span>
                    <span class="requirement-name">${escapeHtml(req.title)}</span>
                </div>
                <div class="requirement-badges">
                    <span class="badge category">${formatValue(req.category)}</span>
                    <span class="badge priority ${escapeHtml(req.priority)}">${escapeHtml(req.priority)}</span>
                </div>
            </div>
            <div class="requirement-body">
                <div class="requirement-statement">${escapeHtml(req.statement)}</div>

                ${req.eu_ai_act_citations?.length ? `
                <div class="requirement-section">
                    <h4>EU AI Act Citations</h4>
                    <ul class="citation-list">
                        ${req.eu_ai_act_citations.map(cite => `
                            <li class="citation-item">
                                <span class="citation-ref">${escapeHtml(cite.reference_text || formatCitation(cite))}</span>
                                ${cite.quoted_text ? `<span class="citation-text">"${escapeHtml(truncate(cite.quoted_text, 200))}"</span>` : ''}
                            </li>
                        `).join('')}
                    </ul>
                </div>
                ` : ''}

                ${req.hleg_citations?.length ? `
                <div class="requirement-section">
                    <h4>HLEG Alignment</h4>
                    <ul class="citation-list">
                        ${req.hleg_citations.map(cite => `
                            <li class="citation-item hleg-item">
                                <span>${formatValue(cite.requirement_id)}${cite.subtopic_id ? ` > ${formatValue(cite.subtopic_id)}` : ''}</span>
                                <span class="hleg-score">${((cite.relevance_score || 0) * 100).toFixed(0)}%</span>
                            </li>
                        `).join('')}
                    </ul>
                </div>
                ` : ''}

                ${req.verification_criteria?.length ? `
                <div class="requirement-section">
                    <h4>Verification Criteria</h4>
                    <ul class="verification-list">
                        ${req.verification_criteria.map(v => `<li>${escapeHtml(v)}</li>`).join('')}
                    </ul>
                </div>
                ` : ''}

                ${req.rationale ? `
                <div class="requirement-section">
                    <h4>Rationale</h4>
                    <p>${escapeHtml(req.rationale)}</p>
                </div>
                ` : ''}
            </div>
        </div>
    `).join('');
}

function toggleRequirement(id) {
    const card = document.querySelector(`.requirement-card[data-id="${id}"]`);
    if (card) {
        card.classList.toggle('expanded');
    }
}

function displayCoverage(matrix, validation) {
    let html = '';

    // Article coverage
    if (validation) {
        html += `
            <div class="coverage-section">
                <h4>Article Coverage</h4>
                <div class="coverage-bar">
                    <span class="label">EU AI Act Articles</span>
                    <div class="bar">
                        <div class="bar-fill" style="width: ${validation.article_coverage * 100}%"></div>
                    </div>
                    <span class="percent">${(validation.article_coverage * 100).toFixed(0)}%</span>
                </div>
            </div>
        `;
    }

    // HLEG coverage
    if (validation) {
        html += `
            <div class="coverage-section">
                <h4>HLEG Principles Coverage</h4>
                <div class="coverage-bar">
                    <span class="label">Principles Addressed</span>
                    <div class="bar">
                        <div class="bar-fill" style="width: ${validation.hleg_coverage * 100}%"></div>
                    </div>
                    <span class="percent">${(validation.hleg_coverage * 100).toFixed(0)}%</span>
                </div>
            </div>
        `;
    }

    elements.coverageGrid.innerHTML = html;
}

function displayValidation(validation) {
    if (!validation) {
        elements.validationResults.innerHTML = '<p>No validation data available.</p>';
        return;
    }

    const items = [
        {
            label: 'Article Coverage',
            value: `${(validation.article_coverage * 100).toFixed(0)}%`,
            status: validation.article_coverage >= 0.8 ? 'success' : 'warning',
        },
        {
            label: 'HLEG Coverage',
            value: `${(validation.hleg_coverage * 100).toFixed(0)}%`,
            status: validation.hleg_coverage >= 0.7 ? 'success' : 'warning',
        },
        {
            label: 'Completeness',
            value: validation.is_complete ? 'Yes' : 'No',
            status: validation.is_complete ? 'success' : 'warning',
        },
        {
            label: 'Consistency',
            value: validation.is_consistent ? 'Yes' : 'No',
            status: validation.is_consistent ? 'success' : 'error',
        },
    ];

    elements.validationResults.innerHTML = items.map(item => `
        <div class="validation-item">
            <span class="validation-icon ${item.status}">${item.status === 'success' ? '✓' : item.status === 'warning' ? '!' : '✗'}</span>
            <span class="validation-label">${item.label}</span>
            <span class="validation-value">${item.value}</span>
        </div>
    `).join('');
}

function displayMetrics(metrics) {
    if (!metrics) return;

    const items = [
        { label: 'Total Requirements', value: metrics.total_requirements || 0 },
        { label: 'Total Citations', value: metrics.total_citations || 0 },
        { label: 'Articles Cited', value: metrics.unique_articles_cited || 0 },
        { label: 'HLEG Principles', value: metrics.unique_hleg_principles_addressed || 0 },
        { label: 'Critical Reqs', value: metrics.critical_requirements || 0 },
        { label: 'High Priority', value: metrics.high_requirements || 0 },
    ];

    elements.metricsGrid.innerHTML = items.map(item => `
        <div class="metric-item">
            <div class="metric-value">${item.value}</div>
            <div class="metric-label">${item.label}</div>
        </div>
    `).join('');
}

// ============================================================================
// Export
// ============================================================================

async function exportReport(format) {
    if (!currentJobId) return;

    // Disable export buttons during operation
    elements.exportJsonBtn.disabled = true;
    elements.exportMdBtn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/export/${currentJobId}/${format}`);
        if (!response.ok) throw new Error('Failed to export');

        const blob = await response.blob();
        // Improved regex for filename extraction
        const contentDisposition = response.headers.get('Content-Disposition') || '';
        const filenameMatch = contentDisposition.match(/filename="?([^";\n]+)"?/);
        const filename = (filenameMatch ? filenameMatch[1] : '').trim()
            || `tere4ai_report.${format === 'json' ? 'json' : 'md'}`;

        // Download
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

    } catch (error) {
        showExportError(`Export failed: ${error.message}`);
    } finally {
        elements.exportJsonBtn.disabled = false;
        elements.exportMdBtn.disabled = false;
    }
}

/**
 * Show export error inline
 */
function showExportError(message) {
    let errorEl = document.getElementById('export-error');
    if (!errorEl) {
        errorEl = document.createElement('div');
        errorEl.id = 'export-error';
        errorEl.style.cssText = 'color: #e53e3e; font-size: 0.875rem; margin-top: 0.5rem; padding: 0.5rem; background: #fff5f5; border-radius: 4px; text-align: center;';
        document.querySelector('.export-row').appendChild(errorEl);
    }
    errorEl.textContent = message;
    // Auto-clear after 5 seconds
    setTimeout(() => {
        if (errorEl && errorEl.parentNode) {
            errorEl.remove();
        }
    }, 5000);
}

// ============================================================================
// View Management
// ============================================================================

function showInput() {
    stopPolling();
    currentJobId = null;

    elements.inputSection.classList.remove('hidden');
    elements.progressSection.classList.add('hidden');
    elements.errorSection.classList.add('hidden');
    elements.resultsSection.classList.add('hidden');

    // Reset progress
    elements.progressFill.style.width = '0%';
    elements.progressPercent.textContent = '0%';
    document.querySelectorAll('.phase').forEach(el => {
        el.classList.remove('active', 'complete');
    });
}

function showProgress() {
    elements.inputSection.classList.add('hidden');
    elements.progressSection.classList.remove('hidden');
    elements.errorSection.classList.add('hidden');
    elements.resultsSection.classList.add('hidden');
}

function showError(message) {
    stopPolling();

    elements.inputSection.classList.add('hidden');
    elements.progressSection.classList.add('hidden');
    elements.errorSection.classList.remove('hidden');
    elements.resultsSection.classList.add('hidden');

    elements.errorMessage.textContent = message;
}

function showResults() {
    elements.inputSection.classList.add('hidden');
    elements.progressSection.classList.add('hidden');
    elements.errorSection.classList.add('hidden');
    elements.resultsSection.classList.remove('hidden');
}

// ============================================================================
// Utilities
// ============================================================================

/**
 * Escape HTML to prevent XSS attacks
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatValue(value) {
    if (!value) return 'N/A';
    return escapeHtml(value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
}

function formatCitation(cite) {
    if (cite.article) {
        let ref = `Article ${cite.article}`;
        if (cite.paragraph) ref += `(${cite.paragraph})`;
        if (cite.point) ref += `(${cite.point})`;
        return ref;
    }
    if (cite.recital) return `Recital ${cite.recital}`;
    if (cite.annex) return `Annex ${cite.annex}`;
    return 'Citation';
}

function truncate(text, maxLength) {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Make toggleRequirement available globally
window.toggleRequirement = toggleRequirement;
