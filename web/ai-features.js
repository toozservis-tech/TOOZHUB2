/**
 * AI Feature Suggestions UI
 * Komponenta pro zobrazení a správu navrhovaných funkcí
 */

// Globální proměnné
let aiFeaturesSuggestions = [];
let aiFeaturesStats = null;

/**
 * Načíst návrhy funkcí z API
 */
async function loadAIFeaturesSuggestions(status = null, category = null) {
    try {
        let url = '/api/v1/ai-features/suggestions?limit=50';
        if (status) url += `&status=${status}`;
        if (category) url += `&category=${category}`;
        
        const suggestions = await apiCall(url, 'GET');
        aiFeaturesSuggestions = suggestions || [];
        renderAIFeaturesSuggestions();
    } catch (error) {
        console.error('[AI-FEATURES] Chyba při načítání návrhů:', error);
        showAlert('Chyba při načítání návrhů funkcí', 'error');
    }
}

/**
 * Načíst statistiky použití
 */
async function loadAIFeaturesStats() {
    try {
        const stats = await apiCall('/api/v1/ai-features/analytics/stats?days=30', 'GET');
        aiFeaturesStats = stats;
        renderAIFeaturesStats();
    } catch (error) {
        console.error('[AI-FEATURES] Chyba při načítání statistik:', error);
    }
}

/**
 * Spustit analýzu a navrhnout nové funkce
 */
async function analyzeAndSuggestFeatures() {
    try {
        showAlert('Spouštím analýzu použití aplikace...', 'info');
        
        const result = await apiCall('/api/v1/ai-features/suggestions/analyze?days=30', 'POST');
        
        if (result && result.suggestions_created > 0) {
            showAlert(`Analýza dokončena! Vytvořeno ${result.suggestions_created} nových návrhů.`, 'success');
            await loadAIFeaturesSuggestions();
        } else {
            showAlert('Analýza dokončena. Nebyly nalezeny nové návrhy.', 'info');
        }
    } catch (error) {
        console.error('[AI-FEATURES] Chyba při analýze:', error);
        showAlert('Chyba při spuštění analýzy', 'error');
    }
}

/**
 * Vykreslit návrhy funkcí
 */
function renderAIFeaturesSuggestions() {
    const container = document.getElementById('aiFeaturesContainer');
    if (!container) return;
    
    if (aiFeaturesSuggestions.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #64748b;">
                <p style="font-size: 18px; margin-bottom: 16px;">🤖 Zatím nejsou žádné návrhy funkcí</p>
                <p style="margin-bottom: 24px;">Návrhy funkcí se zobrazí po spuštění analýzy administrátorem.</p>
            </div>
        `;
        return;
    }
    
    let html = '<div class="ai-features-grid">';
    
    aiFeaturesSuggestions.forEach(suggestion => {
        const priorityColor = getPriorityColor(suggestion.priority);
        const statusBadge = getStatusBadge(suggestion.status);
        const complexityBadge = suggestion.implementation_complexity 
            ? `<span class="badge badge-${suggestion.implementation_complexity}">${suggestion.implementation_complexity}</span>`
            : '';
        
        html += `
            <div class="ai-feature-card" data-id="${suggestion.id}">
                <div class="ai-feature-header">
                    <h3>${escapeHtml(suggestion.title)}</h3>
                    <div class="ai-feature-badges">
                        ${statusBadge}
                        ${complexityBadge}
                    </div>
                </div>
                <div class="ai-feature-body">
                    <p class="ai-feature-description">${escapeHtml(suggestion.description)}</p>
                    
                    ${suggestion.reasoning ? `
                        <div class="ai-feature-reasoning">
                            <strong>💡 Proč:</strong> ${escapeHtml(suggestion.reasoning)}
                        </div>
                    ` : ''}
                    
                    <div class="ai-feature-meta">
                        <div class="ai-feature-meta-item">
                            <span class="label">Priorita:</span>
                            <div class="priority-bar">
                                <div class="priority-fill" style="width: ${suggestion.priority}%; background: ${priorityColor};"></div>
                            </div>
                            <span class="value">${suggestion.priority}/100</span>
                        </div>
                        
                        <div class="ai-feature-meta-item">
                            <span class="label">Jistota AI:</span>
                            <span class="value">${Math.round(suggestion.confidence_score * 100)}%</span>
                        </div>
                        
                        ${suggestion.estimated_effort_hours ? `
                            <div class="ai-feature-meta-item">
                                <span class="label">Odhadovaný čas:</span>
                                <span class="value">${suggestion.estimated_effort_hours}h</span>
                            </div>
                        ` : ''}
                        
                        ${suggestion.category ? `
                            <div class="ai-feature-meta-item">
                                <span class="label">Kategorie:</span>
                                <span class="value">${escapeHtml(suggestion.category)}</span>
                            </div>
                        ` : ''}
                    </div>
                </div>
                
                <div class="ai-feature-actions">
                    <button class="btn btn-sm" onclick="viewFeatureDetail(${suggestion.id})" style="background: #6366f1;">
                        📋 Detail
                    </button>
                    ${suggestion.status === 'suggested' ? `
                        <button class="btn btn-sm btn-approve" onclick="approveFeature(${suggestion.id})" style="background: #10b981; display: none;">
                            ✅ Schválit
                        </button>
                        <button class="btn btn-sm btn-reject" onclick="rejectFeature(${suggestion.id})" style="background: #ef4444; display: none;">
                            ❌ Odmítnout
                        </button>
                    ` : ''}
                    <button class="btn btn-sm" onclick="voteOnFeature(${suggestion.id}, 1)" style="background: #3b82f6;">
                        👍 Hlasovat
                    </button>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

/**
 * Vykreslit statistiky
 */
function renderAIFeaturesStats() {
    const container = document.getElementById('aiFeaturesStats');
    if (!container || !aiFeaturesStats) return;
    
    container.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">${aiFeaturesStats.total_requests || 0}</div>
                <div class="stat-label">Celkem požadavků</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${aiFeaturesStats.active_users || 0}</div>
                <div class="stat-label">Aktivní uživatelé</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${Math.round(aiFeaturesStats.avg_response_time_ms || 0)}ms</div>
                <div class="stat-label">Průměrná doba odezvy</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${aiFeaturesStats.error_rate_percent?.toFixed(1) || 0}%</div>
                <div class="stat-label">Chybovost</div>
            </div>
        </div>
        
        ${aiFeaturesStats.top_endpoints && aiFeaturesStats.top_endpoints.length > 0 ? `
            <div class="top-endpoints">
                <h4>Nejčastěji používané endpointy:</h4>
                <ul>
                    ${aiFeaturesStats.top_endpoints.map(e => `
                        <li>${escapeHtml(e.endpoint)} - ${e.count}x</li>
                    `).join('')}
                </ul>
            </div>
        ` : ''}
    `;
}

/**
 * Zobrazit detail návrhu
 */
async function viewFeatureDetail(suggestionId) {
    try {
        const suggestion = await apiCall(`/api/v1/ai-features/suggestions/${suggestionId}`, 'GET');
        
        // Získat plán integrace
        const integrationPlan = await apiCall(`/api/v1/ai-features/suggestions/${suggestionId}/integration-plan`, 'GET');
        const dependencies = await apiCall(`/api/v1/ai-features/suggestions/${suggestionId}/dependencies`, 'GET');
        
        // Zobrazit modal s detailem
        showFeatureDetailModal(suggestion, integrationPlan, dependencies);
    } catch (error) {
        console.error('[AI-FEATURES] Chyba při načítání detailu:', error);
        showAlert('Chyba při načítání detailu návrhu', 'error');
    }
}

/**
 * Zobrazit modal s detailem návrhu
 */
function showFeatureDetailModal(suggestion, integrationPlan, dependencies) {
    // TODO: Implementovat modal okno s detailem
    alert(`Detail návrhu: ${suggestion.title}\n\n${suggestion.description}`);
}

/**
 * Schválit návrh
 */
async function approveFeature(suggestionId) {
    if (!confirm('Opravdu chcete schválit tento návrh?')) return;
    
    try {
        await apiCall(`/api/v1/ai-features/suggestions/${suggestionId}/approve`, 'POST');
        showAlert('Návrh byl schválen', 'success');
        await loadAIFeaturesSuggestions();
    } catch (error) {
        console.error('[AI-FEATURES] Chyba při schvalování:', error);
        showAlert('Chyba při schvalování návrhu', 'error');
    }
}

/**
 * Odmítnout návrh
 */
async function rejectFeature(suggestionId) {
    if (!confirm('Opravdu chcete odmítnout tento návrh?')) return;
    
    try {
        await apiCall(`/api/v1/ai-features/suggestions/${suggestionId}/reject`, 'POST');
        showAlert('Návrh byl odmítnut', 'info');
        await loadAIFeaturesSuggestions();
    } catch (error) {
        console.error('[AI-FEATURES] Chyba při odmítání:', error);
        showAlert('Chyba při odmítání návrhu', 'error');
    }
}

/**
 * Hlasovat o návrhu
 */
async function voteOnFeature(suggestionId, vote) {
    try {
        await apiCall(`/api/v1/ai-features/suggestions/${suggestionId}/vote`, 'POST', {
            vote: vote,
            comment: null
        });
        showAlert('Váš hlas byl zaznamenán', 'success');
    } catch (error) {
        console.error('[AI-FEATURES] Chyba při hlasování:', error);
        showAlert('Chyba při hlasování', 'error');
    }
}

/**
 * Pomocné funkce
 */
function getPriorityColor(priority) {
    if (priority >= 80) return '#ef4444'; // Červená - vysoká
    if (priority >= 60) return '#f59e0b'; // Oranžová - střední
    return '#10b981'; // Zelená - nízká
}

function getStatusBadge(status) {
    const badges = {
        'suggested': '<span class="badge badge-info">Navrženo</span>',
        'approved': '<span class="badge badge-success">Schváleno</span>',
        'rejected': '<span class="badge badge-danger">Odmítnuto</span>',
        'implemented': '<span class="badge badge-success">Implementováno</span>',
        'testing': '<span class="badge badge-warning">Testování</span>'
    };
    return badges[status] || `<span class="badge">${status}</span>`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Inicializace při načtení záložky
 */
async function initAIFeaturesTab() {
    // Načíst návrhy (všichni uživatelé)
    await loadAIFeaturesSuggestions();
    
    // Načíst statistiky pouze pokud je uživatel admin
    try {
        await loadAIFeaturesStats();
    } catch (error) {
        // Pokud není admin, statistiky se nenačtou (403) - to je v pořádku
        console.log('[AI-FEATURES] Statistiky nejsou dostupné (pouze pro adminy)');
        const statsContainer = document.getElementById('aiFeaturesStats');
        if (statsContainer) {
            statsContainer.innerHTML = '<p style="color: #64748b; font-style: italic;">Statistiky jsou dostupné pouze pro administrátory.</p>';
        }
    }
    
    // Upravit UI podle role uživatele
    await updateUIForUserRole();
}

/**
 * Zkontrolovat, zda je uživatel admin
 */
async function checkIfAdmin() {
    try {
        // Zkusit načíst statistiky - pokud to projde, je admin
        await apiCall('/api/v1/ai-features/analytics/stats?days=1', 'GET');
        return true;
    } catch (error) {
        return false;
    }
}

/**
 * Zobrazit/skrýt admin funkce podle role
 */
async function updateUIForUserRole() {
    const isAdmin = await checkIfAdmin();
    
    // Skrýt tlačítko "Analyzovat" pro ne-adminy
    const analyzeButton = document.querySelector('button[onclick="analyzeAndSuggestFeatures()"]');
    if (analyzeButton) {
        analyzeButton.style.display = isAdmin ? 'inline-block' : 'none';
    }
    
    // Skrýt tlačítka "Schválit" a "Odmítnout" pro ne-adminy
    document.querySelectorAll('.btn-approve, .btn-reject').forEach(btn => {
        btn.style.display = isAdmin ? 'inline-block' : 'none';
    });
}

