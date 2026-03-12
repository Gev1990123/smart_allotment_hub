// ============================================
// SENSORS PAGE JAVASCRIPT
// ============================================

// Global state
let allSensors = [];
let allPlantProfiles = [];
let sensorToDelete = null;

// Plant modal state
let plantModalSensorId = null;
let plantModalSelectedProfileId = null;
let plantModalCurrentProfileId = null;

// ============================================
// PAGE INITIALIZATION
// ============================================
document.addEventListener('DOMContentLoaded', function () {
    loadSensors();
    loadPlantProfiles(); // pre-fetch so modal opens instantly

    // Auto-refresh every 30 seconds
    setInterval(loadSensors, 30000);
});

// ============================================
// DATA LOADING
// ============================================
async function loadSensors() {
    const container = document.getElementById('sensorsTableContainer');
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');

    try {
        const res = await fetch('/api/sensors/list');
        const data = await res.json();

        allSensors = data.sensors || [];

        if (allSensors.length === 0) {
            container.style.display = 'none';
            loadingState.style.display = 'none';
            emptyState.style.display = 'block';
            updateStats();
            return;
        }

        loadingState.style.display = 'none';
        emptyState.style.display = 'none';
        container.style.display = 'block';

        populateDeviceFilter();
        updateStats();
        filterSensors();

    } catch (e) {
        console.error('Failed to load sensors:', e);
        loadingState.innerHTML = '<p style="color: #e53935;">Error loading sensors. Please try again.</p>';
        loadingState.style.display = 'block';
    }
}

async function loadPlantProfiles() {
    try {
        const res = await fetch('/api/plant-profiles');
        const data = await res.json();
        allPlantProfiles = data.plant_profiles || [];
    } catch (e) {
        console.error('Failed to load plant profiles:', e);
    }
}

function populateDeviceFilter() {
    const deviceFilter = document.getElementById('deviceFilter');
    const uniqueDevices = [...new Set(allSensors.map(s => s.device_uid))].sort();

    deviceFilter.innerHTML = '<option value="">All Devices</option>';
    uniqueDevices.forEach(uid => {
        const option = document.createElement('option');
        option.value = uid;
        option.textContent = uid;
        deviceFilter.appendChild(option);
    });
}

function updateStats() {
    const total = allSensors.length;
    const active = allSensors.filter(s => s.active).length;
    const inactive = total - active;
    const devices = new Set(allSensors.map(s => s.device_uid)).size;

    document.getElementById('totalSensors').textContent = total;
    document.getElementById('activeSensors').textContent = active;
    document.getElementById('inactiveSensors').textContent = inactive;
    document.getElementById('devicesWithSensors').textContent = devices;
}

// ============================================
// FILTERING
// ============================================
function filterSensors() {
    const deviceFilter = document.getElementById('deviceFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;

    let filtered = allSensors;
    if (deviceFilter) filtered = filtered.filter(s => s.device_uid === deviceFilter);
    if (statusFilter === 'active') filtered = filtered.filter(s => s.active);
    else if (statusFilter === 'inactive') filtered = filtered.filter(s => !s.active);

    renderSensorsTable(filtered);
}

// ============================================
// TABLE RENDERING
// ============================================
function renderSensorsTable(sensors) {
    const container = document.getElementById('sensorsTableContainer');

    if (sensors.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666; padding: 20px;">No sensors match the current filters.</p>';
        return;
    }

    const table = `
        <table class="sensors-table">
            <thead>
                <tr>
                    <th>Device</th>
                    <th>Sensor Name</th>
                    <th>Type</th>
                    <th>Unit</th>
                    <th>Status</th>
                    <th>Last Value</th>
                    <th>Last Seen</th>
                    <th>Plant Profile</th>
                    <th>Notes</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${sensors.map(sensor => renderSensorRow(sensor)).join('')}
            </tbody>
        </table>
    `;

    container.innerHTML = table;
}

function renderSensorRow(sensor) {
    const statusBadge = sensor.active
        ? '<span class="status-badge online">Active</span>'
        : '<span class="status-badge offline">Inactive</span>';

    const lastValue = sensor.last_value !== null ? sensor.last_value.toFixed(2) : '--';
    const lastSeen = sensor.last_seen ? timeAgo(sensor.last_seen) : 'Never';
    const notes = sensor.notes || '<em style="color: #999;">No notes</em>';

    // Plant profile badge — only shown for moisture sensors
    let plantCell = '<span style="color:#ccc; font-size:12px;">N/A</span>';
    if (sensor.sensor_type === 'moisture') {
        if (sensor.plant_profile_name) {
            plantCell = `
                <span class="plant-badge">🌱 ${sensor.plant_profile_name}</span>
            `;
        } else {
            plantCell = `<span class="plant-badge unassigned">General</span>`;
        }
    }

    // Plant assign button — only for moisture sensors
    const plantBtn = sensor.sensor_type === 'moisture'
        ? `<button class="btn-small" style="background:#2e7d32;" 
               onclick="openPlantModal(${sensor.id}, '${sensor.sensor_name}', '${sensor.device_uid}', ${sensor.plant_profile_id === null || sensor.plant_profile_id === undefined ? 'null' : sensor.plant_profile_id})">
               🌱 Plant
           </button>`
        : '';

    return `
        <tr class="${sensor.active ? '' : 'inactive-row'}">
            <td data-label="Device"><span class="device-uid">${sensor.device_uid}</span></td>
            <td data-label="Sensor Name"><strong>${sensor.sensor_name}</strong></td>
            <td data-label="Type">${sensor.sensor_type}</td>
            <td data-label="Unit">${sensor.unit || '--'}</td>
            <td data-label="Status">${statusBadge}</td>
            <td data-label="Last Value">${lastValue}</td>
            <td data-label="Last Seen">${lastSeen}</td>
            <td data-label="Plant Profile">${plantCell}</td>
            <td data-label="Notes" style="max-width: 180px; overflow: hidden; text-overflow: ellipsis;" 
                title="${sensor.notes || ''}">${notes}</td>
            <td data-label="Actions">
                <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                    ${sensor.active
                        ? `<button class="btn-small btn-secondary" onclick="toggleSensorStatus(${sensor.id}, false)">Deactivate</button>`
                        : `<button class="btn-small" onclick="toggleSensorStatus(${sensor.id}, true)">Activate</button>`
                    }
                    ${plantBtn}
                    <button class="btn-small btn-danger" onclick="deleteSensor(${sensor.id}, '${sensor.sensor_name}', '${sensor.device_uid}')">Delete</button>
                </div>
            </td>
        </tr>
    `;
}

// ============================================
// PLANT PROFILE MODAL
// ============================================
function openPlantModal(sensorId, sensorName, deviceUid, currentProfileId) {
    // Normalize profile id (number or null)
    const profileId =
        (currentProfileId === null ||
         currentProfileId === undefined ||
         currentProfileId === 'null')
            ? null
            : parseInt(currentProfileId, 10);

    plantModalSensorId = sensorId;
    plantModalSelectedProfileId = profileId;
    plantModalCurrentProfileId = profileId;

    document.getElementById('plantModalSensorName').textContent = sensorName;
    document.getElementById('plantModalDeviceUid').textContent = deviceUid;
    document.getElementById('plantModalError').style.display = 'none';
    document.getElementById('plantModalSuccess').style.display = 'none';

    // Disable Save until user changes selection
    document.getElementById('savePlantBtn').disabled = true;

    // Show current assignment strip if one exists
    const currentStrip = document.getElementById('currentAssignment');
    if (profileId !== null) {
        const profile = allPlantProfiles.find(p => Number(p.id) === profileId);
        document.getElementById('currentAssignmentName').textContent =
            profile ? profile.name : 'Unknown';
        currentStrip.style.display = 'flex';
    } else {
        currentStrip.style.display = 'none';
    }

    // Render cards and open modal
    renderPlantProfileCards();
    document.getElementById('plantModal').classList.add('is-open');
}

function renderPlantProfileCards() {
    const grid = document.getElementById('plantProfileCards');

    if (!allPlantProfiles || !allPlantProfiles.length) {
        grid.innerHTML = `
            <div style="color:#999; text-align:center; padding:20px; grid-column:span 2;">
                No profiles available.
            </div>
        `;
        return;
    }

    grid.innerHTML = allPlantProfiles.map(profile => {
        const id = Number(profile.id);
        const isSelected = plantModalSelectedProfileId === id;
        return `
            <div class="plant-profile-card ${isSelected ? 'selected' : ''}"
                 onclick="selectPlantCard(${id}, this)">
                <div class="plant-card-name">${profile.name}</div>
                <div class="plant-card-range">💧 ${profile.moisture_min}% – ${profile.moisture_max}%</div>
                <div class="plant-card-desc">${profile.description || ''}</div>
            </div>
        `;
    }).join('');
}

function selectPlantCard(profileId, cardEl) {
    const id = parseInt(profileId, 10);
    // Deselect all, select clicked
    document.querySelectorAll('.plant-profile-card')
        .forEach(c => c.classList.remove('selected'));
    cardEl.classList.add('selected');

    plantModalSelectedProfileId = id;

    // Enable save only if selection has changed from current
    document.getElementById('savePlantBtn').disabled =
        (plantModalCurrentProfileId === id);
}

async function savePlantProfile() {
    if (!plantModalSelectedProfileId || !plantModalSensorId) return;

    const saveBtn = document.getElementById('savePlantBtn');
    const errorEl = document.getElementById('plantModalError');
    const successEl = document.getElementById('plantModalSuccess');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    errorEl.style.display = 'none';
    successEl.style.display = 'none';

    try {
        const res = await fetch(`/api/sensors/${plantModalSensorId}/plant-profile`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plant_profile_id: plantModalSelectedProfileId })
        });

        const data = await res.json();

        if (res.ok) {
            const profile = allPlantProfiles.find(p => p.id === plantModalSelectedProfileId);
            successEl.textContent = `✓ Assigned to ${profile ? profile.name : 'profile'} successfully`;
            successEl.style.display = 'block';

            // Update current assignment strip immediately
            plantModalCurrentProfileId = plantModalSelectedProfileId;
            document.getElementById('currentAssignmentName').textContent = profile ? profile.name : '';
            document.getElementById('currentAssignment').style.display = 'flex';

            setTimeout(() => {
                closePlantModal();
                loadSensors(); // refresh table to show updated badge
            }, 1200);
        } else {
            errorEl.textContent = data.detail || 'Failed to save plant profile';
            errorEl.style.display = 'block';
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
        }
    } catch (e) {
        errorEl.textContent = 'Network error. Please try again.';
        errorEl.style.display = 'block';
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
    }
}

async function removePlantProfile() {
    if (!plantModalSensorId) return;

    const errorEl = document.getElementById('plantModalError');
    const successEl = document.getElementById('plantModalSuccess');
    errorEl.style.display = 'none';
    successEl.style.display = 'none';

    try {
        const res = await fetch(`/api/sensors/${plantModalSensorId}/plant-profile`, {
            method: 'DELETE'
        });

        if (res.ok) {
            successEl.textContent = '✓ Plant profile removed — sensor will use General defaults';
            successEl.style.display = 'block';

            // Clear selection state
            plantModalCurrentProfileId = null;
            plantModalSelectedProfileId = null;
            document.getElementById('currentAssignment').style.display = 'none';
            document.querySelectorAll('.plant-profile-card').forEach(c => c.classList.remove('selected'));
            document.getElementById('savePlantBtn').disabled = true;

            setTimeout(() => {
                closePlantModal();
                loadSensors();
            }, 1200);
        } else {
            const data = await res.json();
            errorEl.textContent = data.detail || 'Failed to remove plant profile';
            errorEl.style.display = 'block';
        }
    } catch (e) {
        errorEl.textContent = 'Network error. Please try again.';
        errorEl.style.display = 'block';
    }
}

function closePlantModal() {
    document.getElementById('plantModal').classList.remove('is-open');
    plantModalSensorId = null;
    plantModalSelectedProfileId = null;
    plantModalCurrentProfileId = null;
}

// ============================================
// REGISTER SENSOR MODAL
// ============================================
async function openAddSensorModal() {
    document.getElementById('sensorModal').classList.add('is-open');
    document.getElementById('modalTitle').textContent = 'Register New Sensor';
    document.getElementById('sensorForm').reset();
    document.getElementById('sensorId').value = '';
    document.getElementById('formError').style.display = 'none';
    document.getElementById('formSuccess').style.display = 'none';
    document.getElementById('submitBtn').textContent = 'Register Sensor';
    await loadDevicesForModal();
}

async function loadDevicesForModal() {
    const deviceSelect = document.getElementById('sensorDevice');
    deviceSelect.innerHTML = '<option value="">Loading devices...</option>';

    try {
        const response = await fetch('/api/devices');
        const data = await response.json();
        const devices = data?.devices || [];

        deviceSelect.innerHTML = '<option value="">Select a device...</option>';
        if (Array.isArray(devices) && devices.length > 0) {
            devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.uid;
                option.textContent = `${device.name || device.uid} (${device.uid})`;
                deviceSelect.appendChild(option);
            });
        } else {
            deviceSelect.innerHTML = '<option value="">No devices available</option>';
        }
    } catch (error) {
        console.error('Error fetching devices:', error);
        deviceSelect.innerHTML = '<option value="">Error loading devices</option>';
    }
}

function updateUnitField() {
    const typeSelect = document.getElementById('sensorType');
    const unitInput = document.getElementById('sensorUnit');
    const unitMap = { 'moisture': '%', 'temperature': '°C', 'light': 'lx' };
    unitInput.value = unitMap[typeSelect.value] || '';
}

function closeSensorModal() {
    document.getElementById('sensorModal').classList.remove('is-open');
}

document.getElementById('sensorForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const formError = document.getElementById('formError');
    const formSuccess = document.getElementById('formSuccess');
    const submitBtn = document.getElementById('submitBtn');

    formError.style.display = 'none';
    formSuccess.style.display = 'none';

    const deviceUid = document.getElementById('sensorDevice').value;
    const sensorName = document.getElementById('sensorName').value.trim();
    const sensorType = document.getElementById('sensorType').value;
    const unit = document.getElementById('sensorUnit').value.trim() || null;
    const notes = document.getElementById('sensorNotes').value.trim() || null;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Registering...';

    try {
        const response = await fetch('/api/sensors/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_uid: deviceUid, sensor_name: sensorName, sensor_type: sensorType, unit, notes })
        });

        const data = await response.json();

        if (response.ok) {
            formSuccess.textContent = `Sensor "${sensorName}" registered successfully!`;
            formSuccess.style.display = 'block';
            setTimeout(() => { closeSensorModal(); loadSensors(); }, 1500);
        } else {
            formError.textContent = data.detail || 'Failed to register sensor';
            formError.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.textContent = 'Register Sensor';
        }
    } catch (error) {
        formError.textContent = 'Network error. Please try again.';
        formError.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Register Sensor';
    }
});

// ============================================
// SENSOR ACTIONS
// ============================================
async function toggleSensorStatus(sensorId, activate) {
    const action = activate ? 'activate' : 'deactivate';
    try {
        const response = await fetch(`/api/sensors/${sensorId}/${action}`, { method: 'POST' });
        if (response.ok) {
            await loadSensors();
        } else {
            const data = await response.json();
            alert(`Failed to ${action} sensor: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`Network error. Failed to ${action} sensor.`);
    }
}

function deleteSensor(sensorId, sensorName, deviceUid) {
    sensorToDelete = sensorId;
    document.getElementById('deleteMessage').textContent =
        `Are you sure you want to delete sensor "${sensorName}" from device "${deviceUid}"?`;
    document.getElementById('confirmDeleteModal').classList.add('is-open'); 
}

async function confirmDelete() {
    if (!sensorToDelete) return;
    try {
        const response = await fetch(`/api/sensors/${sensorToDelete}/delete`, { method: 'DELETE' });
        if (response.ok) {
            closeDeleteModal();
            await loadSensors();
        } else {
            const data = await response.json();
            alert(`Failed to delete sensor: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        alert('Network error. Failed to delete sensor.');
    }
}

function closeDeleteModal() {
    document.getElementById('confirmDeleteModal').classList.remove('is-open'); 
    sensorToDelete = null;
}

// Close modals when clicking outside
window.onclick = function (event) {
    if (event.target === document.getElementById('sensorModal')) closeSensorModal();
    if (event.target === document.getElementById('confirmDeleteModal')) closeDeleteModal();
    if (event.target === document.getElementById('plantModal')) closePlantModal();
};