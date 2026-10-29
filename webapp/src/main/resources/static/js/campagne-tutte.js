/**
 * Pagina "Tutte le campagne".
 * Flow:
 * 1) filtri + ricerca impostano i parametri (stato/persona/nome/data).
 * 2) refreshCampagne() ricarica il frammento via HTMX con paginazione.
 * 3) azioni campagna (termina/elimina) aggiornano la tabella corrente.
 */
let currentFilter = 'TUTTI';
let currentPage = 1;
let searchTimer = null;

window.addEventListener('DOMContentLoaded', () => {
    setActiveFilterButton('TUTTI');
    syncCurrentPageFromDom();
    bindFilterButtons();
    bindSearchControls();
});

document.body.addEventListener('htmx:afterRequest', (event) => {
    if (event.target.matches('button[hx-post*="/api/v1/campagne/"]')) {
        const { successful, xhr } = event.detail;
        if (successful) {
            const action = event.target.getAttribute('hx-post') || '';
            if (action.includes('/termina')) {
                alert('Campagna terminata con successo');
                if (window.BSNLiveMonitor) {
                    window.BSNLiveMonitor.close();
                }
            } else if (action.includes('/elimina')) {
                alert('Campagna eliminata con successo');
            } else {
                alert('Operazione completata con successo');
            }
            refreshCampagne();
        } else {
            alert(parseErrorMessage(xhr));
        }
    }
});

document.body.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action="live"]');
    if (!button || !window.BSNLiveMonitor) return;
    window.BSNLiveMonitor.openFromButton(button);
});

document.body.addEventListener('click', (event) => {
    const button = event.target.closest('#campagnePagination [data-page]');
    if (!button) return;
    event.preventDefault();
    if (button.classList.contains('btn-disabled')) return;
    const target = button.dataset.page;
    const totalPages = getTotalPages();
    if (target === 'prev') {
        currentPage = Math.max(1, currentPage - 1);
    } else if (target === 'next') {
        currentPage = Math.min(totalPages, currentPage + 1);
    } else {
        const page = Number(target);
        if (!Number.isNaN(page)) {
            currentPage = page;
        }
    }
    refreshCampagne();
});

document.body.addEventListener('htmx:afterSwap', (event) => {
    if (event.target && event.target.id === 'campagneTableWrapper') {
        syncCurrentPageFromDom();
    }
});

/**
 * Ricarica il frammento campagne con filtri e pagina corrente.
 */
function refreshCampagne() {
    const params = new URLSearchParams();
    params.set('stato', currentFilter);
    params.set('page', currentPage);
    const persona = getSearchValue('searchPersona');
    const campagna = getSearchValue('searchCampagna');
    const dataInizio = getSearchValue('searchDataInizio');
    if (persona) params.set('persona', persona);
    if (campagna) params.set('campagna', campagna);
    if (dataInizio) params.set('dataInizio', dataInizio);

    htmx.ajax('GET', `/fragments/campagne/all?${params.toString()}`, {
        target: '#campagneTableWrapper',
        swap: 'innerHTML'
    });
}

/**
 * Evidenzia il filtro attivo nella UI.
 */
function setActiveFilterButton(filter) {
    currentFilter = filter;
    document.querySelectorAll('#filtriCampagne button').forEach(btn => {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-outline');
    });
    const active = document.querySelector(`#filtriCampagne button[data-filter="${filter}"]`);
    if (active) {
        active.classList.add('btn-primary');
        active.classList.remove('btn-outline');
    }
}

/**
 * Collega i bottoni di filtro allo stato e al refresh.
 */
function bindFilterButtons() {
    document.querySelectorAll('#filtriCampagne button[data-filter]').forEach(btn => {
        btn.addEventListener('click', (event) => {
            event.preventDefault();
            if (!btn.dataset.filter) return;
            setActiveFilterButton(btn.dataset.filter);
            currentPage = 1;
            refreshCampagne();
        });
    });
}

/**
 * Collega input di ricerca e data al refresh con debounce.
 */
function bindSearchControls() {
    const personaInput = document.getElementById('searchPersona');
    const campagnaInput = document.getElementById('searchCampagna');
    const dataInput = document.getElementById('searchDataInizio');

    const onInput = () => scheduleRefresh();
    if (personaInput) personaInput.addEventListener('input', onInput);
    if (campagnaInput) campagnaInput.addEventListener('input', onInput);
    if (dataInput) dataInput.addEventListener('change', () => {
        currentPage = 1;
        refreshCampagne();
    });
}

/**
 * Debounce per evitare richieste troppo frequenti durante la digitazione.
 */
function scheduleRefresh() {
    if (searchTimer) {
        clearTimeout(searchTimer);
    }
    currentPage = 1;
    searchTimer = setTimeout(() => refreshCampagne(), 250);
}

/**
 * Legge un valore di input in modo sicuro.
 */
function getSearchValue(id) {
    const input = document.getElementById(id);
    if (!input) return '';
    return (input.value || '').trim();
}

/**
 * Sincronizza la pagina corrente dai data-attributes del DOM.
 */
function syncCurrentPageFromDom() {
    const pagination = document.getElementById('campagnePagination');
    if (!pagination) return;
    const pageValue = Number(pagination.dataset.currentPage);
    if (!Number.isNaN(pageValue) && pageValue > 0) {
        currentPage = pageValue;
    }
}

/**
 * Recupera il numero totale di pagine disponibili.
 */
function getTotalPages() {
    const pagination = document.getElementById('campagnePagination');
    if (!pagination) return currentPage;
    const value = Number(pagination.dataset.totalPages);
    if (Number.isNaN(value) || value <= 0) return currentPage;
    return value;
}

/**
 * Estrae un messaggio leggibile dalla risposta HTTP.
 */
function parseErrorMessage(xhr) {
    if (!xhr) return 'Errore';
    const raw = xhr.responseText || xhr.statusText || 'Errore';
    try {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.message) return parsed.message;
    } catch (_) {
        // ignore
    }
    return raw;
}
