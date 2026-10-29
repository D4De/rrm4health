/**
 * Live monitor della campagna.
 * Flusso: apre una connessione SSE verso /sse/imu, riceve eventi "imu" e "battery",
 * aggiorna i dataset Chart.js e mostra lo stato sensori/batteria.
 */
window.BSNLiveMonitor = (() => {
    const imuBuffer = [];
    let chartUpdateTimer = null;
    const CHART_UPDATE_INTERVAL = 500; // ms
    const SENSOR_INACTIVE_THRESHOLD_MS = 5000; // ms
    const HISTORY_LIMIT = 120;
    const OUTPUT_HISTORY_LIMIT = 10;
    const dirtyCharts = new Set();

    function flushImuBuffer() {
        if (!imuBuffer.length) return;

        for (const payload of imuBuffer) {
            processPayloadForCharts(payload);
        }
        imuBuffer.length = 0;

        for (const chartKey of dirtyCharts) {
            const chart = charts[chartKey];
            if (chart) chart.update('none');
        }
        dirtyCharts.clear();
    }
    const palette = [
        '#e11d48', '#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6', '#f97316',
        '#14b8a6', '#22c55e', '#ef4444', '#3b82f6', '#a855f7', '#84cc16'
    ];

    const charts = {};
    const datasets = {};
    const battery = {};
    const lastSeen = {};
    const imuHistory = {};
    const applicationOutputs = {};
    let eventSource = null;
    let campaignId = null;
    let campaignName = null;
    let sensorList = [];
    let sensorLocations = {};
    let currentLayout = 'axis';

    /**
     * Flow sintetico:
     * 1) {@link open()} inizializza UI e grafici
     * 2) {@link connectSse()} crea EventSource verso /sse/imu
     * 3) eventi imu/battery aggiornano dataset e stato sensori
     * 4) {@link stop()} termina la campagna, close() chiude la UI
     */

    /**
     * Avvia il monitor live per una campagna.
     * Config attesa: { id, nome, sensori }.
     */
    function open(config) {
        cleanup();
        campaignId = config.id;
        campaignName = config.nome || 'Campagna in corso';
        sensorLocations = {};
        sensorList = (config.sensori || []).map(item => {
            const sensor = typeof item === 'string' ? item : item.codice;
            const normalized = String(sensor || '').toUpperCase();
            if (typeof item === 'object' && item && item.location) {
                sensorLocations[normalized] = String(item.location);
            }
            return normalized;
        }).filter(Boolean);
        Object.entries(config.sensorLocations || {}).forEach(([sensor, location]) => {
            sensorLocations[String(sensor).toUpperCase()] = String(location || '');
        });
        resetUI();
        initCharts();
        renderSensors();
        connectSse();

        if (chartUpdateTimer) clearInterval(chartUpdateTimer);
        chartUpdateTimer = setInterval(flushImuBuffer, CHART_UPDATE_INTERVAL);
        startStatusTimer();

        const modal = document.getElementById('liveMonitorModal');
        if (modal) {
            modal.showModal();
            if (!modal.dataset.boundClose) {
                modal.addEventListener('close', () => close(true));
                modal.dataset.boundClose = 'true';
            }
        }
    }

    /**
     * Termina la campagna tramite backend e chiude il monitor.
     */
    function stop() {
        if (!campaignId) return;
        fetch(`/api/v1/campagne/${campaignId}/termina`, {
            method: 'POST',
            credentials: 'same-origin'
        })
            .then(async res => {
                if (!res.ok) {
                    const data = await res.json().catch(() => null);
                    throw new Error(data && data.message ? data.message : 'Errore terminazione');
                }
                if (typeof showSuccess === 'function') {
                    showSuccess('Campagna terminata con successo!');
                }
                if (window.htmx) {
                    htmx.ajax('GET', '/fragments/campagne/home', {
                        target: '#campagneTableBody',
                        swap: 'innerHTML'
                    });
                }
                close(false);
            })
            .catch(err => {
                alert(err.message || 'Errore terminazione');
            });
    }

    /**
     * Chiude il monitor senza terminare la campagna.
     * @param {boolean} fromModal true se la chiusura arriva dal dialog stesso.
     */
    function close(fromModal) {
        cleanup();
        if (!fromModal) {
            const modal = document.getElementById('liveMonitorModal');
            if (modal && modal.open) modal.close();
        }
    }

    /**
     * Ripulisce risorse e stato: SSE, grafici, cache sensori.
     */
    function cleanup() {
        stopStatusTimer();
        if (chartUpdateTimer) {
            clearInterval(chartUpdateTimer);
            chartUpdateTimer = null;
        }
        imuBuffer.length = 0;
        dirtyCharts.clear();
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        destroyAllCharts();
        Object.keys(datasets).forEach(key => delete datasets[key]);
        Object.keys(battery).forEach(key => delete battery[key]);
        Object.keys(lastSeen).forEach(key => delete lastSeen[key]);
        Object.keys(imuHistory).forEach(key => delete imuHistory[key]);
        Object.keys(applicationOutputs).forEach(key => delete applicationOutputs[key]);
        campaignId = null;
        campaignName = null;
        sensorList = [];
        sensorLocations = {};
        currentLayout = 'axis';

        const container = document.getElementById('liveSensorChartsContainer');
        if (container) container.innerHTML = '';
        renderApplicationOutputs();
    }

    /**
     * Connette l'SSE e registra i listener per eventi imu/battery.
     */
    function connectSse() {
        const params = new URLSearchParams();
        if (sensorList.length > 0) {
            params.set('imuid', sensorList.join(','));
        }
        if (campaignId) {
            params.set('campaignId', String(campaignId));
        }
        const url = params.toString() ? `/sse/imu?${params}` : '/sse/imu';
        eventSource = new EventSource(url);

        eventSource.addEventListener('imu', (event) => {
            const payload = JSON.parse(event.data);
            handleImu(payload);
        });
        eventSource.addEventListener('battery', (event) => {
            const payload = JSON.parse(event.data);
            handleBattery(payload);
        });
        eventSource.addEventListener('application-data', (event) => {
            const payload = JSON.parse(event.data);
            handleApplicationData(payload);
        });
        eventSource.onerror = () => {
            // ignored: reconnection is automatic
        };
    }

    /**
     * Aggiorna i grafici con i valori IMU ricevuti.
     */
    function handleImu(payload) {
        if (!payload || !payload.values) return;
        const sensor = (payload.imuid || '').toUpperCase();
        if (!sensor) return;
        let sensorAdded = false;
        if (!sensorList.includes(sensor)) {
            sensorList.push(sensor);
            sensorAdded = true;
            if (currentLayout === 'sensor') {
                createSensorChartsForSensor(sensor);
                replaySensorHistory(sensor);
            }
        }
        payload._ts = Date.now();
        appendImuHistory(sensor, payload);
        lastSeen[sensor] = payload._ts;
        imuBuffer.push(payload);
        if (sensorAdded) renderSensors();
    }

    /**
     * Aggiorna la batteria e lo stato dei sensori.
     */
    function handleBattery(payload) {
        if (!payload || !payload.values) return;
        const sensor = (payload.imuid || '').toUpperCase();
        if (!sensor) return;
        if (!sensorList.includes(sensor)) {
            sensorList.push(sensor);
            if (currentLayout === 'sensor') {
                createSensorChartsForSensor(sensor);
            }
        }
        battery[sensor] = payload.values.battery;
        lastSeen[sensor] = Date.now();
        renderSensors();
    }

    /**
     * Mantiene le ultime righe di ciascun topic senza esporre il topic nella UI.
     */
    function handleApplicationData(payload) {
        if (!payload || !payload.topic || !payload.values) return;
        const topic = String(payload.topic);
        const timestamp = parseEventTimestamp(payload.receivedAt);
        const stream = applicationOutputs[topic] || {
            columns: [],
            rows: []
        };
        Object.keys(payload.values).forEach(column => {
            if (!stream.columns.includes(column)) {
                stream.columns.push(column);
            }
        });
        stream.rows.push({
            timestamp,
            values: { ...payload.values }
        });
        stream.rows.sort((left, right) => right.timestamp - left.timestamp);
        if (stream.rows.length > OUTPUT_HISTORY_LIMIT) {
            stream.rows.length = OUTPUT_HISTORY_LIMIT;
        }
        applicationOutputs[topic] = stream;
        renderApplicationOutputs();
    }

    function parseEventTimestamp(value) {
        const timestamp = value ? Date.parse(value) : NaN;
        return Number.isFinite(timestamp) ? timestamp : Date.now();
    }

    function renderApplicationOutputs() {
        const section = document.getElementById('liveApplicationOutputSection');
        const container = document.getElementById('liveApplicationOutputTables');
        if (!section || !container) return;

        const topics = Object.keys(applicationOutputs);
        section.classList.toggle('hidden', topics.length === 0);
        container.innerHTML = '';

        topics.forEach(topic => {
            const stream = applicationOutputs[topic];
            const block = document.createElement('div');
            block.className = 'border border-base-300 bg-base-100';
            const headers = stream.columns
                .map(column => `<th class="whitespace-nowrap">${escapeHtml(column)}</th>`)
                .join('');
            const rows = stream.rows
                .map(row => {
                    const cells = stream.columns
                        .map(column => `<td class="whitespace-nowrap">${escapeHtml(formatOutputValue(row.values[column]))}</td>`)
                        .join('');
                    return `
                        <tr>
                            <td class="whitespace-nowrap">${escapeHtml(formatOutputTimestamp(row.timestamp))}</td>
                            ${cells}
                        </tr>
                    `;
                })
                .join('');
            block.innerHTML = `
                <div class="overflow-x-auto">
                    <table class="table table-sm">
                        <thead>
                            <tr class="text-base-content/60">
                                <th class="whitespace-nowrap">Ora</th>
                                ${headers}
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
            container.appendChild(block);
        });
    }

    function formatOutputTimestamp(timestamp) {
        return new Date(timestamp).toLocaleTimeString('it-IT', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    function formatOutputValue(value) {
        if (typeof value === 'number' && Number.isFinite(value)) {
            return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
        }
        return String(value == null ? '' : value);
    }

    function processPayloadForCharts(payload) {
        if (!payload || !payload.values) return;
        const sensor = (payload.imuid || '').toUpperCase();
        if (!sensor) return;

        if (currentLayout === 'sensor') {
            updateSensorGroup(sensor, 'acc', payload.values.ax, payload.values.ay, payload.values.az, payload._ts || Date.now());
            updateSensorGroup(sensor, 'gyro', payload.values.gx, payload.values.gy, payload.values.gz, payload._ts || Date.now());
            updateSensorGroup(sensor, 'magn', payload.values.mx, payload.values.my, payload.values.mz, payload._ts || Date.now());
            return;
        }

        updateAxis(sensor, 'ax', payload.values.ax, payload._ts || Date.now());
        updateAxis(sensor, 'ay', payload.values.ay, payload._ts || Date.now());
        updateAxis(sensor, 'az', payload.values.az, payload._ts || Date.now());
        updateAxis(sensor, 'gx', payload.values.gx, payload._ts || Date.now());
        updateAxis(sensor, 'gy', payload.values.gy, payload._ts || Date.now());
        updateAxis(sensor, 'gz', payload.values.gz, payload._ts || Date.now());
        updateAxis(sensor, 'mx', payload.values.mx, payload._ts || Date.now());
        updateAxis(sensor, 'my', payload.values.my, payload._ts || Date.now());
        updateAxis(sensor, 'mz', payload.values.mz, payload._ts || Date.now());
    }

    function appendImuHistory(sensor, payload) {
        if (!imuHistory[sensor]) imuHistory[sensor] = [];
        imuHistory[sensor].push({
            ts: payload._ts || Date.now(),
            values: {
                ax: payload.values.ax,
                ay: payload.values.ay,
                az: payload.values.az,
                gx: payload.values.gx,
                gy: payload.values.gy,
                gz: payload.values.gz,
                mx: payload.values.mx,
                my: payload.values.my,
                mz: payload.values.mz
            }
        });
        while (imuHistory[sensor].length > HISTORY_LIMIT) imuHistory[sensor].shift();
    }

    function updateAxis(sensor, axis, value, timestamp) {
        if (value === null || value === undefined) return;
        const chartKey = `chart-${axis}`;
        const chart = charts[chartKey];
        if (!chart) return;
        const dataset = ensureDataset(chartKey, sensor, {
            color: getColor(sensor),
            label: sensorHeading(sensor)
        });
        dataset.data.push({ x: timestamp, y: Number(value) });
        if (dataset.data.length > HISTORY_LIMIT) dataset.data.shift();
        dirtyCharts.add(chartKey);
    }

    function updateSensorGroup(sensor, group, x, y, z, timestamp) {
        const chartKey = getSensorChartKey(sensor, group);
        const chart = charts[chartKey];
        if (!chart) return;

        const dx = ensureDataset(chartKey, 'x', { color: getAxisColor('x'), label: 'X' });
        const dy = ensureDataset(chartKey, 'y', { color: getAxisColor('y'), label: 'Y' });
        const dz = ensureDataset(chartKey, 'z', { color: getAxisColor('z'), label: 'Z' });

        if (x !== null && x !== undefined) {
            dx.data.push({ x: timestamp, y: Number(x) });
            if (dx.data.length > HISTORY_LIMIT) dx.data.shift();
        }
        if (y !== null && y !== undefined) {
            dy.data.push({ x: timestamp, y: Number(y) });
            if (dy.data.length > HISTORY_LIMIT) dy.data.shift();
        }
        if (z !== null && z !== undefined) {
            dz.data.push({ x: timestamp, y: Number(z) });
            if (dz.data.length > HISTORY_LIMIT) dz.data.shift();
        }

        dirtyCharts.add(chartKey);
    }

    function ensureDataset(chartKey, seriesKey, options) {
        if (!datasets[chartKey]) datasets[chartKey] = {};
        if (!datasets[chartKey][seriesKey]) {
            const chart = charts[chartKey];
            if (!chart) return null;
            const dataset = {
                label: options.label,
                data: [],
                borderColor: options.color,
                backgroundColor: options.color,
                pointRadius: 0,
                pointHoverRadius: 0,
                pointHitRadius: 6,
                borderWidth: 1.5,
                tension: 0.25,
                fill: false
            };
            chart.data.datasets.push(dataset);
            datasets[chartKey][seriesKey] = dataset;
        }
        return datasets[chartKey][seriesKey];
    }

    /**
     * Assegna un colore stabile per sensore.
     */
    function getColor(sensor) {
        const index = sensorList.indexOf(sensor);
        if (index === -1) return palette[0];
        return palette[index % palette.length];
    }

    function getAxisColor(axis) {
        if (axis === 'x') return '#ef4444';
        if (axis === 'y') return '#22c55e';
        return '#3b82f6';
    }

    function getSensorChartKey(sensor, group) {
        return `chart-${sensor}-${group}`;
    }

    function getSensorCanvasId(sensor, group) {
        const safeSensor = sensor.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
        return `sensor-chart-${safeSensor}-${group}`;
    }

    function getSensorStatusBadgeId(sensor) {
        const safeSensor = sensor.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
        return `live-sensor-card-status-${safeSensor}`;
    }

    function sensorHeading(sensor) {
        const location = sensorLocations[sensor] || '';
        return location ? `${sensor} — ${location}` : sensor;
    }

    function escapeHtml(value) {
        const element = document.createElement('div');
        element.textContent = String(value == null ? '' : value);
        return element.innerHTML;
    }

    function initCharts() {
        destroyAllCharts();
        Object.keys(datasets).forEach(key => delete datasets[key]);

        if (currentLayout === 'sensor') {
            createSensorLayoutCharts();
            replayAllHistory();
            return;
        }

        createChart('chart-ax');
        createChart('chart-ay');
        createChart('chart-az');
        createChart('chart-gx');
        createChart('chart-gy');
        createChart('chart-gz');
        createChart('chart-mx');
        createChart('chart-my');
        createChart('chart-mz');

        replayAllHistory();
    }

    function destroyAllCharts() {
        Object.values(charts).forEach(chart => chart.destroy());
        Object.keys(charts).forEach(key => delete charts[key]);
        dirtyCharts.clear();
    }

    function createChart(canvasId, legendPosition = 'bottom') {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        const gridColor = 'rgba(30, 41, 59, 0.12)';
        const tickColor = 'rgba(30, 41, 59, 0.72)';
        charts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: { datasets: [] },
            options: {
                animation: false,
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'nearest', intersect: false },
                elements: {
                    line: { borderWidth: 1.5 },
                    point: { radius: 0, hitRadius: 6, hoverRadius: 0 }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: legendPosition,
                        labels: {
                            color: tickColor,
                            boxWidth: 10,
                            boxHeight: 10,
                            padding: 8,
                            usePointStyle: true,
                            pointStyle: 'line',
                            font: { size: 10 }
                        }
                    },
                    title: { display: false },
                    tooltip: { enabled: true }
                },
                scales: {
                    x: {
                        type: 'linear',
                        grid: { color: gridColor, drawBorder: false },
                        ticks: {
                            color: tickColor,
                            maxTicksLimit: 4,
                            autoSkip: true,
                            padding: 4,
                            callback: (value) => {
                                const d = new Date(value);
                                return d.toLocaleTimeString('it-IT', {
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    second: '2-digit'
                                });
                            },
                            font: { size: 10 }
                        }
                    },
                    y: {
                        beginAtZero: false,
                        grid: { color: gridColor, drawBorder: false },
                        ticks: {
                            color: tickColor,
                            maxTicksLimit: 4,
                            padding: 4,
                            callback: (value) => Math.round(value),
                            font: { size: 10 }
                        }
                    }
                }
            }
        });
    }

    function createSensorLayoutCharts() {
        const container = document.getElementById('liveSensorChartsContainer');
        if (!container) return;
        container.innerHTML = '';
        sensorList.forEach(sensor => createSensorChartsForSensor(sensor));
    }

    function createSensorChartsForSensor(sensor) {
        if (!sensor) return;
        const container = document.getElementById('liveSensorChartsContainer');
        if (!container) return;

        const safeSensor = sensor.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
        const sectionId = `sensor-section-${safeSensor}`;
        if (document.getElementById(sectionId)) return;
        const statusBadgeId = getSensorStatusBadgeId(sensor);

        const section = document.createElement('div');
        section.id = sectionId;
        section.className = 'card bg-base-200 border border-base-300';
        section.innerHTML = `
            <div class="card-body gap-4">
                <div class="flex items-center justify-between">
                    <h4 class="font-semibold uppercase tracking-widest text-xs text-base-content/70">${escapeHtml(sensorHeading(sensor))}</h4>
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-base-content/50 uppercase tracking-widest">IMU</span>
                        <span id="${statusBadgeId}" class="badge badge-sm">--</span>
                    </div>
                </div>
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    ${sensorGroupBlock(sensor, 'acc', 'Accelerazione', 'M/S^2')}
                    ${sensorGroupBlock(sensor, 'magn', 'Magnetometro', 'uT')}
                    ${sensorGroupBlock(sensor, 'gyro', 'Giroscopio', 'DEG/S')}
                </div>
            </div>
        `;
        container.appendChild(section);

        createChart(getSensorCanvasId(sensor, 'acc'), 'bottom');
        createChart(getSensorCanvasId(sensor, 'magn'), 'bottom');
        createChart(getSensorCanvasId(sensor, 'gyro'), 'bottom');

        charts[getSensorChartKey(sensor, 'acc')] = charts[getSensorCanvasId(sensor, 'acc')];
        charts[getSensorChartKey(sensor, 'magn')] = charts[getSensorCanvasId(sensor, 'magn')];
        charts[getSensorChartKey(sensor, 'gyro')] = charts[getSensorCanvasId(sensor, 'gyro')];

        delete charts[getSensorCanvasId(sensor, 'acc')];
        delete charts[getSensorCanvasId(sensor, 'magn')];
        delete charts[getSensorCanvasId(sensor, 'gyro')];
    }

    function sensorGroupBlock(sensor, group, title, unit) {
        const canvasId = getSensorCanvasId(sensor, group);
        return `
            <div class="rounded-xl border border-base-300 bg-base-100 p-3">
                <div class="flex items-center justify-between mb-2">
                    <div class="text-xs uppercase tracking-widest text-base-content/60">${title}</div>
                    <div class="text-[10px] uppercase tracking-widest text-base-content/50">${unit}</div>
                </div>
                <div class="mb-2 text-[10px] uppercase tracking-widest text-base-content/50">
                    Assi: <span class="text-red-400">X</span> / <span class="text-green-400">Y</span> / <span class="text-blue-400">Z</span>
                </div>
                <div class="h-36">
                    <canvas id="${canvasId}" class="w-full h-full"></canvas>
                </div>
            </div>
        `;
    }

    function replayAllHistory() {
        sensorList.forEach(sensor => replaySensorHistory(sensor));
        for (const chartKey of Object.keys(charts)) {
            const chart = charts[chartKey];
            if (chart) chart.update('none');
        }
    }

    function replaySensorHistory(sensor) {
        const history = imuHistory[sensor] || [];
        for (const row of history) {
            const payload = {
                imuid: sensor,
                _ts: row.ts,
                values: row.values
            };
            processPayloadForCharts(payload);
        }
    }

    function switchLayout(layout) {
        const nextLayout = layout === 'sensor' ? 'sensor' : 'axis';
        if (currentLayout === nextLayout) return;
        currentLayout = nextLayout;
        applyLayoutVisibility();
        initCharts();
    }

    function applyLayoutVisibility() {
        const axisView = document.getElementById('liveChartsAxisView');
        const sensorView = document.getElementById('liveChartsSensorView');
        if (axisView) axisView.classList.toggle('hidden', currentLayout !== 'axis');
        if (sensorView) sensorView.classList.toggle('hidden', currentLayout !== 'sensor');
    }

    /**
     * Renderizza la lista sensori e i relativi stati/batteria.
     */
    function renderSensors() {
        const list = document.getElementById('liveSensorList');
        const batteryList = document.getElementById('liveBatteryList');
        if (!list || !batteryList) return;
        list.innerHTML = '';
        batteryList.innerHTML = '';

        sensorList.forEach(sensor => {
            const color = getColor(sensor);
            const seenAt = lastSeen[sensor];
            const isActive = seenAt && (Date.now() - seenAt) < SENSOR_INACTIVE_THRESHOLD_MS;

            const row = document.createElement('div');
            row.className = 'flex items-center gap-2';
            row.innerHTML = `
                <span class="inline-block w-2 h-2 rounded-full" style="background:${color}"></span>
                <span><span class="font-mono">${escapeHtml(sensor)}</span>${sensorLocations[sensor] ? ` <span class="text-gray-400">— ${escapeHtml(sensorLocations[sensor])}</span>` : ''}</span>
                <span class="text-xs ${isActive ? 'text-green-600' : 'text-gray-400'}">
                    ${isActive ? 'attivo' : 'inattivo'}
                </span>
            `;
            list.appendChild(row);

            const batteryRow = document.createElement('div');
            batteryRow.className = 'flex items-center justify-between gap-2 bg-base-100 rounded px-3 py-2';
            const value = battery[sensor] !== undefined ? battery[sensor] : 'N/A';
            batteryRow.innerHTML = `
                <span><span class="font-mono">${escapeHtml(sensor)}</span>${sensorLocations[sensor] ? ` <span class="text-gray-400">— ${escapeHtml(sensorLocations[sensor])}</span>` : ''}</span>
                <span class="font-semibold">${value}</span>
            `;
            batteryList.appendChild(batteryRow);

            const statusBadge = document.getElementById(getSensorStatusBadgeId(sensor));
            if (statusBadge) {
                statusBadge.textContent = isActive ? 'attivo' : 'inattivo';
                statusBadge.className = isActive
                    ? 'badge badge-sm badge-success'
                    : 'badge badge-sm badge-ghost';
            }
        });
    }

    /**
     * Aggiorna testo e stato iniziale del monitor.
     */
    function resetUI() {
        const name = document.getElementById('liveCampaignName');
        const meta = document.getElementById('liveCampaignMeta');
        const layoutSelect = document.getElementById('liveChartLayoutSelect');
        if (name) name.textContent = campaignName;
        if (meta) meta.textContent = 'Monitoraggio in tempo reale';
        if (layoutSelect) {
            layoutSelect.value = currentLayout;
            if (!layoutSelect.dataset.boundChange) {
                layoutSelect.addEventListener('change', (event) => {
                    switchLayout(event.target.value);
                });
                layoutSelect.dataset.boundChange = 'true';
            }
        }
        applyLayoutVisibility();
        renderSensors();
    }

    let statusTimer = null;
    /**
     * Avvia il timer per aggiornare lo stato attivo/inattivo dei sensori.
     */
    function startStatusTimer() {
        stopStatusTimer();
        statusTimer = setInterval(() => renderSensors(), 1000);
    }

    /**
     * Ferma il timer di aggiornamento stato sensori.
     */
    function stopStatusTimer() {
        if (statusTimer) {
            clearInterval(statusTimer);
            statusTimer = null;
        }
    }

    /**
     * Apre il monitor live a partire dai data-attribute del bottone.
     */
    async function openFromButton(button) {
        if (!button) return;
        const id = Number(button.dataset.id);
        const nome = button.dataset.nome || '';
        const sensori = button.dataset.sensors ? button.dataset.sensors.split(',') : [];
        try {
            const response = await fetch(`/api/v1/campagne/${id}`, {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin'
            });
            if (!response.ok) throw new Error();
            const data = await response.json();
            open({ id, nome: data.nome || nome, sensori: data.sensori || sensori });
        } catch (_) {
            open({ id, nome, sensori });
        }
    }

    /**
     * Apre il monitor live partendo dalla risposta JSON di avvio campagna.
     */
    function openFromResponse(xhr) {
        if (!xhr || !xhr.responseText) return;
        try {
            const data = JSON.parse(xhr.responseText);
            if (!data || !data.id) return;
            const sensori = Array.isArray(data.sensori) ? data.sensori : [];
            open({ id: data.id, nome: data.nome, sensori });
        } catch (_) {
            // ignore
        }
    }

    return { open, openFromButton, openFromResponse, stop, close };
})();
