// Script per aggiornamento live sensori via SSE
(function() {
    const sensoriContainer = document.getElementById('sensoriConfigContainer');
    if (!sensoriContainer) return;
    let selezionati = [];
    let locations = {};
    let eventSource = null;

    function renderSensori(sensori) {
        // Mantieni selezione solo se il sensore non è occupato
        const selezionatiValidi = selezionati.filter(id => sensori.some(s => String(s.id) === id && !s.occupato));
        sensoriContainer.innerHTML = '';
        sensori.forEach(sensore => {
            const id = String(sensore.id);
            const checked = !sensore.occupato && selezionatiValidi.includes(id);
            const row = document.createElement('div');
            row.className = 'grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(220px,1fr)] sm:items-center';

            const label = document.createElement('label');
            label.className = 'cursor-pointer flex items-center gap-2';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'checkbox checkbox-sm';
            checkbox.name = 'idSensori';
            checkbox.value = id;
            checkbox.setAttribute('form', 'createCampagnaForm');
            checkbox.disabled = Boolean(sensore.occupato);
            checkbox.checked = checked;
            label.appendChild(checkbox);

            const description = document.createElement('span');
            description.className = 'label-text';
            description.textContent = `${sensore.nome || 'Sensore'} (${sensore.tipo || '-'})`;
            if (sensore.occupato) {
                const badge = document.createElement('span');
                badge.className = 'ml-2 badge badge-error text-xs';
                badge.textContent = 'In uso';
                description.appendChild(badge);
            }
            label.appendChild(description);
            row.appendChild(label);

            const location = document.createElement('input');
            location.type = 'text';
            location.maxLength = 255;
            location.className = 'input input-bordered input-sm w-full sensor-location-input';
            location.dataset.sensorLocationId = id;
            location.placeholder = 'Location (es. polso destro)';
            location.value = locations[id] || '';
            location.disabled = !checked;
            location.required = false;
            row.appendChild(location);
            sensoriContainer.appendChild(row);
        });
    }

    window.refreshAvailableSensors = function() {
        selezionati = Array.from(sensoriContainer.querySelectorAll('input[type=checkbox]:checked:not(:disabled)'))
            .map(cb => cb.value);
        locations = {};
        sensoriContainer.querySelectorAll('[data-sensor-location-id]').forEach(input => {
            locations[input.dataset.sensorLocationId] = input.value;
        });
        fetch('/api/v1/sensori/disponibili', { credentials: 'same-origin' })
            .then(response => response.ok ? response.json() : Promise.reject(response))
            .then(renderSensori)
            .catch(() => {});
    };

    function connectSse() {
        if (eventSource) eventSource.close();
        eventSource = new EventSource('/sse/sensori');
        eventSource.onmessage = function(event) {
            try {
                // Salva selezione attuale
                selezionati = Array.from(sensoriContainer.querySelectorAll('input[type=checkbox]:checked:not(:disabled)'))
                    .map(cb => cb.value);
                locations = {};
                sensoriContainer.querySelectorAll('[data-sensor-location-id]').forEach(input => {
                    locations[input.dataset.sensorLocationId] = input.value;
                });
                const sensori = JSON.parse(event.data);
                renderSensori(sensori);
            } catch (e) {}
        };
        eventSource.onerror = function() {
            // Riprova dopo 2s
            setTimeout(connectSse, 2000);
        };
    }
    connectSse();
})();
