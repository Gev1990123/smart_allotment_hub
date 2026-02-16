// ============================================
// SENSORS PAGE JAVASCRIPT
// ============================================

// Global state
let allSensors = [];
let sensorToDelete = null;

// ============================================
// PAGE INITIALIZATION
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    loadSensors();
    
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
        
        // Populate device filter
        populateDeviceFilter();
        
        // Update stats
        updateStats();
        
        // Render table
        filterSensors();
        
    } catch (e) {
        console.error('Failed to load sensors:', e);
        loadingState.innerHTML = '<p style="color: #e53935;">Error loading sensors. Please try again.</p>';
        loadingState.style.display = 'block';
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
    
    if (deviceFilter) {
        filtered = filtered.filter(s => s.device_uid === deviceFilter);
    }
    
    if (statusFilter === 'active') {
        filtered = filtered.filter(s => s.active);
    } else if (statusFilter === 'inactive') {
        filtered = filtered.filter(s => !s.active);
    }
    
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
                    <th>Sensor ID</th>
                    <th>Type</th>
                    <th>Unit</th>
                    <th>Status</th>
                    <th>Last Value</th>
                    <th>Last Seen</th>
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
    
    return `
        <tr class="${sensor.active ? '' : 'inactive-row'}">
            <td><span class="device-uid">${sensor.device_uid}</span></td>
            <td><strong>${sensor.sensor_name}</strong></td>
            <td>${sensor.sensor_type}</td>
            <td>${sensor.unit || '--'}</td>
            <td>${statusBadge}</td>
            <td>${lastValue}</td>
            <td>${lastSeen}</td>
            <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;" title="${sensor.notes || ''}">${notes}</td>
            <td>
                <div style="display: flex; gap: 5px;">
                    ${sensor.active 
                        ? `<button class="btn-small btn-secondary" onclick="toggleSensorStatus(${sensor.id}, false)">Deactivate</button>`
                        : `<button class="btn-small" onclick="toggleSensorStatus(${sensor.id}, true)">Activate</button>`
                    }
                    <button class="btn-small btn-danger" onclick="deleteSensor(${sensor.id}, '${sensor.sensor_name}', '${sensor.device_uid}')">Delete</button>
                </div>
            </td>
        </tr>
    `;
}

// ============================================
// ADD/EDIT SENSOR MODAL
// ============================================
async function openAddSensorModal() {
    document.getElementById('sensorModal').style.display = 'block';
    document.getElementById('modalTitle').textContent = 'Register New Sensor';
    document.getElementById('sensorForm').reset();
    document.getElementById('sensorId').value = '';
    document.getElementById('formError').style.display = 'none';
    document.getElementById('formSuccess').style.display = 'none';
    document.getElementById('submitBtn').textContent = 'Register Sensor';

    // Load devices
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
    
    const unitMap = {
        'moisture': '%',
        'temperature': '°C',
        'light': 'lx'
    };
    
    unitInput.value = unitMap[typeSelect.value] || '';
}

function closeSensorModal() {
    document.getElementById('sensorModal').style.display = 'none';
}

// Handle form submission
document.getElementById('sensorForm').addEventListener('submit', async function(e) {
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
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                device_uid: deviceUid,
                sensor_name: sensorName,
                sensor_type: sensorType,
                unit: unit,
                notes: notes
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            formSuccess.textContent = `Sensor "${sensorName}" registered successfully!`;
            formSuccess.style.display = 'block';
            
            setTimeout(() => {
                closeSensorModal();
                loadSensors();
            }, 1500);
            
        } else {
            formError.textContent = data.detail || 'Failed to register sensor';
            formError.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.textContent = 'Register Sensor';
        }
        
    } catch (error) {
        console.error('Error registering sensor:', error);
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
        const response = await fetch(`/api/sensors/${sensorId}/${action}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            await loadSensors();
        } else {
            const data = await response.json();
            alert(`Failed to ${action} sensor: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error(`Error ${action}ing sensor:`, error);
        alert(`Network error. Failed to ${action} sensor.`);
    }
}

function deleteSensor(sensorId, sensorName, deviceUid) {
    sensorToDelete = sensorId;
    document.getElementById('deleteMessage').textContent = 
        `Are you sure you want to delete sensor "${sensorName}" from device "${deviceUid}"?`;
    document.getElementById('confirmDeleteModal').style.display = 'block';
}

async function confirmDelete() {
    if (!sensorToDelete) return;
    
    try {
        const response = await fetch(`/api/sensors/${sensorToDelete}/delete`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            closeDeleteModal();
            await loadSensors();
        } else {
            const data = await response.json();
            alert(`Failed to delete sensor: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Error deleting sensor:', error);
        alert('Network error. Failed to delete sensor.');
    }
}

function closeDeleteModal() {
    document.getElementById('confirmDeleteModal').style.display = 'none';
    sensorToDelete = null;
}

// Close modals when clicking outside
window.onclick = function(event) {
    const sensorModal = document.getElementById('sensorModal');
    const deleteModal = document.getElementById('confirmDeleteModal');
    
    if (event.target === sensorModal) {
        closeSensorModal();
    }
    if (event.target === deleteModal) {
        closeDeleteModal();
    }
}