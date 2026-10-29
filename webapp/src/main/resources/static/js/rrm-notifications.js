// Mostra un modal quando arriva una notifica asincrona dall'RRM.
(function() {
    const modal = document.getElementById('rrmNotificationModal');
    const box = document.getElementById('rrmNotificationBox');
    const messageNode = document.getElementById('rrmNotificationMessage');
    const severityBadge = document.getElementById('rrmNotificationSeverity');
    const severityText = document.getElementById('rrmNotificationSeverityText');
    const icon = document.getElementById('rrmNotificationIcon');

    if (!modal || !box || !messageNode || !severityBadge || !severityText || !icon) {
        return;
    }

    let source = null;
    const notificationQueue = [];

    function normalizeSeverity(severity) {
        const value = String(severity || 'info').toLowerCase();
        if (value === 'error' || value === 'warning' || value === 'info') {
            return value;
        }
        return 'info';
    }

    function severityToBadgeClass(severity) {
        if (severity === 'error') return 'badge badge-error mt-2';
        if (severity === 'warning') return 'badge badge-warning mt-2';
        return 'badge badge-info mt-2';
    }

    function severityToBoxClass(severity) {
        if (severity === 'error') return 'modal-box max-w-xl rrm-notification-box rrm-notification-error';
        if (severity === 'warning') return 'modal-box max-w-xl rrm-notification-box rrm-notification-warning';
        return 'modal-box max-w-xl rrm-notification-box rrm-notification-info';
    }

    function severityToLabel(severity) {
        if (severity === 'error') return 'Errore';
        if (severity === 'warning') return 'Attenzione';
        return 'Info';
    }

    function severityToIcon(severity) {
        if (severity === 'error') return '!';
        if (severity === 'warning') return '!';
        return 'i';
    }

    function renderNotification(payload) {
        const severity = normalizeSeverity(payload && payload.severity);
        const message = payload && payload.message ? String(payload.message) : 'Notifica senza contenuto.';

        box.className = severityToBoxClass(severity);
        severityBadge.className = severityToBadgeClass(severity);
        severityText.textContent = severityToLabel(severity);
        icon.textContent = severityToIcon(severity);
        messageNode.textContent = message;

    }

    function showNextNotification() {
        if (modal.open || notificationQueue.length === 0 || document.hidden || !document.hasFocus()) {
            return;
        }

        const nextPayload = notificationQueue[0];
        renderNotification(nextPayload);

        if (typeof modal.showModal === 'function') {
            try {
                modal.showModal();
                notificationQueue.shift();
            } catch (_) {
                // La notifica resta in coda e verra riprovata al prossimo focus.
            }
        }
    }

    function enqueueNotification(payload) {
        notificationQueue.push(payload || {});
        showNextNotification();
    }

    function enqueueExternalNotification(payload) {
        if (!payload || !payload.message) {
            return;
        }
        enqueueNotification(payload);
    }

    function connect() {
        if (source) source.close();

        source = new EventSource('/api/v1/rrm/connection/gui-notifications/events');

        source.addEventListener('gui-notification', function(event) {
            try {
                const payload = JSON.parse(event.data);
                enqueueNotification(payload);
            } catch (_) {
                // ignore malformed payload
            }
        });

        source.onmessage = function(event) {
            // fallback for unnamed SSE events
            try {
                const payload = JSON.parse(event.data);
                if (payload && payload.message) {
                    enqueueNotification(payload);
                }
            } catch (_) {
                // ignore malformed payload
            }
        };

        source.onerror = function() {
            if (source) source.close();
            setTimeout(connect, 2000);
        };
    }

    window.BSNRrmNotifications = {
        enqueue: enqueueExternalNotification
    };

    window.addEventListener('rrm-gui-notification', function(event) {
        const payload = event && event.detail ? event.detail : null;
        enqueueExternalNotification(payload);
    });

    modal.addEventListener('close', showNextNotification);
    window.addEventListener('focus', showNextNotification);
    window.addEventListener('pageshow', showNextNotification);
    document.addEventListener('visibilitychange', showNextNotification);

    connect();
})();
