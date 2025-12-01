/**
 * HOD Document Inbox Functions
 * Add these functions to hod.js to enable document management
 */

const API_BASE = '/api';
let currentDocumentId = null;

/**
 * Load documents routed to HOD
 */
async function loadDocumentInbox() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/public/login_index.html';
        return;
    }

    try {
        console.log('Fetching HOD inbox...');
        const response = await fetch(`${API_BASE}/documents/inbox`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        console.log('Inbox fetch status:', response.status);

        if (!response.ok) throw new Error('Failed to load inbox');

        const documents = await response.json();
        console.log('Inbox payload:', documents);
        renderDocumentInbox(documents);

        // Update inbox count in overview
        const countEl = document.getElementById('inboxCount');
        if (countEl) countEl.textContent = documents.length;
    } catch (error) {
        console.error('Error loading document inbox:', error);
        showToast('Error loading documents', 'error');
    }
}

/**
 * Render document inbox table
 */
function renderDocumentInbox(documents) {
    const tbody = document.getElementById('inboxBody');
    console.log('Inbox tbody element:', tbody);
    if (!tbody) return;

    if (documents.length === 0) {
        console.log('No documents to render');
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:40px; color: var(--text-muted);">No documents in inbox</td></tr>';
        return;
    }
    console.log(`Rendering ${documents.length} documents`);

    tbody.innerHTML = documents.map(doc => `
        <tr>
            <td><input type="checkbox" class="select-item" data-id="${doc.id}"></td>
            <td>${doc.title}</td>
            <td>${doc.from_user}</td>
            <td>${new Date(doc.received_at).toLocaleDateString()}</td>
            <td><span class="badge badge-primary">Pending</span></td>
            <td>
                <button class="btn btn-sm primary" onclick="viewFileWorkflow(${doc.id}, ${doc.workflow_id})" title="View">
                    <i class="fas fa-eye"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

/**
 * View file workflow details
 */
let currentWorkflowId = null;
async function viewFileWorkflow(fileId, workflowId) {
    const token = localStorage.getItem('access_token');
    currentDocumentId = fileId;
    currentWorkflowId = workflowId;

    try {
        // Fetch file details (not document, since inbox contains files)
        const response = await fetch(`${API_BASE}/files/${fileId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to load file details');

        const file = await response.json();
        renderFileDetails(file);
        showModal('documentDetailsModal');
    } catch (error) {
        console.error('Error loading file details:', error);
        showToast('Error loading file details', 'error');
    }
}

/**
 * Render document details in modal
 */
function renderDocumentDetails(doc) {
    document.getElementById('docDetailTitle').textContent = doc.title;
    document.getElementById('docDetailFileNumber').textContent = doc.file_number;
    document.getElementById('docDetailType').textContent = doc.type;
    document.getElementById('docDetailCreator').textContent = doc.created_by_name;
    document.getElementById('docDetailContent').textContent = doc.content;

    // Render workflow history
    const timeline = document.getElementById('docWorkflowTimeline');
    if (doc.workflow_history && doc.workflow_history.length > 0) {
        timeline.innerHTML = doc.workflow_history.map(item => `
            <div style="margin-bottom: 20px; position: relative;">
                <div style="position: absolute; left: -25px; top: 0; width: 12px; height: 12px; border-radius: 50%; background: var(--primary-color); border: 3px solid white;"></div>
                <div style="background: #f8fafc; padding: 12px; border-radius: 6px; border-left: 3px solid var(--primary-color);">
                    <div style="font-weight: 600; text-transform: uppercase; font-size: 0.85rem; color: var(--primary-color);">${item.action}</div>
                    <div style="font-size: 0.9rem; color: var(--text-muted); margin-top: 3px;">
                        ${new Date(item.created_at).toLocaleString()} by ${item.from_user || 'System'}
                    </div>
                    ${item.comment ? `<div style="margin-top: 8px; font-style: italic;">"${item.comment}"</div>` : ''}
                    ${item.to_user ? `<div style="margin-top: 5px; font-size: 0.85rem;">→ Sent to <strong>${item.to_user}</strong></div>` : ''}
                </div>
            </div>
        `).join('');
    } else {
        timeline.innerHTML = '<p style="color: var(--text-muted);">No workflow history available.</p>';
    }
}

/**
 * Render file details in modal
 */
function renderFileDetails(file) {
    document.getElementById('docDetailTitle').textContent = file.filename || 'File';
    document.getElementById('docDetailFileNumber').textContent = file.file_number || 'N/A';
    document.getElementById('docDetailType').textContent = file.file_category || 'File';
    document.getElementById('docDetailCreator').textContent = file.uploader_name || 'Unknown';
    document.getElementById('docDetailContent').textContent = `File State: ${file.file_state}\nDepartment: ${file.department_name || 'N/A'}\nUploaded: ${new Date(file.created_at).toLocaleString()}`;

    // Render workflow history (if available)
    const timeline = document.getElementById('docWorkflowTimeline');
    timeline.innerHTML = '<p style="color: var(--text-muted);">File workflow history not yet implemented.</p>';
}

/**
 * Approve workflow
 */
async function approveDocument() {
    if (!currentWorkflowId) {
        showToast('No workflow selected', 'error');
        return;
    }

    const comment = prompt('Add a comment (optional):');
    await performWorkflowAction('approved', comment);
}

/**
 * Reject workflow
 */
async function rejectDocument() {
    if (!currentWorkflowId) {
        showToast('No workflow selected', 'error');
        return;
    }

    const comment = prompt('Reason for rejection:');
    if (!comment) {
        showToast('Comment required for rejection', 'warn');
        return;
    }

    await performWorkflowAction('rejected', comment);
}

/**
 * Perform workflow action (approve/reject)
 */
async function performWorkflowAction(status, comment) {
    const token = localStorage.getItem('access_token');

    try {
        const payload = { status, comment: comment || '' };

        const response = await fetch(`${API_BASE}/workflows/${currentWorkflowId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok) throw new Error(result.error || 'Action failed');

        showToast(result.message || `Workflow ${status}`, 'success');
        closeModal('documentDetailsModal');
        loadDocumentInbox(); // Refresh inbox
    } catch (error) {
        console.error('Error performing workflow action:', error);
        showToast('Error: ' + error.message, 'error');
    }
}

/**
 * Helper: Show modal
 */
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.setAttribute('aria-hidden', 'false');
        modal.style.display = 'flex';
    }
}

/**
 * Helper: Close modal
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.setAttribute('aria-hidden', 'true');
        modal.style.display = 'none';
    }
}

/**
 * Helper: Show toast notification
 */
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.textContent = message;
        toast.className = `toast toast-${type}`;
        toast.hidden = false;
        setTimeout(() => toast.hidden = true, 3000);
    } else {
        alert(message);
    }
}

// Attach event listeners when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Attach modal action handlers if modal exists
    const approveBtn = document.getElementById('docActionApprove');
    const rejectBtn = document.getElementById('docActionReject');

    if (approveBtn) approveBtn.addEventListener('click', approveDocument);
    if (rejectBtn) rejectBtn.addEventListener('click', rejectDocument);
});

// Make functions globally available for HOD dashboard to use
window.loadDocumentInbox = loadDocumentInbox;
window.viewFileWorkflow = viewFileWorkflow;
