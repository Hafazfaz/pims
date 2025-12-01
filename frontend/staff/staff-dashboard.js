// Staff Dashboard JavaScript
// Handles authentication, profile loading, navigation, file upload, file list, document actions

document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '../public/login_index.html';
        return;
    }
    // Global state
    let currentUser = null;
    // Initialise UI
    (async () => {
        await loadProfile();
        setupNavigation();
        await populateHodDropdowns();
        setupUploadForms();
        // Load default section if any
        const activeSection = document.querySelector('.dashboard-section.active');
        if (activeSection && activeSection.id === 'my-files') {
            loadMyFiles();
        }
    })();
});

// ------------------- Profile -------------------
async function loadProfile() {
    const token = localStorage.getItem('access_token');
    try {
        const resp = await fetch('/api/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!resp.ok) throw new Error('Failed to load profile');
        const user = await resp.json();
        currentUser = user;
        document.getElementById('welcomeName').textContent = user.username || 'Staff Member';
        document.getElementById('headerUserName').textContent = user.username || '';
        const initials = (user.username || 'U').substring(0, 2).toUpperCase();
        document.querySelectorAll('.avatar, .user-avatar').forEach(el => el.textContent = initials);
    } catch (e) {
        console.error('Profile load error:', e);
    }
}

// ------------------- Navigation -------------------
function setupNavigation() {
    const navLinks = document.querySelectorAll('.sidebar nav a');
    const sections = document.querySelectorAll('.dashboard-section');
    navLinks.forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            // Logout handling
            if (link.id === 'logout-btn') {
                localStorage.removeItem('access_token');
                window.location.href = '/public/login_index.html';
                return;
            }
            // Activate link
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            // Show target section
            const target = link.getAttribute('data-section');
            sections.forEach(sec => {
                sec.classList.toggle('active', sec.id === target);
                if (sec.id === target && target === 'my-files') {
                    loadMyFiles();
                }
            });
        });
    });
}

// ------------------- HOD Dropdowns -------------------

async function populateHodDropdowns() {
    const token = localStorage.getItem('access_token');
    try {
        console.log('Fetching HODs...');
        const resp = await fetch('/api/staff/hods', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        console.log('HOD fetch status:', resp.status);
        if (!resp.ok) throw new Error('Failed to fetch HOD list: ' + resp.statusText);

        const hods = await resp.json();
        console.log('Fetched HODs payload:', hods);

        const singleSelect = document.getElementById('single-file-hod');
        const bulkSelect = document.getElementById('bulk-file-hod');
        console.log('Single select element:', singleSelect);
        console.log('Bulk select element:', bulkSelect);

        const resetSelect = (select) => {
            if (!select) return;
            select.innerHTML = '';
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select HOD';
            select.appendChild(placeholder);
        };
        resetSelect(singleSelect);
        resetSelect(bulkSelect);

        if (Array.isArray(hods) && hods.length > 0) {
            console.log(`Adding ${hods.length} HOD options to dropdowns`);
            hods.forEach((hod, index) => {
                console.log(`Adding HOD ${index}:`, hod);
                const opt = document.createElement('option');
                opt.value = hod.id;
                opt.textContent = hod.username;
                if (singleSelect) {
                    singleSelect.appendChild(opt.cloneNode(true));
                }
                if (bulkSelect) {
                    bulkSelect.appendChild(opt.cloneNode(true));
                }
            });
            console.log('Single select children:', singleSelect?.children.length);
            console.log('Bulk select children:', bulkSelect?.children.length);
        } else {
            console.warn('No HODs returned from API - adding fallback');
            const fallback = document.createElement('option');
            fallback.value = '999';
            fallback.textContent = 'Test HOD (Fallback)';
            if (singleSelect) singleSelect.appendChild(fallback);
            if (bulkSelect) bulkSelect.appendChild(fallback);
            alert('Warning: No HODs found. A fallback "Test HOD" has been added for testing.');
        }
    } catch (e) {
        console.error('Failed to load HOD list:', e);
        alert('Error loading HOD list: ' + e.message);
    }
}

// ------------------- Upload Forms -------------------
function setupUploadForms() {
    // Single file upload
    const singleForm = document.getElementById('single-upload-form');
    if (singleForm) {
        singleForm.addEventListener('submit', async e => {
            e.preventDefault();
            const formData = new FormData(singleForm);
            const fileInput = document.getElementById('single-file');
            if (!fileInput.files.length) {
                alert('Please select a file');
                return;
            }
            const hodSelect = document.getElementById('single-file-hod');
            const hodId = hodSelect ? hodSelect.value : '';
            if (!hodId) {
                alert('Please select a HOD');
                return;
            }
            formData.set('hod_id', hodId);
            console.log('Submitting file upload with FormData:', {
                'file': fileInput.files[0].name,
                'hod_id': hodId,
                'department': formData.get('department'),
                'category': formData.get('category')
            });
            try {
                console.log('Sending POST to /api/staff/submit_file...');
                const resp = await fetch('/api/staff/submit_file', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
                    body: formData
                });
                console.log('Upload response status:', resp.status);
                console.log('Upload response headers:', resp.headers);
                const result = await resp.json();
                console.log('Upload response body:', result);
                if (!resp.ok) throw new Error(result.error || 'Upload failed');
                alert('File uploaded successfully');
                singleForm.reset();
                // Reset HOD dropdown to default
                if (hodSelect) hodSelect.selectedIndex = 0;
                loadMyFiles();
            } catch (err) {
                console.error('Upload error:', err);
                console.error('Error type:', err.name);
                console.error('Error message:', err.message);
                alert('Error: ' + err.message);
            }
        });
    }

    // Bulk file upload
    const bulkForm = document.getElementById('bulk-upload-form');
    if (bulkForm) {
        bulkForm.addEventListener('submit', async e => {
            e.preventDefault();
            const filesInput = document.getElementById('bulk-files');
            if (!filesInput.files.length) {
                alert('Select at least one file');
                return;
            }
            const category = document.getElementById('bulk-file-category').value;
            const department = document.getElementById('bulk-file-department').value;
            const hodSelect = document.getElementById('bulk-file-hod');
            const hodId = hodSelect ? hodSelect.value : '';
            if (!hodId) {
                alert('Please select a HOD for bulk upload');
                return;
            }
            for (let i = 0; i < filesInput.files.length; i++) {
                const file = filesInput.files[i];
                const formData = new FormData();
                formData.append('file', file);
                formData.append('file_category', category);
                formData.append('department', department);
                formData.append('hod_id', hodId);
                try {
                    const resp = await fetch('/api/staff/submit_file', {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
                        body: formData
                    });
                    const result = await resp.json();
                    if (!resp.ok) throw new Error(result.error || 'Upload failed');
                } catch (err) {
                    console.error('Bulk upload error for file', file.name, err);
                    alert('Error uploading ' + file.name + ': ' + err.message);
                }
            }
            alert('Bulk upload completed');
            bulkForm.reset();
            if (hodSelect) hodSelect.selectedIndex = 0;
            loadMyFiles();
        });
    }
}

// ------------------- My Files -------------------
async function loadMyFiles() {
    const token = localStorage.getItem('access_token');
    const tbody = document.getElementById('my-files-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" class="text-center">Loading...</td></tr>';
    try {
        const resp = await fetch('/api/staff/files', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!resp.ok) throw new Error('Failed to load files');
        const files = await resp.json();
        if (files.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No files found.</td></tr>';
            return;
        }
        tbody.innerHTML = files.map(file => {
            const stateClass = `state-${file.file_state?.toLowerCase() || 'inactive'}`;
            const activationBtn = `<button class="btn-success btn-sm" onclick="requestActivation(${file.id})" title="Activate"><i class="fas fa-check"></i></button>`;
            const viewBtn = `<button class="btn-info btn-sm" onclick="openFileDetails(${file.id})" title="Open"><i class="fas fa-folder-open"></i></button>`;
            return `
                <tr>
                    <td><strong>${file.file_number || 'N/A'}</strong></td>
                    <td>${file.filename}</td>
                    <td>${file.file_category || 'N/A'}</td>
                    <td><span class="state-badge ${stateClass}">${file.file_state || 'Inactive'}</span></td>
                    <td>${file.department_name || 'N/A'}</td>
                    <td>${new Date(file.created_at).toLocaleDateString()}</td>
                    <td>${activationBtn}${viewBtn}</td>
                </tr>`;
        }).join('');
    } catch (e) {
        console.error('Load files error:', e);
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error loading files.</td></tr>';
    }
}

// ------------------- File Details -------------------
let currentFileIdForDoc = null;
async function openFileDetails(fileId) {
    currentFileIdForDoc = fileId;
    const token = localStorage.getItem('access_token');
    const modal = document.getElementById('file-details-modal');
    // Reset UI
    document.getElementById('detail-file-number').textContent = 'Loading...';
    document.getElementById('detail-file-name').textContent = '';
    document.getElementById('detail-file-state').textContent = '';
    document.getElementById('detail-file-location').textContent = '';
    document.getElementById('documents-tbody').innerHTML = '<tr><td colspan="5" class="text-center">Loading documents...</td></tr>';
    modal.classList.add('show');
    try {
        const fileResp = await fetch(`/api/files/${fileId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!fileResp.ok) throw new Error('Failed to fetch file');
        const file = await fileResp.json();
        document.getElementById('detail-file-number').textContent = file.file_number;
        document.getElementById('detail-file-name').textContent = file.filename;
        document.getElementById('detail-file-state').textContent = file.file_state;
        document.getElementById('detail-file-state').className = `badge state-${file.file_state?.toLowerCase()}`;
        document.getElementById('detail-file-location').textContent = file.current_location_user_id ? 'With User' : 'Registry';
        const createBtn = document.getElementById('create-doc-btn');
        if (file.file_state === 'Active') {
            createBtn.disabled = false;
            createBtn.title = 'Create new document';
        } else {
            createBtn.disabled = true;
            createBtn.title = 'File must be Active to add documents';
        }
        await loadDocuments(fileId);
    } catch (e) {
        console.error('Error loading file details:', e);
        alert('Failed to load file details');
        modal.classList.remove('show');
    }
}
function closeFileDetailsModal() {
    document.getElementById('file-details-modal').classList.remove('show');
    currentFileIdForDoc = null;
}
async function loadDocuments(fileId) {
    const token = localStorage.getItem('access_token');
    const tbody = document.getElementById('documents-tbody');
    try {
        const resp = await fetch(`/api/files/${fileId}/documents`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!resp.ok) throw new Error('Failed to load documents');
        const docs = await resp.json();
        if (docs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No documents found.</td></tr>';
            return;
        }
        tbody.innerHTML = docs.map(doc => `
            <tr>
                <td>${doc.title}</td>
                <td><span class="badge badge-secondary">${doc.type}</span></td>
                <td>${doc.created_by_name}</td>
                <td>${new Date(doc.created_at).toLocaleDateString()}</td>
                <td>
                    <button class="btn-info btn-sm" onclick="viewDocument(${doc.id})" title="View"><i class="fas fa-eye"></i></button>
                    <button class="btn-success btn-sm" onclick="sendToHod(${doc.id})" title="Send to HOD"><i class="fas fa-paper-plane"></i></button>
                </td>
            </tr>`).join('');
    } catch (e) {
        console.error('Error loading documents:', e);
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error: ${e.message}</td></tr>`;
    }
}
function viewDocument(docId) {
    alert('Document view feature coming soon.');
}
async function sendToHod(docId) {
    if (!confirm('Send this document to your HOD?')) return;
    const comment = prompt('Add a comment (optional):');
    const token = localStorage.getItem('access_token');
    try {
        const resp = await fetch(`/api/documents/${docId}/route`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ target_role: 'HOD', comment: comment || '' })
        });
        const result = await resp.json();
        if (!resp.ok) throw new Error(result.error || 'Failed to send');
        alert('Document sent to HOD successfully!');
        if (currentFileIdForDoc) await loadDocuments(currentFileIdForDoc);
    } catch (e) {
        console.error('Error sending document:', e);
        alert('Error: ' + e.message);
    }
}

// ------------------- Activation -------------------
let selectedFileId = null;
function requestActivation(fileId) {
    selectedFileId = fileId;
    document.getElementById('activation-modal').classList.add('show');
}
function closeActivationModal() {
    document.getElementById('activation-modal').classList.remove('show');
    selectedFileId = null;
}
async function submitActivationRequest() {
    const token = localStorage.getItem('access_token');
    const reason = document.getElementById('activation-reason').value.trim();
    if (!reason) { alert('Enter a reason'); return; }
    try {
        const resp = await fetch(`/api/staff/files/${selectedFileId}/request-activation`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ request_reason: reason })
        });
        const result = await resp.json();
        if (!resp.ok) throw new Error(result.error || 'Failed');
        alert('Activation request submitted.');
        closeActivationModal();
        loadMyFiles();
    } catch (e) {
        console.error('Activation error:', e);
        alert('Error: ' + e.message);
    }
}

// ------------------- Document Creation -------------------
function openCreateDocumentModal() {
    document.getElementById('create-document-form').reset();
    document.getElementById('doc-file-id').value = currentFileIdForDoc || '';
    document.getElementById('create-document-modal').classList.add('show');
}
function closeCreateDocumentModal() {
    document.getElementById('create-document-modal').classList.remove('show');
}
async function submitCreateDocument() {
    const token = localStorage.getItem('access_token');
    const title = document.getElementById('doc-title').value;
    const type = document.getElementById('doc-type').value;
    const content = document.getElementById('doc-content').value;
    const fileId = document.getElementById('doc-file-id').value;
    if (!title || !content) { alert('Fill required fields'); return; }
    try {
        const resp = await fetch('/api/documents', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: fileId, title, type, content })
        });
        const result = await resp.json();
        if (!resp.ok) throw new Error(result.error || 'Failed');
        alert('Document created');
        closeCreateDocumentModal();
        if (currentFileIdForDoc) await loadDocuments(currentFileIdForDoc);
    } catch (e) {
        console.error('Create doc error:', e);
        alert('Error: ' + e.message);
    }
}

// ------------------- Track Flow -------------------
async function trackFlow() {
    const token = localStorage.getItem('access_token');
    const input = document.getElementById('track-file-id').value.trim();
    const detailsDiv = document.getElementById('flow-details');
    if (!input) { alert('Enter File ID or name'); return; }
    detailsDiv.innerHTML = '<p style="text-align:center;">Searching...</p>';
    try {
        const searchResp = await fetch(`/api/files?search=${encodeURIComponent(input)}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const files = await searchResp.json();
        if (files.length === 0) { detailsDiv.innerHTML = '<p style="text-align:center;color:red;">File not found.</p>'; return; }
        const file = files[0];
        const histResp = await fetch(`/api/files/${file.id}/history`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const history = await histResp.json();
        let html = `<h3>Flow for: ${file.filename} (${file.file_number})</h3>`;
        html += '<div class="flow-timeline" style="margin-top:20px;">';
        if (history.length === 0) {
            html += '<p>No history recorded.</p>';
        } else {
            history.forEach(item => {
                html += `
                    <div class="flow-item" style="border-left:2px solid var(--primary-color);padding-left:20px;margin-bottom:20px;position:relative;">
                        <div style="position:absolute;left:-6px;top:0;width:10px;height:10px;border-radius:50%;background:var(--primary-color);"></div>
                        <div style="font-weight:bold;">${item.action.toUpperCase()}</div>
                        <div style="font-size:0.9rem;color:var(--text-muted);">${new Date(item.timestamp).toLocaleString()} by ${item.user}</div>
                        <div>${item.details}</div>
                    </div>`;
            });
        }
        html += '</div>';
        detailsDiv.innerHTML = html;
    } catch (e) {
        console.error('Track flow error:', e);
        detailsDiv.innerHTML = '<p style="text-align:center;color:red;">Error tracking file.</p>';
    }
}
// Bind track button
document.addEventListener('DOMContentLoaded', () => {
    const trackBtn = document.getElementById('search-flow-btn');
    if (trackBtn) trackBtn.addEventListener('click', trackFlow);
});
