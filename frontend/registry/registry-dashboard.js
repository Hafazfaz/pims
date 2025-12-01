// Registry Dashboard JavaScript
const API_URL = '/api';
let currentUser = null;
let selectedRequestId = null;

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    await loadProfile();
    setupEventListeners();
    await loadDashboardData();
});

// Load user profile
async function loadProfile() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '../public/login_index.html';
        return;
    }

    try {
        const response = await fetch(`${API_URL}/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            throw new Error('Failed to load profile');
        }

        currentUser = await response.json();
        document.getElementById('welcomeName').textContent = currentUser.username;
        document.getElementById('headerUserName').textContent = currentUser.username;
        document.querySelector('.avatar').textContent = currentUser.username.charAt(0).toUpperCase();
    } catch (error) {
        console.error('Error loading profile:', error);
        localStorage.removeItem('access_token');
        window.location.href = '../public/login_index.html';
    }
}

// Setup event listeners
function setupEventListeners() {
    // Sidebar navigation
    document.querySelectorAll('.sidebar a[data-section]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const section = e.currentTarget.dataset.section;
            showSection(section);
        });
    });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        localStorage.removeItem('access_token');
        window.location.href = '../public/login_index.html';
    });

    // Create file form
    document.getElementById('create-file-form').addEventListener('submit', handleCreateFile);

    // Category change
    document.getElementById('file-category').addEventListener('change', handleCategoryChange);

    // File name to uppercase
    document.getElementById('file-name').addEventListener('input', (e) => {
        e.target.value = e.target.value.toUpperCase();
    });
}

// Show section
function showSection(sectionId) {
    // Update active nav link
    document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
    document.querySelector(`[data-section="${sectionId}"]`).classList.add('active');

    // Hide all sections
    document.querySelectorAll('.dashboard-section').forEach(s => s.classList.remove('active'));

    // Show selected section
    document.getElementById(sectionId).classList.add('active');

    // Load data for specific sections
    if (sectionId === 'activation-requests') {
        loadActivationRequests();
    }
}

// Load dashboard data
async function loadDashboardData() {
    await loadStats();
    await loadActivationRequests();
    await loadDepartments();
    await loadStaff();
    await loadFiles();
}

// Load statistics
async function loadStats() {
    const token = localStorage.getItem('access_token');

    try {
        // For now, we'll use placeholder data
        // In production, these would be API calls to get actual counts
        document.getElementById('files-today').textContent = '0';
        document.getElementById('files-this-month').textContent = '0';
        document.getElementById('active-files').textContent = '0';
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Load activation requests
async function loadActivationRequests() {
    const token = localStorage.getItem('access_token');

    try {
        const response = await fetch(`${API_URL}/registry/activation-requests`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to load activation requests');

        const requests = await response.json();

        // Update badge count
        const pendingCount = requests.length;
        document.getElementById('pending-badge').textContent = pendingCount;
        document.getElementById('pending-activations').textContent = pendingCount;

        // Update table
        const tbody = document.getElementById('activation-requests-body');
        if (requests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No pending activation requests</td></tr>';
            return;
        }

        tbody.innerHTML = requests.map(req => `
            <tr>
                <td><strong>${req.file_number}</strong></td>
                <td>${req.filename}</td>
                <td><span class="state-badge ${req.file_category === 'Personal' ? 'state-active' : 'state-inactive'}">${req.file_category}</span></td>
                <td>${req.requestor_name} <small>(${req.requestor_email})</small></td>
                <td>${req.request_reason}</td>
                <td>${new Date(req.created_at).toLocaleString()}</td>
                <td>
                    <button class="btn btn-success" style="padding: 0.5rem 1rem;" onclick="openApproveModal(${req.id}, '${req.file_number}', '${req.filename}')">
                        <i class="fas fa-check"></i> Approve
                    </button>
                    <button class="btn btn-danger" style="padding: 0.5rem 1rem;" onclick="openRejectModal(${req.id}, '${req.file_number}', '${req.filename}')">
                        <i class="fas fa-times"></i> Reject
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading activation requests:', error);
        console.error('Error details:', error.message);

        // Try to get more details from response
        const tbody = document.getElementById('activation-requests-body');
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color: #ef4444;">Error: ${error.message}. Check browser console for details.</td></tr>`;

        showNotification(`Error loading activation requests: ${error.message}`, 'error');
    }
}

// Load departments for dropdown
async function loadDepartments() {
    const token = localStorage.getItem('access_token');

    try {
        const response = await fetch(`${API_URL}/departments`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to load departments');

        const departments = await response.json();
        const select = document.getElementById('department');
        select.innerHTML = '<option value="">-- Select Department --</option>' +
            departments.map(d => `<option value="${d.id}" data-code="${d.code}">${d.name}</option>`).join('');
    } catch (error) {
        console.error('Error loading departments:', error);
    }
}

// Load staff for owner dropdown
async function loadStaff() {
    const token = localStorage.getItem('access_token');

    try {
        const response = await fetch(`${API_URL}/users`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to load staff');

        const staff = await response.json();
        const select = document.getElementById('owner');
        select.innerHTML = '<option value="">-- Select Staff Member --</option>' +
            staff.map(s => `<option value="${s.id}">${s.username} (${s.role_name})</option>`).join('');
    } catch (error) {
        console.error('Error loading staff:', error);
    }
}

// Handle category change
function handleCategoryChange() {
    const category = document.getElementById('file-category').value;
    const employmentGroup = document.getElementById('employment-type-group');
    const departmentGroup = document.getElementById('department-group');
    const ownerGroup = document.getElementById('owner-group');

    if (category === 'Personal') {
        employmentGroup.style.display = 'block';
        departmentGroup.style.display = 'none';
        ownerGroup.style.display = 'block';
        document.getElementById('employment-type').required = true;
        document.getElementById('department').required = false;
    } else if (category === 'Policy') {
        employmentGroup.style.display = 'none';
        departmentGroup.style.display = 'block';
        ownerGroup.style.display = 'none';
        document.getElementById('employment-type').required = false;
        document.getElementById('department').required = true;
    } else {
        employmentGroup.style.display = 'none';
        departmentGroup.style.display = 'none';
        ownerGroup.style.display = 'none';
    }
}

// Handle create file
async function handleCreateFile(e) {
    e.preventDefault();

    const token = localStorage.getItem('access_token');
    const fileName = document.getElementById('file-name').value;
    const category = document.getElementById('file-category').value;
    const employmentType = document.getElementById('employment-type').value;
    const departmentId = document.getElementById('department').value;
    const ownerId = document.getElementById('owner').value || null;
    const secondLevelAuth = document.getElementById('second-level-auth').checked;

    const data = {
        file_name: fileName,
        category: category,
        employment_type: employmentType || null,
        department_id: departmentId ? parseInt(departmentId) : null,
        owner_id: ownerId ? parseInt(ownerId) : null,
        second_level_auth: secondLevelAuth
    };

    try {
        const response = await fetch(`${API_URL}/registry/files`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to create file');
        }

        showNotification(`File created successfully! File Number: ${result.file_number}`, 'success');
        document.getElementById('create-file-form').reset();
        await loadDashboardData();
        showSection('overview');
    } catch (error) {
        console.error('Error creating file:', error);
        showNotification(error.message, 'error');
    }
}

// Open approve modal
function openApproveModal(requestId, fileNumber, fileName) {
    selectedRequestId = requestId;
    document.getElementById('approve-details').textContent =
        `Are you sure you want to approve activation for file "${fileName}" (${fileNumber})?`;
    document.getElementById('approve-modal').classList.add('show');
}

// Confirm approval
async function confirmApproval() {
    const token = localStorage.getItem('access_token');

    try {
        const response = await fetch(`${API_URL}/registry/activation-requests/${selectedRequestId}/approve`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to approve request');
        }

        showNotification('File activation approved successfully', 'success');
        closeModal('approve-modal');
        await loadActivationRequests();
        await loadStats();
    } catch (error) {
        console.error('Error approving request:', error);
        showNotification(error.message, 'error');
    }
}

// Open reject modal
function openRejectModal(requestId, fileNumber, fileName) {
    selectedRequestId = requestId;
    document.getElementById('reject-details').textContent =
        `Rejecting activation for file "${fileName}" (${fileNumber})`;
    document.getElementById('rejection-reason').value = '';
    document.getElementById('reject-modal').classList.add('show');
}

// Confirm rejection
async function confirmRejection() {
    const token = localStorage.getItem('access_token');
    const rejectionReason = document.getElementById('rejection-reason').value.trim();

    if (!rejectionReason) {
        showNotification('Please enter a rejection reason', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/registry/activation-requests/${selectedRequestId}/reject`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ rejection_reason: rejectionReason })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to reject request');
        }

        showNotification('File activation request rejected', 'success');
        closeModal('reject-modal');
        await loadActivationRequests();
    } catch (error) {
        console.error('Error rejecting request:', error);
        showNotification(error.message, 'error');
    }
}

// Close modal
function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('show');
}

// Load files for management
async function loadFiles(searchQuery = '') {
    const token = localStorage.getItem('access_token');
    const tbody = document.getElementById('files-body');

    try {
        let url = `${API_URL}/registry/files`;
        if (searchQuery) {
            url += `?search=${encodeURIComponent(searchQuery)}`;
        }

        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to load files');

        const files = await response.json();

        if (files.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No files found</td></tr>';
            return;
        }

        tbody.innerHTML = files.map(file => `
            <tr>
                <td><strong>${file.file_number}</strong></td>
                <td>${file.filename}</td>
                <td><span class="badge badge-secondary">${file.file_category}</span></td>
                <td><span class="state-badge state-${file.file_state.toLowerCase()}">${file.file_state}</span></td>
                <td>${file.current_holder ? file.current_holder : '<span class="text-muted">Registry</span>'}</td>
                <td>${new Date(file.created_at).toLocaleDateString()}</td>
                <td>
                    <div class="btn-group">
                        ${file.file_state === 'Active' ? `
                        <button class="btn btn-warning btn-sm" onclick="deactivateFile(${file.id}, '${file.file_number}')" title="Return to Registry">
                            <i class="fas fa-undo"></i>
                        </button>` : ''}
                        <button class="btn btn-info btn-sm" onclick="viewFileHistory(${file.id})" title="View History">
                            <i class="fas fa-history"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

    } catch (error) {
        console.error('Error loading files:', error);
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">Error loading files: ${error.message}</td></tr>`;
    }
}

// Search files
function searchFiles() {
    const query = document.getElementById('file-search').value;
    loadFiles(query);
}

// Deactivate file
async function deactivateFile(fileId, fileNumber) {
    if (!confirm(`Are you sure you want to return file ${fileNumber} to Registry (Deactivate)?`)) return;

    const token = localStorage.getItem('access_token');
    try {
        const response = await fetch(`${API_URL}/registry/files/${fileId}/deactivate`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to deactivate file');

        showNotification('File deactivated successfully', 'success');
        loadFiles();
        loadStats();
    } catch (error) {
        showNotification(error.message, 'error');
    }
}

// View file history (placeholder)
function viewFileHistory(fileId) {
    showNotification('History view coming soon', 'info');
}

// Show notification
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 0.5rem;
        color: white;
        font-weight: 500;
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(400px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(400px); opacity: 0; }
    }
    .state-badge { padding: 0.25rem 0.5rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .state-active { background: #d1fae5; color: #065f46; }
    .state-inactive { background: #f3f4f6; color: #374151; }
    .state-archived { background: #fee2e2; color: #991b1b; }
`;
document.head.appendChild(style);
