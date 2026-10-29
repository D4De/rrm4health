// Aggiorna la card "Status sensori" tramite eventi SSE dal RrmConnectionController.
(function() {
    const body = document.getElementById('resourcesStatusCardBody');
    if (!body) return;

    const warning = document.getElementById('resourcesWarning');
    const list = document.getElementById('resourcesStatusList');
    const connectionBanner = document.getElementById('rrmConnectionBanner');
    const connectionText = document.getElementById('rrmConnectionText');
    const connectionIconConnected = document.getElementById('rrmConnectionIconConnected');
    const connectionIconDisconnected = document.getElementById('rrmConnectionIconDisconnected');

    let source = null;

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function statusBadgeClass(status) {
        const normalized = String(status || '').toUpperCase();
        if (normalized === 'ACTIVE') return 'badge-success';
        if (normalized === 'INACTIVE') return 'badge-warning';
        return 'badge-neutral';
    }

    function setEmpty(message) {
        list.innerHTML = '<div class="alert alert-info py-2"><span>' + escapeHtml(message) + '</span></div>';
    }

    function updateConnectionBanner(connected) {
        if (!connectionBanner || !connectionText) return;

        connectionBanner.classList.toggle('success', Boolean(connected));
        connectionBanner.classList.toggle('error', !Boolean(connected));
        connectionText.textContent = connected ? 'Sistema connesso!' : 'Sistema non connesso.';

        if (connectionIconConnected) {
            connectionIconConnected.classList.toggle('hidden', !Boolean(connected));
        }
        if (connectionIconDisconnected) {
            connectionIconDisconnected.classList.toggle('hidden', Boolean(connected));
        }
    }

    function render(payload) {
        const resources = Array.isArray(payload.resources) ? payload.resources : [];
        const connected = Boolean(payload.connected);

        warning.classList.toggle('hidden', connected);
        updateConnectionBanner(connected);

        if (!resources.length) {
            setEmpty('Nessun sensore DB trovato nello stato risorse RRM.');
            return;
        }

        list.innerHTML = resources.map(function(resource) {
            const rid = escapeHtml(resource.resource_id);
            const type = escapeHtml(resource.type);
            const status = escapeHtml(resource.status);
            const connection = escapeHtml(resource.connection);
            const badgeClass = statusBadgeClass(resource.status);
            return [
                '<div class="rounded-xl border border-base-300 bg-base-200/60 p-3">',
                '  <div class="flex items-start justify-between gap-2">',
                '    <div>',
                '      <div class="font-semibold">' + rid + '</div>',
                '      <div class="text-xs text-gray-500">' + type + '</div>',
                '    </div>',
                '    <span class="badge ' + badgeClass + '">' + status + '</span>',
                '  </div>',
                '  <div class="mt-2 text-xs text-gray-600">Connessione: <span class="font-medium">' + connection + '</span></div>',
                '</div>'
            ].join('');
        }).join('');
    }

    function fetchSnapshot() {
        fetch('/api/v1/rrm/connection/resources-status/filtered', { headers: { 'Accept': 'application/json' } })
            .then(function(resp) { return resp.ok ? resp.json() : null; })
            .then(function(payload) {
                if (payload) {
                    render(payload);
                    return;
                }

                updateConnectionBanner(false);
                setEmpty('Impossibile leggere lo stato risorse.');
            })
            .catch(function() {
                updateConnectionBanner(false);
                setEmpty('Impossibile leggere lo stato risorse.');
            });
    }

    function connect() {
        if (source) source.close();

        source = new EventSource('/api/v1/rrm/connection/resources-status/events');
        source.addEventListener('resources-status', function(event) {
            try {
                render(JSON.parse(event.data));
            } catch (_) {
                // ignore malformed events
            }
        });

        source.onmessage = function(event) {
            // fallback in caso di eventi senza nome
            try {
                render(JSON.parse(event.data));
            } catch (_) {
                // ignore malformed events
            }
        };

        source.onerror = function() {
            if (source) source.close();
            updateConnectionBanner(false);
            warning.classList.remove('hidden');
            setTimeout(connect, 2000);
        };
    }

    fetchSnapshot();
    connect();
})();
