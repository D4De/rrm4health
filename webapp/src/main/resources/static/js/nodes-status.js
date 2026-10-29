// Aggiorna la card "Nodi online" tramite eventi SSE dal RrmConnectionController.
(function() {
    const body = document.getElementById('nodesStatusCardBody');
    if (!body) return;

    const warning = document.getElementById('nodesWarning');
    const list = document.getElementById('nodesStatusList');

    let source = null;

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function setEmpty(message) {
        list.innerHTML = '<div class="alert alert-info py-2"><span>' + escapeHtml(message) + '</span></div>';
    }

    function publishNodesStatus(nodes, connected) {
        const onlineCount = Array.isArray(nodes) ? nodes.length : 0;
        window.dispatchEvent(new CustomEvent('nodes-status-updated', {
            detail: {
                onlineCount: onlineCount,
                connected: Boolean(connected)
            }
        }));
    }

    function render(payload) {
        const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
        const connected = Boolean(payload.connected);

        warning.classList.toggle('hidden', connected);
        publishNodesStatus(nodes, connected);

        if (!nodes.length) {
            setEmpty('Nessun nodo online rilevato.');
            return;
        }

        list.innerHTML = nodes.map(function(node) {
            const ip = escapeHtml(node.node_ip || 'n/d');
            const port = escapeHtml(node.node_port == null ? 'n/d' : node.node_port);
            const status = escapeHtml(node.status || 'ONLINE');

            return [
                '<div class="rounded-xl border border-base-300 bg-base-200/60 p-3">',
                '  <div class="flex items-center justify-between gap-2">',
                '    <div class="font-semibold">' + ip + ':' + port + '</div>',
                '    <span class="badge badge-success">' + status + '</span>',
                '  </div>',
                '</div>'
            ].join('');
        }).join('');
    }

    function fetchSnapshot() {
        fetch('/api/v1/rrm/connection/nodes-status/online', { headers: { 'Accept': 'application/json' } })
            .then(function(resp) { return resp.ok ? resp.json() : null; })
            .then(function(payload) {
                if (payload) {
                    render(payload);
                } else {
                    publishNodesStatus([], false);
                }
            })
            .catch(function() {
                setEmpty('Impossibile leggere lo stato nodi.');
                publishNodesStatus([], false);
            });
    }

    function connect() {
        if (source) source.close();

        source = new EventSource('/api/v1/rrm/connection/nodes-status/events');
        source.addEventListener('nodes-status', function(event) {
            try {
                render(JSON.parse(event.data));
            } catch (_) {
                // ignore malformed events
            }
        });

        source.onmessage = function(event) {
            try {
                render(JSON.parse(event.data));
            } catch (_) {
                // ignore malformed events
            }
        };

        source.onerror = function() {
            if (source) source.close();
            publishNodesStatus([], false);
            setTimeout(connect, 2000);
        };
    }

    fetchSnapshot();
    connect();
})();
