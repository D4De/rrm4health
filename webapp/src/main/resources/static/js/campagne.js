/**
 * Frontend campagne: gestione form, modali e interazioni HTMX.
 * Flow principale:
 * 1) selezione tipo campagna -> apre modale configurazione e imposta lo script.
 * 2) submit campagna/paziente -> HTMX, con refresh frammenti senza reload pagina.
 * 3) azioni campagna (termina/elimina) -> refresh tabella home.
 * 4) ricerca paziente -> suggerimenti sotto input con selezione rapida.
 */

// Inizializzazione base
window.addEventListener('DOMContentLoaded', () => {
    wireTipoConfig();
    wireTipoConfigButtons();
    wireQuickApplicationButtons();
    wireFrequenzaSlider();
    wireDurataControls();
    wirePersonaSearch();
    renderParamsForSelectedTipo();
    wireStartButtonByNodesStatus();
});

/**
 * Collega la selezione dei tipi campagna ai radio button.
 */
let currentTipoId = null; // remember which tipo we last handled
const startupMonitors = new Map();
const notifiedStartupFailures = new Set();
const editableParamsCache = new Map();
const editableParamDraftsByApp = new Map();
let hasOnlineNodes = false;
let configMode = 'campaign';
let quickApplicationConfig = null;

function setStartCampaignButtonEnabled(enabled) {
    const button = document.getElementById('btnOpenCreateCampagna');
    if (!button) return;

    button.disabled = !enabled;
    button.classList.toggle('btn-disabled', !enabled);
    button.title = enabled
        ? 'Avvia una nuova campagna'
        : 'Serve almeno un nodo online';

    document.querySelectorAll('[data-action="quick-play"]').forEach((quickButton) => {
        quickButton.disabled = !enabled;
        quickButton.classList.toggle('btn-disabled', !enabled);
        quickButton.title = enabled
            ? 'Avvia applicazione rapida'
            : 'Serve almeno un nodo online';
    });
}

function wireStartButtonByNodesStatus() {
    setStartCampaignButtonEnabled(false);

    window.addEventListener('nodes-status-updated', (event) => {
        const detail = event && event.detail ? event.detail : {};
        const onlineCount = Number(detail.onlineCount || 0);
        hasOnlineNodes = Number.isFinite(onlineCount) && onlineCount >= 1;
        setStartCampaignButtonEnabled(hasOnlineNodes);
    });
}

function wireTipoConfig() {
    const radios = document.querySelectorAll('.tipo-radio');
    radios.forEach(radio => {
        radio.addEventListener('change', () => applyTipoSelection(radio));
        if (radio.checked) applyTipoSelection(radio);
    });
}

/**
 * Applica la selezione del tipo campagna:
 * imposta lo script e apre il modale di configurazione.
 */
function applyTipoSelection(radio) {
    setConfigModalMode('campaign');
    const scriptSelect = document.getElementById('scriptFileName');
    const appId = radio ? (radio.getAttribute('data-script') || '').trim() : '';
    if (scriptSelect) {
        scriptSelect.value = appId || '';
    }
    currentTipoId = radio ? radio.id : null;
    renderUserEditableParams(appId);
    openConfigModal();
}

/**
 * Gestisce il click sul bottone "Configura" vicino a ogni tipo.
 */
function wireTipoConfigButtons() {
    if (document.body.dataset.tipoConfigBound) return;
    document.body.dataset.tipoConfigBound = 'true';
    document.body.addEventListener('click', (event) => {
        const button = event.target.closest('[data-action="config-tipo"]');
        if (!button) return;
        const typeId = button.dataset.typeId;
        const radio = typeId ? document.getElementById(`tipo_${typeId}`) : null;
        if (radio) {
            // if the radio is already checked we only open the modal,
            // do not call applyTipoSelection since that may clear the
            // stored appID (see issue).
            if (!radio.checked) {
                radio.checked = true;
                applyTipoSelection(radio);
            } else {
                openConfigModal();
            }
        } else {
            openConfigModal();
        }
    });
}

function wireQuickApplicationButtons() {
    if (document.body.dataset.quickApplicationBound) return;
    document.body.dataset.quickApplicationBound = 'true';
    document.body.addEventListener('click', (event) => {
        const configButton = event.target.closest('[data-action="quick-config"]');
        if (configButton) {
            openQuickApplicationConfig(configButton);
            return;
        }

        const playButton = event.target.closest('[data-action="quick-play"]');
        if (playButton) {
            startQuickApplication(playButton);
        }
    });
}

/**
 * Ripristina i campi del modale di configurazione campagna.
 */
function resetCampagnaConfigUI() {
    setConfigModalMode('campaign');
    const scriptInput = document.getElementById('scriptFileName');
    if (scriptInput) scriptInput.value = '';
    const frequenza = document.getElementById('frequenzaCampagna');
    if (frequenza) frequenza.value = '10';
    syncFrequenzaLabel();
    const connettivita = document.getElementById('connettivitaCampagna');
    if (connettivita) connettivita.value = '';
    const dbConfig = document.getElementById('dbConfigId');
    if (dbConfig) dbConfig.value = '';
    const enableDurata = document.getElementById('enableDurataCampagna');
    if (enableDurata) enableDurata.checked = false;
    const durata = document.getElementById('durataCampagna');
    if (durata) durata.value = '';
    syncDurataControls();
    document.querySelectorAll('input[name="idSensori"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('[data-sensor-location-id]').forEach(input => {
        input.value = '';
        input.disabled = true;
        input.required = false;
    });
    editableParamDraftsByApp.clear();
    renderParamsForSelectedTipo();
}

/**
 * Apre il modale di configurazione solo se un tipo e' selezionato.
 */
function openConfigModal() {
    setConfigModalMode('campaign');
    const selected = document.querySelector('.tipo-radio:checked');
    if (!selected) {
        showCampagnaError('Seleziona un tipo di campagna prima di configurare.');
        return;
    }
    const appId = (selected.getAttribute('data-script') || '').trim();
    renderUserEditableParams(appId);
    const configModal = document.getElementById('configCampagnaModal');
    if (configModal) configModal.showModal();
}

function openQuickApplicationConfig(button) {
    const appId = (button.getAttribute('data-script') || '').trim();
    const codice = (button.getAttribute('data-codice') || '').trim();
    if (!appId) {
        showCampagnaError('Applicazione rapida non configurata correttamente.');
        return;
    }

    quickApplicationConfig = {
        appId,
        codice,
        configured: quickApplicationConfig
            && quickApplicationConfig.appId === appId
            && quickApplicationConfig.configured === true
    };
    setConfigModalMode('quick');
    renderUserEditableParams(appId);

    const configModal = document.getElementById('configCampagnaModal');
    if (configModal) configModal.showModal();
}

function setConfigModalMode(mode) {
    configMode = mode === 'quick' ? 'quick' : 'campaign';

    const title = document.getElementById('configCampagnaTitle');
    if (title) {
        title.textContent = configMode === 'quick'
            ? 'Configura applicazione rapida'
            : 'Configura Campagna';
    }

    [
        'frequenzaCampagnaField',
        'connettivitaCampagnaField',
        'dbConfigFields',
        'timerCampagnaField'
    ].forEach((id) => {
        const element = document.getElementById(id);
        if (element) element.classList.toggle('hidden', configMode === 'quick');
    });

    const sensorHelp = document.querySelector('#sensoriConfigContainer')
        ?.closest('.form-control')
        ?.querySelector('.label-text-alt');
    if (sensorHelp) {
        sensorHelp.textContent = configMode === 'quick'
            ? 'Location opzionali: compilale tutte oppure nessuna'
            : 'Location opzionali: compilale tutte oppure nessuna';
    }

    const saveButton = document.getElementById('configCampagnaSaveButton');
    if (saveButton) {
        saveButton.textContent = configMode === 'quick'
            ? 'Salva configurazione'
            : 'Salva configurazione';
    }
}

/**
 * Collega lo slider della frequenza al label di supporto.
 */
function wireFrequenzaSlider() {
    const slider = document.getElementById('frequenzaCampagna');
    if (!slider) return;
    slider.addEventListener('input', syncFrequenzaLabel);
    syncFrequenzaLabel();
}

/**
 * Aggiorna il label della frequenza in Hz.
 */
function syncFrequenzaLabel() {
    const slider = document.getElementById('frequenzaCampagna');
    const label = document.getElementById('frequenzaValue');
    if (!slider || !label) return;
    label.textContent = `${slider.value} Hz`;
}

function wireDurataControls() {
    const checkbox = document.getElementById('enableDurataCampagna');
    const input = document.getElementById('durataCampagna');
    if (!checkbox || !input) return;

    checkbox.addEventListener('change', syncDurataControls);
    syncDurataControls();
}

function syncDurataControls() {
    const checkbox = document.getElementById('enableDurataCampagna');
    const input = document.getElementById('durataCampagna');
    if (!checkbox || !input) return;

    const enabled = checkbox.checked;
    input.disabled = !enabled;
    input.required = enabled;
    if (!enabled) {
        input.value = '';
    }
}

/**
 * The drop‑down now contains application IDs instead of script names. we no longer
 * try to programmatically select a value based on the campaign type.
 */
function selectScriptByName(scriptName) {
    // no-op for backwards compatibility
}

function renderParamsForSelectedTipo() {
    const selected = document.querySelector('.tipo-radio:checked');
    if (!selected) {
        renderUserEditableParams('');
        return;
    }
    const appId = (selected.getAttribute('data-script') || '').trim();
    renderUserEditableParams(appId);
}

async function renderUserEditableParams(appId) {
    const container = document.getElementById('userEditableParamsContainer');
    const emptyHint = document.getElementById('userEditableParamsEmpty');
    if (!container || !emptyHint) return;

    const params = await fetchEditableParams(appId);
    const drafts = editableParamDraftsByApp.get(appId) || {};
    container.innerHTML = '';

    if (!params.length) {
        emptyHint.classList.remove('hidden');
        return;
    }

    emptyHint.classList.add('hidden');
    params.forEach((param) => {
        const key = String(param.key || '').trim();
        if (!key) return;

        const wrapper = document.createElement('label');
        wrapper.className = 'form-control';

        const label = document.createElement('span');
        label.className = 'label-text font-semibold';
        label.textContent = param.label || key;

        const labelWrap = document.createElement('span');
        labelWrap.className = 'label';
        labelWrap.appendChild(label);
        wrapper.appendChild(labelWrap);

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'input input-bordered w-full';
        input.value = Object.prototype.hasOwnProperty.call(drafts, key)
            ? String(drafts[key] ?? '')
            : (param.value == null ? '' : String(param.value));
        input.dataset.userAppParamKey = key;
        input.dataset.userAppId = appId;
        input.addEventListener('input', () => {
            saveEditableParamDraft(appId, key, input.value == null ? '' : String(input.value));
        });
        wrapper.appendChild(input);

        container.appendChild(wrapper);
    });
}

function saveEditableParamDraft(appId, key, value) {
    if (!appId || !key) return;
    const current = editableParamDraftsByApp.get(appId) || {};
    current[key] = value;
    editableParamDraftsByApp.set(appId, current);
}

async function fetchEditableParams(appId) {
    if (!appId) return [];
    if (editableParamsCache.has(appId)) {
        return editableParamsCache.get(appId);
    }

    try {
        const response = await fetch(`/api/v1/apps/${encodeURIComponent(appId)}/editable-params`, {
            headers: { 'Accept': 'application/json' }
        });
        if (!response.ok) {
            return [];
        }
        const data = await response.json();
        const params = Object.entries(data || {}).map(([key, value]) => ({
            key,
            label: key,
            value: value == null ? '' : String(value)
        }));
        editableParamsCache.set(appId, params);
        return params;
    } catch (_) {
        return [];
    }
}

function collectUserEditableParamValues() {
    const result = {};
    document.querySelectorAll('[data-user-app-param-key]').forEach((field) => {
        const key = field.dataset.userAppParamKey;
        if (!key) return;
        result[key] = field.value == null ? '' : String(field.value);
    });
    return result;
}

function syncSensorLocationInput(checkbox) {
    if (!checkbox) return;
    const input = document.querySelector(
        `[data-sensor-location-id="${CSS.escape(String(checkbox.value))}"]`
    );
    if (!input) return;
    const enabled = checkbox.checked && !checkbox.disabled;
    input.disabled = !enabled;
    input.required = false;
}

function collectSensorLocations() {
    const result = {};
    document.querySelectorAll('input[name="idSensori"]:checked:not(:disabled)').forEach((checkbox) => {
        const input = document.querySelector(
            `[data-sensor-location-id="${CSS.escape(String(checkbox.value))}"]`
        );
        result[checkbox.value] = input ? input.value.trim() : '';
    });
    return result;
}

function collectSelectedSensorIds() {
    return Array.from(document.querySelectorAll('input[name="idSensori"]:checked:not(:disabled)'))
        .map((checkbox) => Number(checkbox.value))
        .filter((value) => Number.isFinite(value));
}

document.body.addEventListener('change', (event) => {
    if (event.target && event.target.matches('input[name="idSensori"]')) {
        syncSensorLocationInput(event.target);
    }
});

document.body.addEventListener('htmx:configRequest', (event) => {
    if (!event.target || event.target.id !== 'createCampagnaForm') return;

    const enableDurata = document.getElementById('enableDurataCampagna');
    const durataInput = document.getElementById('durataCampagna');
    if (enableDurata && durataInput && enableDurata.checked) {
        const durata = Number(durataInput.value);
        if (!Number.isInteger(durata) || durata <= 0) {
            event.preventDefault();
            showCampagnaError('Inserisci una durata timer valida (minimo 1 minuto).');
            return;
        }
        event.detail.parameters.durata = durata;
    } else {
        delete event.detail.parameters.durata;
    }

    event.detail.parameters.userAppParams = collectUserEditableParamValues();
    event.detail.parameters.sensorLocations = collectSensorLocations();
});

// Gestione HTMX

document.body.addEventListener('htmx:afterRequest', (event) => {
    const targetId = event.target.id;

    if (targetId === 'createPersonaForm') {
        handlePersonaResponse(event);
    }

    if (targetId === 'createCampagnaForm') {
        handleCampagnaResponse(event);
    }

    if (event.target.matches('button[hx-post*="/api/v1/campagne/"]')) {
        handleCampagnaAction(event);
    }
});

document.body.addEventListener('htmx:responseError', (event) => {
    if (!event.target) return;
    const isCreateCampagna = event.target.id === 'createCampagnaForm';
    const isCampagnaAction = typeof event.target.matches === 'function'
        && event.target.matches('button[hx-post*="/api/v1/campagne/"]');
    if (!isCreateCampagna && !isCampagnaAction) return;

    const xhr = event.detail ? event.detail.xhr : null;
    showCampagnaError(parseErrorMessage(xhr), xhr);
});

document.body.addEventListener('htmx:afterSwap', (event) => {
    if (event.target && event.target.id === 'pazienteSelectWrapper') {
        wirePersonaSearch();
    }
});

function handlePersonaResponse(event) {
    const { successful, xhr } = event.detail;
    const createdPersonaId = extractIdFromResponse(xhr);

    if (successful) {
        hidePersonaError();
        document.getElementById('createPersonaForm').reset();
        document.getElementById('createPersonaModal').close();
        showSuccess('Paziente creato con successo!');

        // aggiorna select pazienti
        htmx.ajax('GET', '/fragments/persone/select', {
            target: '#pazienteSelectWrapper',
            swap: 'outerHTML'
        });
        if (createdPersonaId) {
            setTimeout(() => {
                const select = document.getElementById('selectPaziente');
                if (select) select.value = String(createdPersonaId);
            }, 150);
        }
        return;
    }

    const message = parseErrorMessage(xhr);
    showPersonaError(message);
}

/**
 * Gestisce l'esito della creazione campagna (successo/errore).
 */
function handleCampagnaResponse(event) {
    const { successful, xhr } = event.detail;

    if (successful) {
        const createdCampagnaId = extractIdFromResponse(xhr);
        hideCampagnaError();
        document.getElementById('createCampagnaForm').reset();
        resetCampagnaConfigUI();
        document.getElementById('createCampagnaModal').close();
        const configModal = document.getElementById('configCampagnaModal');
        if (configModal) configModal.close();

        showSuccess('Creazione Campagna in corso!');
        /*if (window.BSNLiveMonitor) {
            window.BSNLiveMonitor.openFromResponse(xhr);
        }*/

        // aggiorna tabella home
        htmx.ajax('GET', '/fragments/campagne/home', {
            target: '#campagneTableBody',
            swap: 'innerHTML'
        });

        if (createdCampagnaId) {
            monitorCampagnaStartup(createdCampagnaId);
        }
        return;
    }

    const message = parseErrorMessage(xhr);
    showCampagnaError(message, xhr);
}

/**
 * Gestisce le azioni sulle campagne (termina/elimina).
 */
function handleCampagnaAction(event) {
    const { successful, xhr } = event.detail;
    if (!successful) {
        showCampagnaError(parseErrorMessage(xhr), xhr);
        return;
    }
    const action = event.target.getAttribute('hx-post') || '';
    if (action.includes('/termina')) {
        showSuccess('Terminazione campagna in corso...');
        if (window.BSNLiveMonitor) {
            window.BSNLiveMonitor.close();
        }
    } else {
        showSuccess('Operazione completata con successo!');
    }
    htmx.ajax('GET', '/fragments/campagne/home', {
        target: '#campagneTableBody',
        swap: 'innerHTML'
    });
}

document.body.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action="live"]');
    if (!button || !window.BSNLiveMonitor) return;
    window.BSNLiveMonitor.openFromButton(button);
});

// Modali

/**
 * Apre il modale di avvio nuova campagna.
 */
function openCreateCampagnaModal() {
    if (!hasOnlineNodes) {
        return;
    }
    if (typeof window.refreshAvailableSensors === 'function') {
        window.refreshAvailableSensors();
    }
    document.getElementById('createCampagnaModal').showModal();
}

/**
 * Apre il modale di creazione paziente e ripristina quello campagna al termine.
 */
function openCreatePersonaModal() {
    const campagnaModal = document.getElementById('createCampagnaModal');
    const personaModal = document.getElementById('createPersonaModal');
    if (!personaModal) return;
    const shouldReturn = campagnaModal && campagnaModal.open;
    personaModal.dataset.returnToCampagna = shouldReturn ? 'true' : 'false';
    if (campagnaModal && campagnaModal.open) {
        campagnaModal.close();
    }
    if (!personaModal.dataset.boundClose) {
        personaModal.addEventListener('close', () => restoreCampagnaModal());
        personaModal.dataset.boundClose = 'true';
    }
    personaModal.showModal();
}

/**
 * Riapre il modale campagna se era aperto prima della creazione paziente.
 */
function restoreCampagnaModal() {
    const personaModal = document.getElementById('createPersonaModal');
    if (!personaModal || personaModal.dataset.returnToCampagna !== 'true') return;
    const campagnaModal = document.getElementById('createCampagnaModal');
    if (campagnaModal && !campagnaModal.open) {
        campagnaModal.showModal();
    }
}

function saveCampagnaConfigAndClose() {
    if (configMode === 'quick') {
        saveQuickApplicationConfigAndClose();
        return;
    }

    const selectedTipo = document.querySelector('.tipo-radio:checked');
    if (!selectedTipo) {
        showCampagnaError('Seleziona un tipo di campagna.');
        return;
    }

    const scriptInput = document.getElementById('scriptFileName');
    if (!scriptInput || !scriptInput.value) {
        showCampagnaError('Configura il tipo di campagna selezionato.');
        return;
    }

    const connettivita = document.getElementById('connettivitaCampagna');
    if (!connettivita || !connettivita.value) {
        showCampagnaError('Seleziona la connettivita della campagna.');
        return;
    }

    const dbConfig = document.getElementById('dbConfigId');
    if (!dbConfig || !dbConfig.value) {
        showCampagnaError('Seleziona il database per il salvataggio dati.');
        return;
    }

    const enabledSensors = Array.from(document.querySelectorAll('input[name="idSensori"]:not(:disabled)'));
    const hasSelectedSensor = enabledSensors.some((sensor) => sensor.checked);
    if (!hasSelectedSensor) {
        showCampagnaError('Seleziona almeno un sensore disponibile.');
        return;
    }
    const selectedLocationValues = enabledSensors
        .filter(sensor => sensor.checked)
        .map(sensor => {
            const input = document.querySelector(
                `[data-sensor-location-id="${CSS.escape(String(sensor.value))}"]`
            );
            return input ? input.value.trim() : '';
        });
    const hasAnyLocation = selectedLocationValues.some(location => location.length > 0);
    const hasAllLocations = selectedLocationValues.every(location => location.length > 0);
    if (hasAnyLocation && !hasAllLocations) {
        showCampagnaError('Inserisci la location per tutti i sensori selezionati oppure lasciale tutte vuote.');
        return;
    }

    const enableDurata = document.getElementById('enableDurataCampagna');
    const durataInput = document.getElementById('durataCampagna');
    if (enableDurata && durataInput && enableDurata.checked) {
        const durata = Number(durataInput.value);
        if (!Number.isInteger(durata) || durata <= 0) {
            showCampagnaError('Inserisci una durata timer valida (minimo 1 minuto).');
            return;
        }
    }

    hideCampagnaError();
    const modal = document.getElementById('configCampagnaModal');
    if (modal) modal.close();
}

function saveQuickApplicationConfigAndClose() {
    if (!quickApplicationConfig || !quickApplicationConfig.appId) {
        showCampagnaError('Applicazione rapida non selezionata.');
        return;
    }

    const enabledSensors = Array.from(document.querySelectorAll('input[name="idSensori"]:not(:disabled)'));
    const hasSelectedSensor = enabledSensors.some((sensor) => sensor.checked);
    if (!hasSelectedSensor) {
        showCampagnaError('Seleziona almeno un sensore disponibile.');
        return;
    }

    const selectedLocationValues = enabledSensors
        .filter(sensor => sensor.checked)
        .map(sensor => {
            const input = document.querySelector(
                `[data-sensor-location-id="${CSS.escape(String(sensor.value))}"]`
            );
            return input ? input.value.trim() : '';
        });
    const hasAnyLocation = selectedLocationValues.some(location => location.length > 0);
    const hasAllLocations = selectedLocationValues.every(location => location.length > 0);
    if (hasAnyLocation && !hasAllLocations) {
        showCampagnaError('Inserisci la location per tutti i sensori selezionati oppure lasciale tutte vuote.');
        return;
    }

    quickApplicationConfig = {
        ...quickApplicationConfig,
        configured: true,
        idSensori: collectSelectedSensorIds(),
        sensorLocations: collectSensorLocations(),
        userAppParams: collectUserEditableParamValues()
    };

    hideCampagnaError();
    const modal = document.getElementById('configCampagnaModal');
    if (modal) modal.close();
    showSuccess('Configurazione applicazione rapida salvata.');
}

async function startQuickApplication(button) {
    if (!hasOnlineNodes) {
        showCampagnaError('Serve almeno un nodo online per avviare l’applicazione.');
        return;
    }

    const appId = (button.getAttribute('data-script') || '').trim();
    const codice = (button.getAttribute('data-codice') || '').trim();
    if (!quickApplicationConfig
            || quickApplicationConfig.appId !== appId
            || quickApplicationConfig.configured !== true) {
        openQuickApplicationConfig(button);
        showCampagnaError('Configura l’applicazione rapida prima di avviarla.');
        return;
    }

    const payload = {
        appId,
        idSensori: quickApplicationConfig.idSensori || [],
        sensorLocations: quickApplicationConfig.sensorLocations || {},
        userAppParams: quickApplicationConfig.userAppParams || {}
    };

    if (!payload.idSensori.length) {
        openQuickApplicationConfig(button);
        showCampagnaError('Seleziona almeno un sensore disponibile.');
        return;
    }

    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Avvio...';

    try {
        const response = await fetch('/api/v1/apps/quick-start', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const data = await response.json().catch(() => null);
            throw new Error(data && data.message ? data.message : 'Errore avvio applicazione');
        }

        showSuccess(`Applicazione ${codice || appId} avviata.`);
    } catch (error) {
        showCampagnaError(error.message || 'Errore avvio applicazione rapida.');
    } finally {
        button.disabled = !hasOnlineNodes;
        button.textContent = originalText;
    }
}

/**
 * Ricerca paziente: mostra suggerimenti e seleziona il valore nella select.
 */
function wirePersonaSearch() {
    const input = document.getElementById('searchPaziente');
    const select = document.getElementById('selectPaziente');
    const results = document.getElementById('pazienteSearchResults');
    if (!input || !select || !results) return;
    if (input.dataset.bound) return;
    input.dataset.bound = 'true';

    const clearResults = () => {
        results.innerHTML = '';
        results.classList.add('hidden');
    };

    const buildResults = () => {
        const query = (input.value || '').trim().toLowerCase();
        results.innerHTML = '';
        if (!query) {
            clearResults();
            return;
        }
        const matches = Array.from(select.options)
            .slice(1)
            .filter(option => option.textContent.toLowerCase().includes(query));
        if (!matches.length) {
            clearResults();
            return;
        }
        matches.forEach(option => {
            const item = document.createElement('button');
            item.type = 'button';
            item.dataset.value = option.value;
            item.dataset.label = option.textContent;
            item.className = 'w-full text-left px-2 py-1 text-sm hover:bg-base-200';
            item.textContent = option.textContent;
            results.appendChild(item);
        });
        results.classList.remove('hidden');
    };

    input.addEventListener('input', buildResults);
    input.addEventListener('focus', buildResults);
    input.addEventListener('blur', () => clearResults());
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            clearResults();
        }
    });

    results.addEventListener('mousedown', (event) => {
        if (event.target.closest('[data-value]')) {
            event.preventDefault();
        }
    });

    results.addEventListener('click', (event) => {
        const item = event.target.closest('[data-value]');
        if (!item) return;
        select.value = item.dataset.value;
        input.value = item.dataset.label;
        clearResults();
    });

    select.addEventListener('change', () => {
        const option = select.options[select.selectedIndex];
        input.value = option && option.value ? option.textContent : '';
    });
}

// Messaggi

function showSuccess(message) {
    const alert = document.getElementById('successAlert');
    const text = document.getElementById('successAlertText');
    if (!alert || !text) return;
    text.textContent = message;
    alert.classList.remove('hidden');
    setTimeout(() => alert.classList.add('hidden'), 3000);
}

/**
 * Mostra l'errore nel box della creazione campagna.
 */
function showCampagnaError(message, xhr) {
    const box = document.getElementById('createCampagnaError');
    const text = document.getElementById('createCampagnaErrorText');
    const finalMessage = message || 'Errore durante la configurazione della campagna';
    showSimpleErrorAlert(finalMessage, xhr);
    if (!box || !text) return;
    text.textContent = finalMessage;
    box.classList.remove('hidden');
}

/**
 * Nasconde il box errori della creazione campagna.
 */
function hideCampagnaError() {
    const box = document.getElementById('createCampagnaError');
    if (box) box.classList.add('hidden');
}

/**
 * Mostra l'errore nel box della creazione paziente.
 */
function showPersonaError(message) {
    const box = document.getElementById('createPersonaError');
    const text = document.getElementById('createPersonaErrorText');
    if (!box || !text) return;
    text.textContent = message;
    box.classList.remove('hidden');
}

/**
 * Nasconde il box errori della creazione paziente.
 */
function hidePersonaError() {
    const box = document.getElementById('createPersonaError');
    if (box) box.classList.add('hidden');
}

/**
 * Estrae un messaggio leggibile dalla risposta HTTP.
 */
function parseErrorMessage(xhr) {
    if (!xhr) return 'Errore sconosciuto';
    const raw = xhr.responseText || xhr.statusText || 'Errore';
    try {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.message) return parsed.message;
    } catch (_) {
        // ignore JSON parse errors
    }
    return raw;
}

function showSimpleErrorAlert(message, xhr) {
    if (xhr) {
        if (xhr.bsnErrorAlertShown) return;
        xhr.bsnErrorAlertShown = true;
    }
    window.alert(message);
}

/**
 * Estrae l'id creato dal body JSON (se presente).
 */
function extractIdFromResponse(xhr) {
    if (!xhr || !xhr.responseText) return null;
    try {
        const parsed = JSON.parse(xhr.responseText);
        return parsed && parsed.id ? parsed.id : null;
    } catch (_) {
        return null;
    }
}

function notifyRrmStyleError(message) {
    const text = String(message || '').trim();
    if (!text) return;

    const payload = {
        message: text,
        severity: 'error'
    };

    if (window.BSNRrmNotifications && typeof window.BSNRrmNotifications.enqueue === 'function') {
        window.BSNRrmNotifications.enqueue(payload);
        return;
    }

    window.dispatchEvent(new CustomEvent('rrm-gui-notification', {
        detail: payload
    }));
}

function monitorCampagnaStartup(campagnaId) {
    const id = Number(campagnaId);
    if (!Number.isFinite(id)) return;
    if (startupMonitors.has(id)) return;

    let attempts = 0;
    const maxAttempts = 60;
    const pollMs = 2000;

    const timerId = setInterval(async () => {
        attempts += 1;
        try {
            const response = await fetch(`/api/v1/campagne/${id}`, {
                headers: { 'Accept': 'application/json' }
            });

            if (!response.ok) {
                if (attempts >= maxAttempts) {
                    stopCampagnaStartupMonitor(id);
                }
                return;
            }

            const campagna = await response.json();
            const stato = String(campagna?.stato || '');

            if (stato === 'AVVIO_FALLITO') {
                stopCampagnaStartupMonitor(id);
                const popupMessage = extractStartupFailurePopupMessage(campagna?.note);
                if (popupMessage && !notifiedStartupFailures.has(id)) {
                    notifiedStartupFailures.add(id);
                    notifyRrmStyleError(popupMessage);
                }
                return;
            }

            if (stato !== 'AVVIO_IN_CORSO' || attempts >= maxAttempts) {
                stopCampagnaStartupMonitor(id);
            }
        } catch (_) {
            if (attempts >= maxAttempts) {
                stopCampagnaStartupMonitor(id);
            }
        }
    }, pollMs);

    startupMonitors.set(id, timerId);
}

function stopCampagnaStartupMonitor(campagnaId) {
    const timerId = startupMonitors.get(campagnaId);
    if (!timerId) return;
    clearInterval(timerId);
    startupMonitors.delete(campagnaId);
}

function extractStartupFailurePopupMessage(note) {
    if (!note) return null;

    const lines = String(note).split('\n').reverse();
    for (const line of lines) {
        const systemPrefix = '[SYSTEM]:';
        const systemIdx = line.indexOf(systemPrefix);
        const content = (systemIdx >= 0
            ? line.substring(systemIdx + systemPrefix.length)
            : line).trim();

        if (content.startsWith('Avvio fallito:')) {
            const reason = content.substring('Avvio fallito:'.length).trim();
            if (reason.startsWith('Avvio Fallito:')) {
                return reason;
            }
        }

        if (content.startsWith('Avvio Fallito:')) {
            return content;
        }
    }

    return null;
}
