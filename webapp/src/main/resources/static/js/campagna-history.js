/**
 * Storico campagna (grafici da InfluxDB).
 * Flow:
 * 1) init() legge id campagna e tempi, configura grafici e slider.
 * 2) loadData() chiama /api/v1/campagne/{id}/dati con filtri e limit.
 * 3) renderData() distribuisce i punti nei dataset Chart.js per asse/sensore.
 * 4) lo slider "Tempo" ricarica i dati da un offset in secondi.
 */
window.BSNHistory = (() => {
    const palette = [
        '#e11d48', '#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6', '#f97316',
        '#14b8a6', '#22c55e', '#ef4444', '#3b82f6', '#a855f7', '#84cc16'
    ];

    const axes = ['ax', 'ay', 'az', 'gx', 'gy', 'gz', 'mx', 'my', 'mz'];
    const charts = {};
    const datasets = {};
    let campaignId = null;
    let sensorList = [];
    const sensorLocations = {};
    let currentLayout = 'axis';
    let startTimestampMs = null;
    let useElapsedTime = false;
    let endTimestampMs = null;
    let sliderTimer = null;

    /**
     * Avvia lo storico: prepara dati base, grafici e bindings UI.
     */
    function init() {
        const root = document.getElementById('campaignHistoryRoot');
        if (!root) return;
        campaignId = Number(root.dataset.campaignId);
        if (root.dataset.startTime) {
            const parsed = Date.parse(root.dataset.startTime);
            if (!Number.isNaN(parsed)) {
                startTimestampMs = parsed;
                useElapsedTime = true;
            }
        }
        if (root.dataset.endTime) {
            const parsedEnd = Date.parse(root.dataset.endTime);
            if (!Number.isNaN(parsedEnd)) {
                endTimestampMs = parsedEnd;
            }
        }
        moveFiltersBelowBreathAnalysisOutput();
        const layoutSelect = document.getElementById('historyChartLayoutSelect');
        if (layoutSelect && (layoutSelect.value === 'axis' || layoutSelect.value === 'sensor')) {
            currentLayout = layoutSelect.value;
        }
        sensorList = Array.from(document.querySelectorAll('#historySensorList [data-sensor]'))
            .map(el => {
                const sensor = el.dataset.sensor.toUpperCase();
                sensorLocations[sensor] = el.dataset.location || '';
                return sensor;
            });
        applySensorColors();
        applyLayoutVisibility();
        initCharts();
        bindControls();
        setupTimeSlider();
        loadData();
        loadBreathAnalysisData();
    }

    /**
     * Nelle campagne BreathAnalysis colloca i filtri dopo la tabella degli output.
     * Un segnaposto conserva l'allineamento delle altre schede nel riepilogo.
     */
    function moveFiltersBelowBreathAnalysisOutput() {
        const filters = document.getElementById('historyFiltersCard');
        const slot = document.getElementById('breathAnalysisFiltersSlot');
        if (!filters || !slot || !filters.parentElement) return;

        const placeholder = document.createElement('div');
        placeholder.className = 'hidden lg:block lg:col-span-2';
        filters.parentElement.insertBefore(placeholder, filters);
        filters.classList.remove('lg:col-span-2');
        slot.appendChild(filters);
    }

    /**
     * Collega i controlli di refresh manuale.
     */
    function bindControls() {
        const refresh = document.getElementById('historyRefresh');
        if (refresh) {
            refresh.addEventListener('click', (event) => {
                event.preventDefault();
                loadData();
                loadBreathAnalysisData();
            });
        }
        const outputDownload = document.getElementById('historyOutputDownload');
        if (outputDownload) {
            outputDownload.addEventListener('click', () => downloadApplicationOutputs(outputDownload));
        }
        const imuDownload = document.getElementById('historyImuDownload');
        if (imuDownload) {
            imuDownload.addEventListener('click', () => downloadImuData(imuDownload));
        }
        const dbSelect = document.getElementById('historyDbSelect');
        if (dbSelect) {
            dbSelect.addEventListener('change', () => {
                loadData();
            });
        }
        const layoutSelect = document.getElementById('historyChartLayoutSelect');
        if (layoutSelect) {
            layoutSelect.addEventListener('change', () => {
                currentLayout = layoutSelect.value === 'sensor' ? 'sensor' : 'axis';
                applyLayoutVisibility();
                initCharts();
                loadData();
            });
        }
    }

    async function downloadApplicationOutputs(button) {
        await downloadCampaignFile(
            button,
            `/api/v1/campagne/${campaignId}/output/export`,
            `campagna_${campaignId}_output.zip`,
            'Errore durante il download degli output'
        );
    }

    async function downloadImuData(button) {
        await downloadCampaignFile(
            button,
            `/api/v1/campagne/${campaignId}/imu/export`,
            `campagna_${campaignId}_imu.csv`,
            'Errore durante il download dei dati IMU'
        );
    }

    async function downloadCampaignFile(button, url, fileName, errorMessage) {
        if (!campaignId || !button || button.disabled) return;
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = 'Preparazione...';

        try {
            const response = await fetch(url, {
                credentials: 'same-origin'
            });
            if (!response.ok) {
                const error = await response.json().catch(() => null);
                throw new Error(error && error.message ? error.message : 'Esportazione non disponibile');
            }

            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = objectUrl;
            link.download = fileName;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        } catch (error) {
            alert(error.message || errorMessage);
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    /**
     * Inizializza lo slider temporale in secondi dall'avvio campagna.
     * Se non ci sono tempi validi, il controllo viene disabilitato.
     */
    function setupTimeSlider() {
        const slider = document.getElementById('historyTimeRange');
        const label = document.getElementById('historyTimeLabel');
        if (!slider || !label) return;

        const maxSeconds = resolveDurationSeconds();
        slider.max = String(Math.max(0, Math.floor(maxSeconds)));
        slider.value = String(Math.min(Number(slider.value) || 0, Number(slider.max)));
        label.textContent = formatElapsed(slider.value);

        if (!useElapsedTime || Number(slider.max) === 0) {
            slider.disabled = true;
            return;
        }

        slider.addEventListener('input', () => {
            label.textContent = formatElapsed(slider.value);
            if (sliderTimer) {
                clearTimeout(sliderTimer);
            }
            sliderTimer = setTimeout(() => {
                loadData();
            }, 300);
        });
        slider.addEventListener('change', loadData);
    }

    /**
     * Calcola la durata in secondi per definire il massimo dello slider.
     */
    function resolveDurationSeconds() {
        if (startTimestampMs === null) return 0;
        if (endTimestampMs !== null) {
            return Math.max(0, Math.floor((endTimestampMs - startTimestampMs) / 1000));
        }
        return Math.max(0, Math.floor((Date.now() - startTimestampMs) / 1000));
    }

    /**
     * Applica colori coerenti tra lista sensori e dataset dei grafici.
     */
    function applySensorColors() {
        const items = document.querySelectorAll('#historySensorList [data-sensor]');
        items.forEach((item, index) => {
            const dot = item.querySelector('span');
            if (dot) {
                dot.style.background = palette[index % palette.length];
            }
        });
    }

    /**
     * Carica i dati da InfluxDB con filtri (sensori, limit, fromSeconds).
     */
    function loadData() {
        if (!campaignId) return;
        const sensorChecks = document.querySelectorAll('input[name="historySensors"]:checked');
        const limitInput = document.getElementById('historyLimit');
        const slider = document.getElementById('historyTimeRange');
        const params = new URLSearchParams();
        params.set('measurement', 'campaign');
        const dbSelect = document.getElementById('historyDbSelect');
        if (dbSelect && dbSelect.value) {
            params.set('dbId', dbSelect.value);
        }
        if (sensorChecks.length > 0) {
            const sensors = Array.from(sensorChecks)
                .map(input => input.value)
                .filter(Boolean);
            if (sensors.length > 0) {
                params.set('imuid', sensors.join(','));
            }
        }
        if (limitInput && limitInput.value) {
            params.set('limit', limitInput.value);
        }
        if (slider && !slider.disabled && slider.value) {
            params.set('fromSeconds', slider.value);
        }
        const url = `/api/v1/campagne/${campaignId}/dati?${params.toString()}`;
        setMessage('Caricamento dati...');

        fetch(url)
            .then(async res => {
                if (!res.ok) {
                    const data = await res.json().catch(() => null);
                    throw new Error(data && data.message ? data.message : 'Errore lettura dati');
                }
                return res.json();
            })
            .then(renderData)
            .catch(err => {
                clearCharts();
                setMessage(err.message || 'Errore lettura dati');
            });
    }

    /**
     * Popola i grafici a partire dalle colonne/righe Influx.
     */
    function renderData(data) {
        clearCharts();
        if (!data || !Array.isArray(data.values) || data.values.length === 0) {
            setMessage('Nessun dato disponibile per la campagna.');
            return;
        }
        setMessage('');

        const columns = data.columns || [];
        const idx = {};
        columns.forEach((col, i) => { idx[col] = i; });

        const rows = [];
        const sensorOrder = [];
        const seenSensors = new Set();

        data.values.forEach(row => {
            const imuid = normalizeValue(row[idx.imuid]);
            const timeValue = normalizeValue(row[idx.time]);
            const timestamp = Date.parse(timeValue);
            if (!imuid || Number.isNaN(timestamp)) return;

            const sensor = String(imuid).toUpperCase();
            if (!seenSensors.has(sensor)) {
                seenSensors.add(sensor);
                sensorOrder.push(sensor);
            }

            const xValue = useElapsedTime && startTimestampMs !== null
                ? Math.max(0, (timestamp - startTimestampMs) / 1000)
                : timestamp;

            const values = {};
            axes.forEach(axis => {
                const colIndex = idx[axis];
                if (colIndex === undefined) {
                    values[axis] = null;
                    return;
                }
                const value = normalizeValue(row[colIndex]);
                values[axis] = value;
            });

            rows.push({ sensor, xValue, values });
        });

        if (rows.length === 0) {
            setMessage('Nessun dato disponibile per la campagna.');
            return;
        }

        if (currentLayout === 'sensor') {
            syncSensorCharts(sensorOrder);
        }

        rows.forEach(({ sensor, xValue, values }) => {
            if (currentLayout === 'sensor') {
                pushSensorGroupPoint(sensor, 'acc', xValue, values.ax, values.ay, values.az);
                pushSensorGroupPoint(sensor, 'gyro', xValue, values.gx, values.gy, values.gz);
                pushSensorGroupPoint(sensor, 'magn', xValue, values.mx, values.my, values.mz);
                return;
            }

            axes.forEach(axis => {
                const value = values[axis];
                if (value === null || value === undefined) return;
                const chartKey = `history-${axis}`;
                const dataset = ensureDataset(chartKey, sensor, {
                    label: sensorHeading(sensor),
                    color: getColor(sensor)
                });
                if (!dataset) return;
                dataset.data.push({ x: xValue, y: Number(value) });
            });
        });

        Object.values(charts).forEach(chart => {
            chart.data.datasets.forEach(ds => ds.data.sort((a, b) => a.x - b.x));
            chart.update('none');
        });
    }

    /**
     * Carica gli output applicativi dalle measurement campaign_<id>_<cname>.
     * La sezione esiste soltanto per le campagne BreathAnalysis.
     */
    async function loadBreathAnalysisData() {
        const container = document.getElementById('breathAnalysisOutput');
        if (!container || !campaignId) return;

        const message = document.getElementById('breathAnalysisMessage');
        const wrapper = document.getElementById('breathAnalysisTableWrapper');
        const limitInput = document.getElementById('historyLimit');
        const params = new URLSearchParams();
        if (limitInput && limitInput.value) {
            params.set('limit', limitInput.value);
        }

        if (message) message.textContent = 'Caricamento dati...';
        if (wrapper) wrapper.classList.add('hidden');

        try {
            const response = await fetch(
                `/api/v1/campagne/${campaignId}/output/dati?${params.toString()}`,
                { credentials: 'same-origin' }
            );
            if (!response.ok) {
                const error = await response.json().catch(() => null);
                throw new Error(error && error.message ? error.message : 'Errore lettura risultati');
            }
            renderBreathAnalysisTable(await response.json());
        } catch (error) {
            if (message) {
                message.textContent = error.message || 'Errore durante la lettura dei risultati.';
            }
        }
    }

    function renderBreathAnalysisTable(data) {
        const message = document.getElementById('breathAnalysisMessage');
        const wrapper = document.getElementById('breathAnalysisTableWrapper');
        const head = document.getElementById('breathAnalysisTableHead');
        const body = document.getElementById('breathAnalysisTableBody');
        if (!message || !wrapper || !head || !body) return;

        const series = data && Array.isArray(data.series) ? data.series : [];
        const rows = [];
        const preferredColumns = [];
        const discoveredColumns = new Set();
        const hiddenColumns = new Set([
            '_field_order', 'topic', 'c_id', 'cname', 'imuid', 'event_type'
        ]);

        series.forEach(item => {
            const columns = Array.isArray(item.columns) ? item.columns : [];
            const fieldOrderIndex = columns.indexOf('_field_order');
            (Array.isArray(item.values) ? item.values : []).forEach(values => {
                if (fieldOrderIndex >= 0 && values[fieldOrderIndex]) {
                    String(values[fieldOrderIndex]).split(',').forEach(column => {
                        const value = column.trim();
                        if (value && !hiddenColumns.has(value) && !preferredColumns.includes(value)) {
                            preferredColumns.push(value);
                        }
                    });
                }

                const row = { measurement: item.measurement || '', values: {} };
                columns.forEach((column, index) => {
                    if (hiddenColumns.has(column)) return;
                    discoveredColumns.add(column);
                    row.values[column] = values[index];
                });
                rows.push(row);
            });
        });

        if (rows.length === 0) {
            head.replaceChildren();
            body.replaceChildren();
            wrapper.classList.add('hidden');
            message.textContent = 'Nessun risultato BreathAnalysis disponibile.';
            return;
        }

        const columns = [];
        if (discoveredColumns.has('time')) columns.push('time');
        preferredColumns.forEach(column => {
            if (discoveredColumns.has(column) && !columns.includes(column)) columns.push(column);
        });
        discoveredColumns.forEach(column => {
            if (!columns.includes(column)) columns.push(column);
        });

        rows.sort((left, right) => {
            const leftTime = Date.parse(left.values.time);
            const rightTime = Date.parse(right.values.time);
            return (Number.isNaN(leftTime) ? 0 : leftTime) - (Number.isNaN(rightTime) ? 0 : rightTime);
        });

        const headerRow = document.createElement('tr');
        if (series.length > 1) {
            headerRow.appendChild(createTableCell('th', 'Measurement'));
        }
        columns.forEach(column => {
            headerRow.appendChild(createTableCell('th', column === 'time' ? 'Data e ora' : column));
        });
        head.replaceChildren(headerRow);

        const fragment = document.createDocumentFragment();
        rows.forEach(row => {
            const tableRow = document.createElement('tr');
            if (series.length > 1) {
                tableRow.appendChild(createTableCell('td', row.measurement));
            }
            columns.forEach(column => {
                const value = column === 'time'
                    ? formatTableTimestamp(row.values[column])
                    : formatBreathTableValue(row.values[column]);
                tableRow.appendChild(createTableCell('td', value));
            });
            fragment.appendChild(tableRow);
        });
        body.replaceChildren(fragment);
        message.textContent = `${rows.length} risultati trovati.`;
        wrapper.classList.remove('hidden');
    }

    function createTableCell(tagName, value) {
        const cell = document.createElement(tagName);
        cell.textContent = value === null || value === undefined ? '-' : String(value);
        return cell;
    }

    function formatTableTimestamp(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString('it-IT');
    }

    function formatBreathTableValue(value) {
        if (value === null || value === undefined || value === '') return value;
        const number = Number(value);
        if (!Number.isFinite(number) || Number.isInteger(number)) return value;
        return number.toFixed(2);
    }

    /**
     * Normalizza i valori Influx per evitare stringhe con spazi o null.
     */
    function normalizeValue(value) {
        if (value === null || value === undefined) return null;
        if (typeof value === 'string') return value.trim();
        return value;
    }

    /**
     * Svuota i dataset dei grafici mantenendo la configurazione.
     */
    function clearCharts() {
        Object.values(charts).forEach(chart => {
            chart.data.datasets = [];
            chart.update('none');
        });
        Object.keys(datasets).forEach(key => delete datasets[key]);
    }

    /**
     * Mostra un messaggio informativo (se il box e' presente).
     */
    function setMessage(text) {
        const msg = document.getElementById('historyMessage');
        if (msg) {
            msg.textContent = text;
        }
    }

    /**
     * Restituisce (o crea) il dataset per un sensore e un asse.
     */
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
        const index = sensorList.indexOf(sensor.toUpperCase());
        if (index === -1) {
            sensorList.push(sensor.toUpperCase());
            return palette[(sensorList.length - 1) % palette.length];
        }
        return palette[index % palette.length];
    }

    /**
     * Crea i grafici Chart.js per ciascun asse.
     */
    function initCharts() {
        destroyAllCharts();
        Object.keys(datasets).forEach(key => delete datasets[key]);

        if (currentLayout === 'sensor') {
            syncSensorCharts(getSelectedSensors());
            return;
        }

        axes.forEach(axis => createChart(`history-${axis}`));
    }

    function destroyAllCharts() {
        Object.values(charts).forEach(chart => chart.destroy());
        Object.keys(charts).forEach(key => delete charts[key]);
    }

    function applyLayoutVisibility() {
        const axisView = document.getElementById('historyChartsAxisView');
        const sensorView = document.getElementById('historyChartsSensorView');
        if (axisView) axisView.classList.toggle('hidden', currentLayout !== 'axis');
        if (sensorView) sensorView.classList.toggle('hidden', currentLayout !== 'sensor');
    }

    function getSelectedSensors() {
        const sensorChecks = document.querySelectorAll('input[name="historySensors"]:checked');
        const sensors = Array.from(sensorChecks)
            .map(input => normalizeValue(input.value))
            .filter(Boolean)
            .map(value => String(value).toUpperCase());
        return sensors.length > 0 ? sensors : sensorList;
    }

    function getAxisColor(axis) {
        if (axis === 'x') return '#ef4444';
        if (axis === 'y') return '#22c55e';
        return '#3b82f6';
    }

    function getSensorCanvasId(sensor, group) {
        const safeSensor = sensor.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
        return `history-sensor-chart-${safeSensor}-${group}`;
    }

    function getSensorChartKey(sensor, group) {
        return `history-chart-${sensor}-${group}`;
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

    function syncSensorCharts(sensors) {
        const container = document.getElementById('historySensorChartsContainer');
        if (!container) return;

        destroyAllCharts();
        Object.keys(datasets).forEach(key => delete datasets[key]);
        container.innerHTML = '';

        sensors.forEach(sensor => {
            const normalized = String(sensor).toUpperCase();
            const section = document.createElement('div');
            section.className = 'card bg-neutral/70 border border-neutral-content/10';
            section.innerHTML = `
                <div class="card-body gap-4">
                    <div class="flex items-center justify-between">
                        <h4 class="font-semibold uppercase tracking-widest text-xs text-neutral-content/70">${escapeHtml(sensorHeading(normalized))}</h4>
                        <div class="text-xs text-neutral-content/40 uppercase tracking-widest">IMU</div>
                    </div>
                    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        ${sensorGroupBlock(normalized, 'acc', 'Accelerazione', 'm/s^2')}
                        ${sensorGroupBlock(normalized, 'magn', 'Magnetometro', 'uT')}
                        ${sensorGroupBlock(normalized, 'gyro', 'Giroscopio', 'deg/s')}
                    </div>
                </div>
            `;
            container.appendChild(section);

            createSensorChart(normalized, 'acc');
            createSensorChart(normalized, 'magn');
            createSensorChart(normalized, 'gyro');
        });
    }

    function sensorGroupBlock(sensor, group, title, unit) {
        const canvasId = getSensorCanvasId(sensor, group);
        return `
            <div class="rounded-xl border border-neutral-content/10 bg-neutral/90 p-3">
                <div class="flex items-center justify-between mb-2">
                    <div class="text-xs uppercase tracking-widest text-neutral-content/50">${title}</div>
                    <div class="text-[10px] uppercase tracking-widest text-neutral-content/40">${unit}</div>
                </div>
                <div class="mb-2 text-[10px] uppercase tracking-widest text-neutral-content/40">
                    Assi: <span class="text-red-400">X</span> / <span class="text-green-400">Y</span> / <span class="text-blue-400">Z</span>
                </div>
                <div class="h-36">
                    <canvas id="${canvasId}" class="w-full h-full"></canvas>
                </div>
            </div>
        `;
    }

    function createSensorChart(sensor, group) {
        const canvasId = getSensorCanvasId(sensor, group);
        createChart(canvasId);
        const chart = charts[canvasId];
        if (!chart) return;
        const chartKey = getSensorChartKey(sensor, group);
        charts[chartKey] = chart;
        delete charts[canvasId];
    }

    function pushSensorGroupPoint(sensor, group, xValue, x, y, z) {
        const chartKey = getSensorChartKey(sensor, group);
        const chart = charts[chartKey];
        if (!chart) return;

        const dx = ensureDataset(chartKey, 'x', { label: 'X', color: getAxisColor('x') });
        const dy = ensureDataset(chartKey, 'y', { label: 'Y', color: getAxisColor('y') });
        const dz = ensureDataset(chartKey, 'z', { label: 'Z', color: getAxisColor('z') });

        if (x !== null && x !== undefined && dx) dx.data.push({ x: xValue, y: Number(x) });
        if (y !== null && y !== undefined && dy) dy.data.push({ x: xValue, y: Number(y) });
        if (z !== null && z !== undefined && dz) dz.data.push({ x: xValue, y: Number(z) });
    }

    /**
     * Inizializza un singolo grafico con stile compatto.
     */
    function createChart(canvasId) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        const gridColor = 'rgba(255, 255, 255, 0.08)';
        const tickColor = 'rgba(255, 255, 255, 0.55)';
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
                        position: 'bottom',
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
                                if (useElapsedTime) {
                                    return formatElapsed(value);
                                }
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

    /**
     * Formatta un tempo in secondi nel formato mm:ss o hh:mm:ss.
     */
    function formatElapsed(seconds) {
        const totalSeconds = Math.max(0, Math.floor(seconds));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const secs = totalSeconds % 60;
        if (hours > 0) {
            return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        }
        return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    return { init };
})();

document.addEventListener('DOMContentLoaded', () => {
    window.BSNHistory.init();
});
