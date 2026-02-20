// ---- State ----
let allUsers = [];
let allSites = [];
let editingUserId = null;
let deletingUserId = null;
let siteModalUserId = null;
let userSiteAssignments = {}; // userId -> Set of siteIds

// ---- Init ----
window.addEventListener('DOMContentLoaded', async () => {
    await Promise.all([loadUsers(), loadSites()]);
});

// ---- Data Loading ----
async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    tbody.innerHTML = '<tr class="loading-row"><td colspan="7">Loading users…</td></tr>';
    try {
        const res = await fetch('/api/users/list');
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        allUsers = data.users;
        // Also load site assignments for each user
        await loadAllSiteAssignments();
        renderUsers();
    } catch (e) {
        tbody.innerHTML = `<tr class="loading-row"><td colspan="7" style="color:#e53935;">Failed to load users: ${e.message}</td></tr>`;
    }
}

async function loadSites() {
    try {
        const res = await fetch('/api/sites');
        const data = await res.json();
        allSites = data.sites || [];
    } catch (e) {
        allSites = [];
    }
}

async function loadAllSiteAssignments() {
    // Load site assignments for all users in parallel
    const promises = allUsers.map(u => 
        fetch(`/api/users/${u.id}/sites`)
            .then(r => r.ok ? r.json() : { sites: [] })
            .then(d => ({ userId: u.id, sites: d.sites || [] }))
            .catch(() => ({ userId: u.id, sites: [] }))
    );
    const results = await Promise.all(promises);
    results.forEach(r => {
        userSiteAssignments[r.userId] = new Set(r.sites.map(s => s.id));
    });
}

// ---- Render ----
function renderUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!allUsers.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7">
                    <div class="empty-state">
                        <div class="empty-icon">👤</div>
                        <p>No users found. Create the first one!</p>
                    </div>
                </td>
            </tr>`;
        return;
    }

    tbody.innerHTML = allUsers.map(u => {
        const sites = allSites.filter(s => (userSiteAssignments[u.id] || new Set()).has(s.id));
        const siteHtml = sites.length
            ? sites.map(s => `<span class="site-chip">${s.friendly_name || s.site_code}</span>`).join('')
            : `<span class="no-sites">None assigned</span>`;

        return `
        <tr>
            <td data-label="ID">${u.id}</td>
            <td data-label="Username"><strong>${escHtml(u.username)}</strong></td>
            <td data-label="Full Name">${escHtml(u.full_name || '—')}</td>
            <td data-label="Email">${escHtml(u.email)}</td>
            <td data-label="Role">
                <span class="role-badge ${u.role}">${u.role === 'sys_admin' ? 'Admin' : 'User'}</span>
            </td>
            <td data-label="Sites">
                <div class="site-chips">${siteHtml}</div>
            </td>
            <td data-label="Actions">
                <div class="actions-cell">
                    <button class="btn-small" onclick="openEditModal(${u.id})">✏️ Edit</button>
                    <button class="btn-small btn-secondary" onclick="openSiteModal(${u.id})">🏡 Sites</button>
                    <button class="btn-small btn-danger" onclick="openDeleteModal(${u.id})">🗑️</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ---- Create / Edit Modal ----
function openCreateModal() {
    editingUserId = null;
    document.getElementById('userModalTitle').textContent = 'Add User';
    document.getElementById('userModalSaveBtn').textContent = 'Create User';
    document.getElementById('fieldUsername').value = '';
    document.getElementById('fieldFullName').value = '';
    document.getElementById('fieldEmail').value = '';
    document.getElementById('fieldPassword').value = '';
    document.getElementById('fieldRole').value = 'user';
    document.getElementById('fieldUsername').disabled = false;
    document.getElementById('passwordLabel').textContent = 'Password *';
    document.getElementById('passwordHint').textContent = '';
    clearFormMessages('userFormError', 'userFormSuccess');
    document.getElementById('userModal').style.display = 'block';
}

function openEditModal(userId) {
    const user = allUsers.find(u => u.id === userId);
    if (!user) return;
    editingUserId = userId;
    document.getElementById('userModalTitle').textContent = 'Edit User';
    document.getElementById('userModalSaveBtn').textContent = 'Save Changes';
    document.getElementById('fieldUsername').value = user.username;
    document.getElementById('fieldUsername').disabled = true; // username immutable
    document.getElementById('fieldFullName').value = user.full_name || '';
    document.getElementById('fieldEmail').value = user.email;
    document.getElementById('fieldPassword').value = '';
    document.getElementById('fieldRole').value = user.role;
    document.getElementById('passwordLabel').textContent = 'New Password';
    document.getElementById('passwordHint').textContent = 'Leave blank to keep existing password.';
    clearFormMessages('userFormError', 'userFormSuccess');
    document.getElementById('userModal').style.display = 'block';
}

function closeUserModal() {
    document.getElementById('userModal').style.display = 'none';
    editingUserId = null;
}

async function saveUser() {
    clearFormMessages('userFormError', 'userFormSuccess');
    const username = document.getElementById('fieldUsername').value.trim();
    const fullName = document.getElementById('fieldFullName').value.trim();
    const email = document.getElementById('fieldEmail').value.trim();
    const password = document.getElementById('fieldPassword').value;
    const role = document.getElementById('fieldRole').value;

    if (!email) return showFormError('userFormError', 'Email is required.');

    if (editingUserId) {
        // EDIT
        const body = { email, full_name: fullName || null, role };
        if (password) body.password = password;

        try {
            const res = await fetch(`/api/users/${editingUserId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Update failed');
            showFormSuccess('userFormSuccess', 'User updated successfully!');
            await loadUsers();
            setTimeout(closeUserModal, 1200);
        } catch (e) {
            showFormError('userFormError', e.message);
        }
    } else {
        // CREATE
        if (!username) return showFormError('userFormError', 'Username is required.');
        if (!password) return showFormError('userFormError', 'Password is required.');

        try {
            const res = await fetch('/api/users/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, email, password, full_name: fullName || null, role })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Create failed');
            showFormSuccess('userFormSuccess', `User "${username}" created!`);
            await loadUsers();
            setTimeout(closeUserModal, 1200);
        } catch (e) {
            showFormError('userFormError', e.message);
        }
    }
}

// ---- Site Assignment Modal ----
async function openSiteModal(userId) {
    siteModalUserId = userId;
    const user = allUsers.find(u => u.id === userId);
    document.getElementById('siteModalDesc').textContent =
        `Manage site access for ${user.full_name || user.username}`;
    clearFormMessages('siteFormError');

    const checklist = document.getElementById('sitesChecklist');
    const assigned = userSiteAssignments[userId] || new Set();

    checklist.innerHTML = allSites.map(s => `
        <label class="site-checkbox-item">
            <input type="checkbox"
                id="siteCheck_${s.id}"
                ${assigned.has(s.id) ? 'checked' : ''}
                onchange="toggleSiteAssignment(${userId}, ${s.id}, this.checked)"
            />
            <div class="site-checkbox-label">
                <strong>${escHtml(s.friendly_name || s.site_code)}</strong>
                <span>${escHtml(s.site_code)}</span>
            </div>
        </label>
    `).join('');

    if (!allSites.length) {
        checklist.innerHTML = '<p style="color:#aaa;text-align:center;">No sites registered yet.</p>';
    }

    document.getElementById('siteModal').style.display = 'block';
}

function closeSiteModal() {
    document.getElementById('siteModal').style.display = 'none';
    siteModalUserId = null;
    renderUsers(); // Refresh chips
}

async function toggleSiteAssignment(userId, siteId, assign) {
    clearFormMessages('siteFormError');
    try {
        let res;
        if (assign) {
            res = await fetch(`/api/users/${userId}/assign-site/${siteId}`, { method: 'POST' });
        } else {
            res = await fetch(`/api/users/${userId}/unassign-site/${siteId}`, { method: 'DELETE' });
        }
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Operation failed');
        }
        // Update local state
        if (!userSiteAssignments[userId]) userSiteAssignments[userId] = new Set();
        if (assign) userSiteAssignments[userId].add(siteId);
        else userSiteAssignments[userId].delete(siteId);
    } catch (e) {
        showFormError('siteFormError', e.message);
        // Revert checkbox
        const cb = document.getElementById(`siteCheck_${siteId}`);
        if (cb) cb.checked = !assign;
    }
}

// ---- Delete Modal ----
function openDeleteModal(userId) {
    const user = allUsers.find(u => u.id === userId);
    deletingUserId = userId;
    document.getElementById('deleteUserName').textContent = user.full_name || user.username;
    clearFormMessages('deleteFormError');
    document.getElementById('deleteModal').style.display = 'block';
}

function closeDeleteModal() {
    document.getElementById('deleteModal').style.display = 'none';
    deletingUserId = null;
}

async function confirmDelete() {
    clearFormMessages('deleteFormError');
    try {
        const res = await fetch(`/api/users/${deletingUserId}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Delete failed');
        closeDeleteModal();
        await loadUsers();
    } catch (e) {
        showFormError('deleteFormError', e.message);
    }
}

// ---- Helpers ----
function showFormError(id, msg) {
    const el = document.getElementById(id);
    if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function showFormSuccess(id, msg) {
    const el = document.getElementById(id);
    if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function clearFormMessages(...ids) {
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.textContent = ''; el.style.display = 'none'; }
    });
}

// Close modals on backdrop click
window.addEventListener('click', (e) => {
    if (e.target.id === 'userModal') closeUserModal();
    if (e.target.id === 'siteModal') closeSiteModal();
    if (e.target.id === 'deleteModal') closeDeleteModal();
});