// ============================================
// DASHBOARD PAGE JAVASCRIPT
// ============================================

document.addEventListener('DOMContentLoaded', function () {

    // ─── State ────────────────────────────────────────────
    let currentDeviceUid = null;

    // Active range: either { hours } or { from, to } ISO strings
    let activeRange = { hours: 1 };

    // ─── Initialise datetime pickers to sensible defaults ─
    function setDefaultDatetimeInputs() {
        const now = new Date();
        const yesterday = new Date(now - 24 * 60 * 60 * 1000);
        document.getElementById('rangeTo').value   = toLocalDatetimeInput(now);
        document.getElementById('rangeFrom').value = toLocalDatetimeInput(yesterday);
    }

    /** Convert a Date to the value format needed by datetime-local inputs */
    function toLocalDatetimeInput(date) {
        const pad = n => String(n).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    setDefaultDatetimeInputs();

    // ─── Preset buttons ───────────────────────────────────
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const hours = parseInt(btn.dataset.hours, 10);
            activeRange = { hours };

            // Update the "to" field to now and "from" to hours ago
            const now = new Date();
            const from = new Date(now - hours * 60 * 60 * 1000);
            document.getElementById('rangeTo').value   = toLocalDatetimeInput(now);
            document.getElementById('rangeFrom').value = toLocalDatetimeInput(from);

            updateActiveLabel();
            if (currentDeviceUid) loadHistory(currentDeviceUid);
        });
    });

    // ─── Apply custom range ───────────────────────────────
    document.getElementById('applyRangeBtn').addEventListener('click', () => {
        const fromVal = document.getElementById('rangeFrom').value;
        const toVal   = document.getElementById('rangeTo').value;

        if (!fromVal || !toVal) {
            alert('Please select both a From and To date/time.');
            return;
        }

        const fromDate = new Date(fromVal);
        const toDate   = new Date(toVal);

        if (fromDate >= toDate) {
            alert('"From" must be earlier than "To".');
            return;
        }

        // Deactivate preset buttons
        document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));

        activeRange = {
            from: fromDate.toISOString(),
            to:   toDate.toISOString()
        };

        updateActiveLabel();
        if (currentDeviceUid) loadHistory(currentDeviceUid);
    });

    // ─── Active range label ───────────────────────────────
    function updateActiveLabel() {
        const el = document.getElementById('activeRangeLabel');
        if (activeRange.hours) {
            const labels = { 1:'1 hour', 2:'2 hours', 6:'6 hours', 12:'12 hours',
                             24:'24 hours', 48:'48 hours', 168:'7 days', 720:'30 days' };
            el.innerHTML = `Showing: <strong>${labels[activeRange.hours] || activeRange.hours + 'h'}</strong>`;
        } else {
            const fmtOpts = { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' };
            const fromStr = new Date(activeRange.from).toLocaleString([], fmtOpts);
            const toStr   = new Date(activeRange.to).toLocaleString([], fmtOpts);
            el.innerHTML = `Showing: <strong>${fromStr}</strong> → <strong>${toStr}</strong>`;
        }
    }

    // ─── Build history API URL ────────────────────────────
    function buildHistoryUrl(deviceUid) {
        if (activeRange.hours) {
            return `/api/history/${deviceUid}?hours=${activeRange.hours}`;
        }
        // Custom range → calculate hours (the API only accepts hours)
        const fromDate = new Date(activeRange.from);
        const toDate   = new Date(activeRange.to);
        const hours    = Math.ceil((toDate - fromDate) / (1000 * 60 * 60));
        return `/api/history/${deviceUid}?hours=${hours}`;
    }

    // ─── Fetch devices ────────────────────────────────────
    async function loadDevices() {
        try {
            const res  = await fetch('/api/devices');
            const data = await res.json();

            const select = document.getElementById('deviceSelect');
            select.innerHTML = '';

            data.devices.forEach(device => {
                const opt = document.createElement('option');
                opt.value       = device.uid;
                opt.textContent = device.name || device.uid;
                select.appendChild(opt);
            });

            if (data.devices.length > 0) {
                currentDeviceUid = data.devices[0].uid;
                loadLatest(currentDeviceUid);
                loadHistory(currentDeviceUid);
            }
        } catch (e) {
            console.error('Failed to load devices:', e);
            document.getElementById('deviceSelect').innerHTML = '<option value="SA-NODE1">SA-NODE1</option>';
            currentDeviceUid = 'SA-NODE1';
            loadLatest(currentDeviceUid);
            loadHistory(currentDeviceUid);
        }
    }

    document.getElementById('deviceSelect').addEventListener('change', e => {
        currentDeviceUid = e.target.value;
        if (currentDeviceUid) {
            loadLatest(currentDeviceUid);
            loadHistory(currentDeviceUid);
        }
    });

    // ─── Latest readings ──────────────────────────────────
    async function loadLatest(device_uid) {
        try {
            const res      = await fetch(`/api/latest/${device_uid}`);
            const readings = await res.json();

            if (!Array.isArray(readings) || readings.length === 0) {
                document.getElementById('statusValue').textContent = 'No Data';
                return;
            }

            const tempReading     = readings.find(r => r.sensor_type === 'temperature');
            const moistureReading = readings.find(r => r.sensor_type === 'moisture');
            const lightReading    = readings.find(r => r.sensor_type === 'light');

            document.getElementById('tempValue').textContent     = tempReading     ? tempReading.sensor_value.toFixed(1)     : '--';
            document.getElementById('moistureValue').textContent = moistureReading ? moistureReading.sensor_value.toFixed(1) : '--';
            document.getElementById('lightValue').textContent    = lightReading    ? lightReading.sensor_value.toFixed(1)    : '--';
            document.getElementById('statusValue').textContent   = `Live – ${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
        } catch (e) {
            console.error('Latest failed:', e);
            document.getElementById('statusValue').textContent = 'Error';
        }
    }

    // ─── Charts ───────────────────────────────────────────
    const chartDefaults = {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: items => {
                            const ts = items[0]?.label;
                            return ts ? new Date(ts).toLocaleString([], {
                                month:'short', day:'numeric',
                                hour:'2-digit', minute:'2-digit'
                            }) : '';
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        maxTicksLimit: 8,
                        maxRotation: 0,
                        callback: function(val, idx) {
                            const label = this.getLabelForValue(val);
                            return label ? new Date(label).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '';
                        }
                    },
                    grid: { color: '#f0f0f0' }
                },
                y: { grid: { color: '#f0f0f0' } }
            }
        }
    };

    function makeChart(canvasId, yMin, yMax, yLabel, color) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        const cfg = JSON.parse(JSON.stringify(chartDefaults));
        cfg.options.scales.y.min   = yMin;
        cfg.options.scales.y.max   = yMax;
        cfg.options.scales.y.title = { display: true, text: yLabel };
        return new Chart(ctx, cfg);
    }

    const tempChart     = makeChart('tempChart',     10, 30,    '°C', '#2196f3');
    const moistureChart = makeChart('moistureChart', 0,  110,   '%',  '#4caf50');
    const lightChart    = makeChart('lightChart',    0,  10000, 'lux','#ff9800');

    function setChartLoading(type, loading) {
        document.getElementById(`${type}Loading`).classList.toggle('visible', loading);
    }

    function setChartNoData(type, noData) {
        document.getElementById(`${type}NoData`).classList.toggle('visible', noData);
    }

    function setChartMeta(type, count, fromTs, toTs) {
        const el = document.getElementById(`${type}Meta`);
        if (!count) { el.textContent = ''; return; }
        const fmtOpts = { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' };
        el.textContent = `${count} readings · ${new Date(fromTs).toLocaleString([], fmtOpts)} – ${new Date(toTs).toLocaleString([], fmtOpts)}`;
    }

    function updateChart(chart, type, data, color) {
        let filtered = data.filter(r => r.sensor_type === type);

        if (activeRange.from && activeRange.to) {
            const from = new Date(activeRange.from);
            const to   = new Date(activeRange.to);
            filtered = filtered.filter(r => {
                const t = new Date(r.timestamp);
                return t >= from && t <= to;
            });
        }

        setChartNoData(type, filtered.length === 0);
        setChartMeta(type, filtered.length,
            filtered[0]?.timestamp,
            filtered[filtered.length - 1]?.timestamp
        );

        if (filtered.length === 0) {
            chart.data.labels   = [];
            chart.data.datasets = [];
            chart.update('none');
            return;
        }

        const labels = filtered.map(r => r.timestamp);
        const values = filtered.map(r => r.sensor_value);

        chart.data.labels   = labels;
        chart.data.datasets = [{
            label:            type.charAt(0).toUpperCase() + type.slice(1),
            data:             values,
            borderColor:      color,
            backgroundColor:  color + '22',
            fill:             true,
            tension:          0.35,
            pointRadius:      filtered.length > 100 ? 0 : 2,
            pointHoverRadius: 5,
            borderWidth:      2
        }];

        // Dynamically adjust Y axis
        const min = Math.min(...values);
        const max = Math.max(...values);
        const pad = (max - min) * 0.1 || 1;
        chart.options.scales.y.min          = undefined;
        chart.options.scales.y.max          = undefined;
        chart.options.scales.y.suggestedMin = min - pad;
        chart.options.scales.y.suggestedMax = max + pad;

        chart.update();
    }

    // ─── Fetch history ────────────────────────────────────
    async function loadHistory(device_uid) {
        ['temperature','moisture','light'].forEach(t => {
            setChartLoading(t, true);
            setChartNoData(t, false);
        });

        try {
            const url  = buildHistoryUrl(device_uid);
            const res  = await fetch(url);
            const data = await res.json();

            if (!Array.isArray(data)) throw new Error('Unexpected response');

            updateChart(tempChart,     'temperature', data, '#2196f3');
            updateChart(moistureChart, 'moisture',    data, '#4caf50');
            updateChart(lightChart,    'light',       data, '#ff9800');
        } catch (e) {
            console.error('Failed to load history:', e);
        } finally {
            ['temperature','moisture','light'].forEach(t => setChartLoading(t, false));
        }
    }

    // ─── Boot ─────────────────────────────────────────────
    updateActiveLabel();
    loadDevices();
});