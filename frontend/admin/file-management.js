document.addEventListener('DOMContentLoaded', () => {
    const uploadBtn = document.getElementById('upload-btn');
    const bulkUploadBtn = document.getElementById('bulk-upload-btn');
    const searchInput = document.getElementById('search-input');
    const categoryFilter = document.getElementById('category-filter');
    const departmentFilter = document.getElementById('department-filter');
    const fileTableBody = document.querySelector('#file-table tbody');

    // Modal elements
    const fileModal = document.getElementById('file-modal');
    const closeModalBtn = fileModal.querySelector('.close-button');
    const modalTitle = document.getElementById('modal-title');
    const fileForm = document.getElementById('file-form');
    const fileIdInput = document.getElementById('file-id');
    const singleFileInputGroup = document.getElementById('single-file-input-group');
    const fileInput = document.getElementById('file-input');
    const bulkFileInputGroup = document.getElementById('bulk-file-input-group');
    const bulkFilesInput = document.getElementById('bulk-files-input');
    const fileNameInput = document.getElementById('file-name');
    const fileCategoryInput = document.getElementById('file-category');
    const fileDepartmentInput = document.getElementById('file-department');
    const fileSensitivityInput = document.getElementById('file-sensitivity');
    const fileExpiresAtInput = document.getElementById('file-expires-at');
    const fileTagsInput = document.getElementById('file-tags');
    const submitFileBtn = document.getElementById('submit-file-btn');
    const cancelFileBtn = document.getElementById('cancel-file-btn');

    // History Modal elements
    const historyModal = document.getElementById('history-modal');
    const historyCloseButton = historyModal.querySelector('.history-close-button');
    const historyFileNameSpan = document.getElementById('history-file-name');
    const fileHistoryContent = document.getElementById('file-history-content');

    // Access Log Modal elements
    const accessLogModal = document.getElementById('access-log-modal');
    const accessLogCloseButton = accessLogModal.querySelector('.access-log-close-button');
    const accessLogFileNameSpan = document.getElementById('access-log-file-name');
    const fileAccessLogContent = document.getElementById('file-access-log-content');

    let editingFileId = null; // To keep track of which file is being edited
    let isBulkUpload = false; // To differentiate between single and bulk upload

    // --- API Endpoints (assuming Flask backend running on http://127.0.0.1:5000) ---
    const API_BASE_URL = 'http://127.0.0.1:5000/api';

    // Function to get JWT token (replace with actual token retrieval)
    const getAuthToken = () => {
        // In a real application, retrieve this from localStorage or a secure cookie
        return localStorage.getItem('access_token'); 
    };

    // Function to show notification toast
    const showToast = (message, type = 'success') => {
        const toast = document.getElementById('notification-toast');
        if (!toast) {
            console.warn('Notification toast element not found.');
            return;
        }
        toast.textContent = message;
        toast.className = `toast ${type} show`;
        setTimeout(() => {
            toast.className = toast.className.replace('show', '');
        }, 3000);
    };

    // Function to fetch departments for dropdowns
    const fetchDepartments = async () => {
        try {
            const token = getAuthToken();
            const response = await fetch(`${API_BASE_URL}/departments`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const departments = await response.json();
            populateDepartmentDropdowns(departments);
        } catch (error) {
            console.error('Error fetching departments:', error);
            showToast('Failed to load departments.', 'error');
        }
    };

    // Function to populate department dropdowns
    const populateDepartmentDropdowns = (departments) => {
        const departmentSelects = [departmentFilter, fileDepartmentInput];
        departmentSelects.forEach(selectElement => {
            // Clear existing options except the first one (e.g., "All Departments" or "Select Department")
            while (selectElement.children.length > 1) {
                selectElement.removeChild(selectElement.lastChild);
            }
            departments.forEach(dept => {
                const option = document.createElement('option');
                option.value = dept.id;
                option.textContent = dept.name;
                selectElement.appendChild(option);
            });
        });
    };

    // Function to fetch files from the backend
    const fetchFiles = async () => {
        try {
            const token = getAuthToken();
            const searchTerm = searchInput.value;
            const category = categoryFilter.value;
            const departmentId = departmentFilter.value;

            const queryParams = new URLSearchParams();
            if (searchTerm) queryParams.append('search', searchTerm);
            if (category) queryParams.append('category', category);
            if (departmentId) queryParams.append('department_id', departmentId);

            const response = await fetch(`${API_BASE_URL}/files?${queryParams.toString()}`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const files = await response.json();
            renderFiles(files);
        } catch (error) {
            console.error('Error fetching files:', error);
            showToast('Failed to load files.', 'error');
        }
    };

    // Function to render files in the table
    const renderFiles = (files) => {
        fileTableBody.innerHTML = ''; // Clear existing rows
        if (files.length === 0) {
            fileTableBody.innerHTML = '<tr><td colspan="10">No files found.</td></tr>';
            return;
        }

        files.forEach(file => {
            const row = fileTableBody.insertRow();
            row.dataset.fileId = file.id;
            row.innerHTML = `
                <td>${file.file_number || 'N/A'}</td>
                <td>${file.filename}</td>
                <td>${file.file_category}</td>
                <td>${file.department_name}</td>
                <td>${file.uploader_name}</td>
                <td>${file.sensitivity}</td>
                <td>${file.status}</td>
                <td>${file.expires_at ? new Date(file.expires_at).toLocaleDateString() : 'N/A'}</td>
                <td>${file.tags && file.tags.length > 0 ? file.tags.map(tag => `<span class="tag">${tag}</span>`).join('') : 'N/A'}</td>
                <td>
                    <button class="btn btn-sm btn-info download-btn" data-id="${file.id}" title="Download"><i class="fas fa-download"></i></button>
                    <button class="btn btn-sm btn-warning edit-btn" data-id="${file.id}" title="Edit"><i class="fas fa-edit"></i></button>
                    <button class="btn btn-sm btn-danger delete-btn" data-id="${file.id}" title="Delete"><i class="fas fa-trash"></i></button>
                    <button class="btn btn-sm btn-secondary history-btn" data-id="${file.id}" title="View History"><i class="fas fa-history"></i></button>
                    <button class="btn btn-sm btn-secondary access-log-btn" data-id="${file.id}" title="View Access Logs"><i class="fas fa-user-clock"></i></button>
                </td>
            `;
        });

        // Add event listeners for new buttons
        document.querySelectorAll('.download-btn').forEach(button => {
            button.addEventListener('click', handleDownload);
        });
        document.querySelectorAll('.edit-btn').forEach(button => {
            button.addEventListener('click', handleEdit);
        });
        document.querySelectorAll('.delete-btn').forEach(button => {
            button.addEventListener('click', handleDelete);
        });
        document.querySelectorAll('.history-btn').forEach(button => {
            button.addEventListener('click', handleHistory);
        });
        document.querySelectorAll('.access-log-btn').forEach(button => {
            button.addEventListener('click', handleAccessLogs);
        });
    };

    // --- Modal Operations ---
    const openModal = (mode = 'single') => {
        fileModal.classList.add('show-modal');
        if (mode === 'single') {
            singleFileInputGroup.style.display = 'block';
            bulkFileInputGroup.style.display = 'none';
            fileInput.required = true;
            bulkFilesInput.required = false;
            isBulkUpload = false;
        } else if (mode === 'bulk') {
            singleFileInputGroup.style.display = 'none';
            bulkFileInputGroup.style.display = 'block';
            fileInput.required = false;
            bulkFilesInput.required = true;
            isBulkUpload = true;
        }
    };

    const closeModal = () => {
        console.log('closeModal function called.');
        fileModal.classList.remove('show-modal');
        fileForm.reset(); // Clear form fields
        fileIdInput.value = '';
        editingFileId = null;
        modalTitle.textContent = 'Upload New File';
        submitFileBtn.textContent = 'Upload File';
        fileInput.required = true; // Default to single upload required
        bulkFilesInput.required = false;
        isBulkUpload = false;
        fileNameInput.removeAttribute('readonly'); // Make file name editable again
    };

    const openHistoryModal = (fileName, historyData) => {
        historyFileNameSpan.textContent = fileName;
        fileHistoryContent.innerHTML = ''; // Clear previous content
        if (historyData && historyData.length > 0) {
            const ul = document.createElement('ul');
            historyData.forEach(item => {
                const li = document.createElement('li');
                li.innerHTML = `<strong>${item.action}</strong> by ${item.user_name} on ${new Date(item.timestamp).toLocaleString()}`;
                if (item.details) {
                    li.innerHTML += ` - <em>${item.details}</em>`;
                }
                ul.appendChild(li);
            });
            fileHistoryContent.appendChild(ul);
        } else {
            fileHistoryContent.innerHTML = '<p>No history available for this file.</p>';
        }
        historyModal.classList.add('show-modal');
    };

    const closeHistoryModal = () => {
        historyModal.classList.remove('show-modal');
    };

    const openAccessLogModal = (fileName, accessLogsData) => {
        accessLogFileNameSpan.textContent = fileName;
        fileAccessLogContent.innerHTML = ''; // Clear previous content
        if (accessLogsData && accessLogsData.length > 0) {
            const ul = document.createElement('ul');
            accessLogsData.forEach(log => {
                const li = document.createElement('li');
                li.innerHTML = `Accessed by <strong>${log.user_name}</strong> on ${new Date(log.timestamp).toLocaleString()} (Action: ${log.action})`;
                ul.appendChild(li);
            });
            fileAccessLogContent.appendChild(ul);
        } else {
            fileAccessLogContent.innerHTML = '<p>No access logs available for this file.</p>';
        }
        accessLogModal.classList.add('show-modal');
    };

    const closeAccessLogModal = () => {
        accessLogModal.classList.remove('show-modal');
    };

    closeModalBtn.addEventListener('click', closeModal);
    cancelFileBtn.addEventListener('click', () => {
        console.log('Cancel button clicked.');
        closeModal();
    }); // Add event listener for the new cancel button
    window.addEventListener('click', (event) => {
        if (event.target === fileModal && fileModal.classList.contains('show-modal')) {
            closeModal();
        }
    });

    historyCloseButton.addEventListener('click', closeHistoryModal);
    window.addEventListener('click', (event) => {
        if (event.target === historyModal && historyModal.classList.contains('show-modal')) {
            closeHistoryModal();
        }
    });

    accessLogCloseButton.addEventListener('click', closeAccessLogModal);
    window.addEventListener('click', (event) => {
        if (event.target === accessLogModal && accessLogModal.classList.contains('show-modal')) {
            closeAccessLogModal();
        }
    });

    // --- Event Handlers ---

    // Handle "Upload Single File" button click
    uploadBtn.addEventListener('click', () => {
        modalTitle.textContent = 'Upload New File';
        submitFileBtn.textContent = 'Upload File';
        openModal('single');
    });

    // Handle "Bulk Upload Files" button click
    bulkUploadBtn.addEventListener('click', () => {
        modalTitle.textContent = 'Bulk Upload New Files';
        submitFileBtn.textContent = 'Bulk Upload';
        fileNameInput.value = ''; // Clear filename for bulk upload
        fileNameInput.setAttribute('readonly', 'readonly'); // Make file name read-only for bulk upload
        openModal('bulk');
    });

    // Handle file form submission (Upload/Update)
    fileForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const token = getAuthToken();
        if (!token) {
            showToast('Authentication token not found. Please log in.', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file_category', fileCategoryInput.value);
        formData.append('department_id', fileDepartmentInput.value);
        formData.append('sensitivity', fileSensitivityInput.value);
        formData.append('expires_at', fileExpiresAtInput.value);
        formData.append('tags', fileTagsInput.value);

        if (editingFileId) {
            // Update existing file
            if (fileNameInput.value) { // Only append file name if it's not empty (for single file edit)
                formData.append('file_name', fileNameInput.value);
            }
            // File input is hidden for edit, so no file is appended here unless explicitly re-uploaded
            try {
                const response = await fetch(`${API_BASE_URL}/files/${editingFileId}`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(Object.fromEntries(formData)), // PUT typically uses JSON body
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                showToast('File updated successfully!');
                closeModal();
                fetchFiles();
            } catch (error) {
                console.error('Error updating file:', error);
                showToast('Failed to update file.', 'error');
            }
        } else if (isBulkUpload) {
            // Bulk Upload new files
            if (bulkFilesInput.files.length === 0) {
                showToast('Please select files for bulk upload.', 'error');
                return;
            }
            for (let i = 0; i < bulkFilesInput.files.length; i++) {
                formData.append('files[]', bulkFilesInput.files[i]);
            }

            try {
                const response = await fetch(`${API_BASE_URL}/files/bulk`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData,
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const result = await response.json();
                if (response.status === 207) { // Multi-Status
                    showToast(`Bulk upload completed with some errors. Uploaded: ${result.uploaded.length}, Failed: ${result.errors.length}`, 'warning');
                    console.warn('Bulk upload errors:', result.errors);
                } else {
                    showToast('Files bulk uploaded successfully!');
                }
                closeModal();
                fetchFiles();
            } catch (error) {
                console.error('Error bulk uploading files:', error);
                showToast('Failed to bulk upload files.', 'error');
            }
        } else {
            // Upload single new file
            if (!fileInput.files[0]) {
                showToast('Please select a file to upload.', 'error');
                return;
            }
            formData.append('file', fileInput.files[0]);
            formData.append('file_name', fileNameInput.value); // File name is required for single upload

            try {
                const response = await fetch(`${API_BASE_URL}/files`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData,
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                showToast('File uploaded successfully!');
                closeModal();
                fetchFiles();
            } catch (error) {
                console.error('Error uploading file:', error);
                showToast('Failed to upload file.', 'error');
            }
        }
    });

    // Handle Download button click
    const handleDownload = async (event) => {
        const fileId = event.currentTarget.dataset.id;
        try {
            const token = getAuthToken();
            const response = await fetch(`${API_BASE_URL}/files/${fileId}/download`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const blob = await response.blob();
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'download';
            if (contentDisposition && contentDisposition.indexOf('attachment') !== -1) {
                const filenameRegex = new RegExp('filename\*?=(?:"([^"]+)"|'([^']+)'|([^;]+))');
                const matches = filenameRegex.exec(contentDisposition);
                if (matches != null && matches[1]) {
                    filename = matches[1].replace(/['"]/g, '');
                }
            }

            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            showToast('File download initiated.');
        } catch (error) {
            console.error('Error downloading file:', error);
            showToast('Failed to download file.', 'error');
        }
    };

    // Handle Edit button click
    const handleEdit = async (event) => {
        editingFileId = event.currentTarget.dataset.id;
        try {
            const token = getAuthToken();
            const response = await fetch(`${API_BASE_URL}/files/${editingFileId}`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const file = await response.json();

            modalTitle.textContent = 'Edit File';
            submitFileBtn.textContent = 'Save Changes';
            fileIdInput.value = file.id;
            fileNameInput.value = file.filename;
            fileNameInput.setAttribute('readonly', 'readonly'); // File name not editable during edit
            fileCategoryInput.value = file.file_category;
            fileDepartmentInput.value = file.department_id; // Assuming department_id is returned
            fileSensitivityInput.value = file.sensitivity;
            fileExpiresAtInput.value = file.expires_at ? file.expires_at.split('T')[0] : ''; // Format for date input
            fileTagsInput.value = file.tags ? file.tags.join(', ') : '';
            
            singleFileInputGroup.style.display = 'none'; // Hide file input when editing
            bulkFileInputGroup.style.display = 'none';
            fileInput.required = false; 
            bulkFilesInput.required = false;

            openModal();
        } catch (error) {
            console.error('Error fetching file for edit:', error);
            showToast('Failed to load file for editing.', 'error');
        }
    };

    // Handle Delete button click
    const handleDelete = async (event) => {
        const fileId = event.currentTarget.dataset.id;
        if (confirm('Are you sure you want to delete this file?')) {
            try {
                const token = getAuthToken();
                const response = await fetch(`${API_BASE_URL}/files/${fileId}`, {
                    method: 'DELETE',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                showToast('File deleted successfully!');
                fetchFiles();
            } catch (error) {
                console.error('Error deleting file:', error);
                showToast('Failed to delete file.', 'error');
            }
        }
    };

    // Handle View History button click
    const handleHistory = async (event) => {
        const fileId = event.currentTarget.dataset.id;
        const fileName = event.currentTarget.closest('tr').querySelector('td:nth-child(2)').textContent; // Get filename from table row
        try {
            const token = getAuthToken();
            const response = await fetch(`${API_BASE_URL}/files/${fileId}/history`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const history = await response.json();
            openHistoryModal(fileName, history);
        } catch (error) {
            console.error('Error fetching file history:', error);
            showToast('Failed to load file history.', 'error');
        }
    };

    // Handle View Access Logs button click
    const handleAccessLogs = async (event) => {
        const fileId = event.currentTarget.dataset.id;
        const fileName = event.currentTarget.closest('tr').querySelector('td:nth-child(2)').textContent; // Get filename from table row
        try {
            const token = getAuthToken();
            const response = await fetch(`${API_BASE_URL}/files/${fileId}/access_logs`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const accessLogs = await response.json();
            openAccessLogModal(fileName, accessLogs);
        } catch (error) {
            console.error('Error fetching file access logs:', error);
            showToast('Failed to load file access logs.', 'error');
        }
    };

    // Handle search input and filter changes
    searchInput.addEventListener('input', fetchFiles);
    categoryFilter.addEventListener('change', fetchFiles);
    departmentFilter.addEventListener('change', fetchFiles);

    // Initial fetches when the page loads
    fetchDepartments();
    fetchFiles();
});