document.addEventListener('DOMContentLoaded', function () {
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
        window.location.href = '../public/login_index.html';
        return;
    }

    // Fetch user data and update UI
    fetch('http://localhost:5000/api/me', {
        headers: {
            'Authorization': `Bearer ${accessToken}`
        }
    })
        .then(response => {
            if (!response.ok) {
                localStorage.removeItem('access_token');
                window.location.href = '../public/login_index.html';
                throw new Error('Unauthorized or token expired');
            }
            return response.json();
        })
        .then(user => {
            document.body.setAttribute('data-user-role', user.role);
            document.getElementById('welcome-message').textContent = `Welcome, ${user.username}`;
            updateSidebar();
            updateDashboardCards(user.role);
        })
        .catch(error => {
            console.error('Error fetching user data:', error);
            showToast('Failed to load user data.', 'error');
        });

    // Event Listeners for sidebar navigation
    document.querySelectorAll('.sidebar-menu a').forEach(link => {
        link.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href.startsWith('#')) {
                e.preventDefault();
                document.querySelectorAll('.sidebar-menu a').forEach(l => l.classList.remove('active'));
                this.classList.add('active');
                const targetId = href.substring(1);
                showSection(targetId);

                // Refresh data based on section
                switch (targetId) {
                    case 'staff-management':
                        fetchUsers();
                        break;
                    case 'departments-units':
                        fetchDepartments();
                        break;
                    case 'roles-permissions':
                        fetchRoles();
                        break;
                    case 'audit-logs':
                        fetchAuditLogs();
                        break;
                    case 'dashboard':
                        fetchAnalyticsData();
                        fetchTotalUsers();
                        break;
                }
            }
        });
    });

    // Hamburger menu for mobile
    const mainHeader = document.querySelector('.main-header');
    const sidebar = document.querySelector('.sidebar');
    const hamburger = document.createElement('div');
    hamburger.classList.add('hamburger');
    hamburger.innerHTML = '<span></span><span></span><span></span>';
    mainHeader.insertBefore(hamburger, mainHeader.firstChild);

    // Create overlay for mobile drawer
    let sidebarOverlay = document.getElementById('sidebarOverlay');
    if (!sidebarOverlay) {
        sidebarOverlay = document.createElement('div'); sidebarOverlay.id = 'sidebarOverlay'; document.body.appendChild(sidebarOverlay);
    }

    function openSidebar() { sidebar.classList.add('active'); sidebarOverlay.classList.add('active'); document.body.style.overflow = 'hidden'; }
    function closeSidebar() { sidebar.classList.remove('active'); sidebarOverlay.classList.remove('active'); document.body.style.overflow = ''; }

    hamburger.addEventListener('click', () => {
        if (sidebar.classList.contains('active')) closeSidebar(); else openSidebar();
    });

    // clicking overlay closes the sidebar on mobile
    sidebarOverlay.addEventListener('click', () => { closeSidebar(); });

    // Close sidebar when clicking outside on mobile
    const mainContent = document.querySelector('.main-content');
    mainContent.addEventListener('click', () => {
        if (sidebar.classList.contains('active')) {
            closeSidebar();
        }
    });

    // Create User Button
    const createUserBtn = document.getElementById('create-user-btn');
    if (createUserBtn) {
        createUserBtn.addEventListener('click', () => openModal('create-user-modal'));
    }

    const addUserBtn = document.querySelector('#staff-management .btn-primary');
    if (addUserBtn) {
        addUserBtn.addEventListener('click', () => openModal('create-user-modal'));
    }

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            localStorage.removeItem('access_token');
            window.location.href = '../public/login_index.html';
        });
    }

    // Create User Form Submission
    const createUserForm = document.getElementById('create-user-form');
    if (createUserForm) {
        createUserForm.addEventListener('submit', handleCreateUser);
    }

    // Bulk Upload Button
    const bulkUploadBtn = document.getElementById('bulk-upload-btn');
    if (bulkUploadBtn) {
        bulkUploadBtn.addEventListener('click', handleBulkUpload);
    }

    // Add Department Form Submission
    const addDepartmentForm = document.getElementById('add-department-form');
    if (addDepartmentForm) {
        addDepartmentForm.addEventListener('submit', handleAddDepartment);
    }

    // Edit Department Form Submission
    const editDepartmentForm = document.getElementById('edit-department-form');
    if (editDepartmentForm) {
        editDepartmentForm.addEventListener('submit', handleEditDepartment);
    }

    // Reassign Head Form Submission
    const reassignHeadForm = document.getElementById('reassign-head-form');
    if (reassignHeadForm) {
        reassignHeadForm.addEventListener('submit', handleReassignHead);
    }

    // Edit User Form Submission
    const editUserForm = document.getElementById('edit-user-form');
    if (editUserForm) {
        editUserForm.addEventListener('submit', handleEditUser);
    }

    // Add event listener for Create New Role button
    const createRoleBtn = document.querySelector('#roles-permissions .header-actions .btn-primary');
    if (createRoleBtn) {
        createRoleBtn.addEventListener('click', () => createRole());
    }

    // Add event listener for Create Role Form Submission
    const createRoleForm = document.getElementById('create-role-form');
    if (createRoleForm) {
        createRoleForm.addEventListener('submit', handleCreateRole);
    }

    // Add event listener for Edit Role Form Submission
    const editRoleForm = document.getElementById('edit-role-form');
    if (editRoleForm) {
        editRoleForm.addEventListener('submit', handleEditRole);
    }

    // Initial display of dashboard section
    showSection('dashboard');

    // Fetch initial data for departments and staff
    fetchDepartments();
    fetchStaffForDropdowns();
    fetchUsers();
    fetchRoles();
    fetchRoles();
    fetchTotalUsers();
    fetchAnalyticsData(); // New function to load charts
    fetchAuditLogs(); // Fetch audit logs

    // Expose functions to global scope for onclick handlers
    window.editUser = editUser;
    window.toggleUserStatus = toggleUserStatus;
    window.deleteUser = deleteUser;
    window.editDepartment = editDepartment;
    window.reassignDepartmentHead = reassignDepartmentHead;
    window.deleteDepartment = deleteDepartment;
    window.editRole = editRole;
    window.deleteRole = deleteRole;
});

// Function to fetch and render audit logs
async function fetchAuditLogs() {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch('http://localhost:5000/api/audit-logs', {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        if (!response.ok) throw new Error('Failed to fetch audit logs');

        const logs = await response.json();
        const tbody = document.getElementById('audit-logs-table-body');
        if (tbody) {
            tbody.innerHTML = '';
            logs.forEach(log => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td>${new Date(log.timestamp).toLocaleString()}</td>
                    <td>${log.user || 'System'}</td>
                    <td>${log.action}</td>
                    <td>${log.details}</td>
                    <td>${log.ip_address || 'N/A'}</td>
                `;
            });
        }
    } catch (error) {
        console.error('Error loading audit logs:', error);
    }
}

// Function to fetch and render analytics data
async function fetchAnalyticsData() {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch('http://localhost:5000/api/analytics/stats', {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        if (!response.ok) throw new Error('Failed to fetch analytics');

        const data = await response.json();

        // Update Cards
        document.getElementById('active-files-count').textContent = data.active_files;
        document.getElementById('pending-approvals-count').textContent = data.pending_approvals;
        document.getElementById('overdue-tasks-count').textContent = data.overdue_tasks;

        // Render Charts
        renderDeptChart(data.files_per_department);
        renderTrendChart(data.files_over_time);
        renderStatusChart(data.status_distribution);

    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

function renderDeptChart(data) {
    const ctx = document.getElementById('deptChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.name),
            datasets: [{
                label: 'Files',
                data: data.map(d => d.count),
                backgroundColor: '#36A2EB'
            }]
        }
    });
}

function renderTrendChart(data) {
    const ctx = document.getElementById('trendChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.date),
            datasets: [{
                label: 'New Files',
                data: data.map(d => d.count),
                borderColor: '#4BC0C0',
                fill: false
            }]
        }
    });
}

function renderStatusChart(data) {
    const ctx = document.getElementById('statusChart').getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.map(d => d.status),
            datasets: [{
                data: data.map(d => d.count),
                backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']
            }]
        }
    });
}

// Function to fetch total users and update the dashboard card
async function fetchTotalUsers() {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch('http://localhost:5000/api/users/count', {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            throw new Error('Failed to fetch total users');
        }
        const data = await response.json();
        const totalUsersElement = document.querySelector('.card:nth-child(1) p');
        if (totalUsersElement) {
            // set data-count for animated counter and start animation
            totalUsersElement.setAttribute('data-count', String(data.total_users || 0));
            totalUsersElement.textContent = '0';
            animateNumber(totalUsersElement, Number(data.total_users || 0));
        }
    } catch (error) {
        console.error('Error fetching total users:', error);
        showToast('Failed to load total users count.', 'error');
    }
}

// Animate numeric value from 0 to target
function animateNumber(el, target, duration = 900) {
    if (!el) return; const start = 0; const range = target - start; if (range <= 0) { el.textContent = String(target); return; }
    const startTime = performance.now(); function tick(now) {
        const elapsed = now - startTime; const progress = Math.min(elapsed / duration, 1);
        const value = Math.floor(start + range * easeOutCubic(progress)); el.textContent = String(value);
        if (progress < 1) requestAnimationFrame(tick); else el.textContent = String(target);
    }
    requestAnimationFrame(tick);
}
function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

// Animate all dashboard card numbers (if they include numbers or data-count)
function animateDashboardCards() {
    document.querySelectorAll('.dashboard-cards .card p').forEach(p => {
        const dc = Number(p.getAttribute('data-count') || p.textContent.replace(/[^0-9]/g, '') || 0);
        p.textContent = '0'; animateNumber(p, dc);
    });
}

// Function to fetch and display departments
async function fetchDepartments() {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch('http://localhost:5000/api/departments', {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            console.error('Failed to fetch departments:', response.status, response.statusText);
            throw new Error('Failed to fetch departments');
        }
        const departments = await response.json();
        console.log('Fetched departments:', departments); // Log fetched departments
        const departmentsTableBody = document.querySelector('#departments-table tbody');
        departmentsTableBody.innerHTML = '';
        departments.forEach(dept => {
            const row = departmentsTableBody.insertRow();
            row.innerHTML = `
                <td>${dept.name}</td>
                <td>${dept.code}</td>
                <td>${dept.head_name || 'N/A'}</td>
                <td class="action-buttons">
                    <button class="btn-edit" onclick="editDepartment(${dept.id})"><i class="fas fa-edit"></i></button>
                    <button class="btn-deactivate" onclick="reassignDepartmentHead(${dept.id})"><i class="fas fa-user-tie"></i></button>
                    <button class="btn-delete" onclick="deleteDepartment(${dept.id})"><i class="fas fa-trash"></i></button>
                </td>
            `;
        });
    } catch (error) {
        console.error('Error fetching departments:', error);
        showToast('Failed to load departments.', 'error');
    }
}

// Function to fetch staff for dropdowns
async function fetchStaffForDropdowns() {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch('http://localhost:5000/api/users', {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            throw new Error('Failed to fetch staff for dropdowns');
        }
        const staff = await response.json();
        const departmentHeadSelect = document.getElementById('department-head');
        const editDepartmentHeadSelect = document.getElementById('edit-department-head');
        const reassignNewHeadSelect = document.getElementById('reassign-new-head');

        [departmentHeadSelect, editDepartmentHeadSelect, reassignNewHeadSelect].forEach(select => {
            if (select) {
                select.innerHTML = '<option value="">Select Head</option>';
                staff.forEach(s => {
                    const option = document.createElement('option');
                    option.value = s.id;
                    option.textContent = s.username;
                    select.appendChild(option);
                });
            }
        });
    } catch (error) {
        console.error('Error fetching staff for dropdowns:', error);
        showToast('Failed to load staff for dropdowns.', 'error');
    }
}

// Handle Add Department Form Submission
async function handleAddDepartment(e) {
    e.preventDefault();
    const accessToken = localStorage.getItem('access_token');
    const name = document.getElementById('department-name').value;
    const code = document.getElementById('department-code').value;
    const head_id = document.getElementById('department-head').value;

    try {
        const response = await fetch('http://localhost:5000/api/departments', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ name, code, head_id: head_id || null })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to add department');
        }
        showToast('Department added successfully!', 'success');
        closeModal('add-department-modal');
        document.getElementById('add-department-form').reset();
        fetchDepartments(); // Refresh the list
        fetchStaffForDropdowns(); // Refresh staff dropdowns as well
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error adding department:', error);
    }
}

// Handle Edit Department Form Submission
async function handleEditDepartment(e) {
    e.preventDefault();
    const accessToken = localStorage.getItem('access_token');
    const id = document.getElementById('edit-department-id').value;
    const name = document.getElementById('edit-department-name').value;
    const code = document.getElementById('edit-department-code').value;
    const head_id = document.getElementById('edit-department-head').value;

    try {
        const response = await fetch(`http://localhost:5000/api/departments/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ name, code, head_id: head_id || null })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to update department');
        }
        showToast('Department updated successfully!', 'success');
        closeModal('edit-department-modal');
        fetchDepartments(); // Refresh the list
        fetchStaffForDropdowns(); // Refresh staff dropdowns as well
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error updating department:', error);
    }
}

// Handle Reassign Head Form Submission
async function handleReassignHead(e) {
    e.preventDefault();
    const accessToken = localStorage.getItem('access_token');
    const departmentId = document.getElementById('reassign-department-id').value;
    const new_head_id = document.getElementById('reassign-new-head').value;

    try {
        const response = await fetch(`http://localhost:5000/api/departments/${departmentId}/reassign_head`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ new_head_id: new_head_id || null })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to reassign department head');
        }
        showToast('Department head reassigned successfully!', 'success');
        closeModal('reassign-head-modal');
        fetchDepartments(); // Refresh the list
        fetchStaffForDropdowns(); // Refresh staff dropdowns as well
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error reassigning department head:', error);
    }
}

// Open Edit Department Modal and pre-fill data
async function editDepartment(departmentId) {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch(`http://localhost:5000/api/departments/${departmentId}`, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            throw new Error('Failed to fetch department details');
        }
        const department = await response.json();
        document.getElementById('edit-department-id').value = department.id;
        document.getElementById('edit-department-name').value = department.name;
        document.getElementById('edit-department-code').value = department.code;
        document.getElementById('edit-department-head').value = department.head_id || '';
        openModal('edit-department-modal');
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error loading department for edit:', error);
    }
}

// Delete Department
async function deleteDepartment(departmentId) {
    if (!confirm('Are you sure you want to delete this department?')) {
        return;
    }
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch(`http://localhost:5000/api/departments/${departmentId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to delete department');
        }
        showToast('Department deleted successfully!', 'success');
        fetchDepartments(); // Refresh the list
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error deleting department:', error);
    }
}

// Open Reassign Head Modal
async function reassignDepartmentHead(departmentId) {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch(`http://localhost:5000/api/departments/${departmentId}`, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            throw new Error('Failed to fetch department details');
        }
        const department = await response.json();
        document.getElementById('reassign-department-id').value = department.id;
        document.getElementById('reassign-department-select').innerHTML = `<option value="${department.id}">${department.name}</option>`;
        document.getElementById('reassign-new-head').value = department.head_id || '';
        openModal('reassign-head-modal');
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error loading department for reassign head:', error);
    }
}

function updateSidebar() {
    const userRole = document.body.getAttribute('data-user-role');
    const sidebarLinks = document.querySelectorAll('.sidebar-menu a');

    const rolePermissions = {
        'admin': [
            '#dashboard', '#user-management', '#roles-permissions', '#departments-units',
            '#staff-management', '#file-management', '#document-flow', '#access-control',
            '#reports-analytics', '#notifications-alerts', '#audit-logs'
        ],
        'hod': [
            '#dashboard', '#staff-management', '#file-management', '#document-flow',
            '#reports-analytics', '#notifications-alerts'
        ],
        'staff': [
            '#dashboard', '#file-management', '#document-flow', '#notifications-alerts'
        ]
    };

    // Fallback: if userRole is not found, allow all links for debugging purposes
    const allowedLinks = rolePermissions[userRole] || Object.values(rolePermissions).flat();

    console.log('DEBUG: User Role:', userRole);
    console.log('DEBUG: Allowed Links:', allowedLinks);

    sidebarLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (allowedLinks.includes(href) || !href.startsWith('#')) { // Always show external links for now
            link.parentElement.style.display = 'list-item';
        } else {
            link.parentElement.style.display = 'none';
        }
    });
}

function updateDashboardCards(role) {
    // Example: Adjust card visibility or content based on role
    // For now, all cards are visible in the HTML. This function can be expanded
    // to fetch dynamic data based on the role.
}

function showSection(targetId) {
    const contentSections = document.querySelectorAll('.main-content .content-section');
    contentSections.forEach(section => {
        if (section.id === targetId) {
            section.style.display = 'block';
            section.classList.add('active');
        } else {
            section.style.display = 'none';
            section.classList.remove('active');
        }
    });
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('modal-show');

        // Load roles when opening create user modal
        if (modalId === 'create-user-modal') {
            fetchRoles();
        }
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('modal-show');
    }
}

window.onclick = function (event) {
    const modals = document.getElementsByClassName('modal');
    for (let i = 0; i < modals.length; i++) {
        if (event.target == modals[i]) {
            closeModal(modals[i].id);
        }
    }
}

function openTab(evt, tabName) {
    const tabContents = document.getElementsByClassName('tab-content');
    for (let i = 0; i < tabContents.length; i++) {
        tabContents[i].style.display = 'none';
    }

    const tabLinks = document.getElementsByClassName('tab-link');
    for (let i = 0; i < tabLinks.length; i++) {
        tabLinks[i].className = tabLinks[i].className.replace(' active', '');
    }

    document.getElementById(tabName).style.display = 'block';
    evt.currentTarget.classList.add('active');
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('notification-toast');
    if (toast) {
        toast.textContent = message;
        toast.className = 'toast show ' + type;
        setTimeout(() => {
            toast.className = toast.className.replace('show', '');
        }, 3000);
    }
}

function handleCreateUser(e) {
    e.preventDefault();
    const accessToken = localStorage.getItem('access_token');
    const username = document.getElementById('new-username').value;
    const email = document.getElementById('new-email').value;
    const password = document.getElementById('new-password').value;
    const role = document.getElementById('new-role').value;

    fetch('http://localhost:5000/api/admin/users', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${accessToken}`
        },
        body: JSON.stringify({ username, email, password, role })
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw new Error(err.error || err.message || 'Failed to create user'); });
            }
            return response.json();
        })
        .then(data => {
            showToast('User created successfully!', 'success');
            closeModal('create-user-modal');
            document.getElementById('create-user-form').reset();
            fetchUsers(); // Refresh the user list
            fetchStaffForDropdowns(); // Refresh staff dropdowns
        })
        .catch(error => {
            showToast(error.message, 'error');
            console.error('Error creating user:', error);
        });
}

// Function to fetch and display all users (staff)
async function fetchUsers() {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch('http://localhost:5000/api/users', {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            console.error('Failed to fetch users:', response.status, response.statusText);
            throw new Error('Failed to fetch users');
        }
        const users = await response.json();
        console.log('Fetched users:', users); // Log fetched users
        const staffTableBody = document.querySelector('#staff-management tbody');
        staffTableBody.innerHTML = ''; // Clear existing rows

        users.forEach(user => {
            const row = staffTableBody.insertRow();
            const statusClass = user.is_active ? 'status-active' : 'status-inactive';
            const statusText = user.is_active ? 'Active' : 'Inactive';
            const toggleIcon = user.is_active ? 'fa-toggle-on' : 'fa-toggle-off';

            row.innerHTML = `
                <td>${user.username}</td>
                <td>${user.email}</td>
                <td>${user.role}</td>
                <td><span class="${statusClass}">${statusText}</span></td>
                <td class="action-buttons">
                    <button class="btn-edit" onclick="editUser(${user.id})"><i class="fas fa-edit"></i></button>
                    <button class="btn-deactivate" onclick="toggleUserStatus(${user.id}, ${user.is_active})"><i class="fas ${toggleIcon}"></i></button>
                    <button class="btn-delete" onclick="deleteUser(${user.id})"><i class="fas fa-trash"></i></button>
                </td>
            `;
        });
    } catch (error) {
        console.error('Error fetching users:', error);
        showToast('Failed to load staff data.', 'error');
    }
}

// Function to fetch and display roles

async function fetchRoles() {

    const accessToken = localStorage.getItem('access_token');

    try {

        const response = await fetch('http://localhost:5000/api/roles', {

            headers: {

                'Authorization': `Bearer ${accessToken}`

            }

        });

        if (!response.ok) {
            console.error('Failed to fetch roles:', response.status, response.statusText);
            throw new Error('Failed to fetch roles');

        }

        const roles = await response.json();
        console.log('Fetched roles:', roles); // Log fetched roles

        const rolesTableBody = document.querySelector('#roles-permissions tbody');

        rolesTableBody.innerHTML = ''; // Clear existing rows



        roles.forEach(role => {

            const row = rolesTableBody.insertRow();

            row.innerHTML = `

                <td>${role.name}</td>

                <td>${role.description || 'N/A'}</td>

                <td>

                    <button class="btn-edit" onclick="editRole(${role.id})"><i class="fas fa-edit"></i></button>

                    <button class="btn-delete" onclick="deleteRole(${role.id})"><i class="fas fa-trash"></i></button>

                </td>

            `;

        });

        // Populate role dropdown in create user modal
        const roleSelect = document.getElementById('new-role');
        if (roleSelect) {
            roleSelect.innerHTML = '<option value="">-- Select Role --</option>';
            roles.forEach(role => {
                const option = document.createElement('option');
                option.value = role.name;  // Use role name, not ID
                option.textContent = role.name;
                roleSelect.appendChild(option);
            });
        }

    } catch (error) {

        console.error('Error fetching roles:', error);

        showToast('Failed to load roles data.', 'error');

    }

}



// Function to open create role modal and populate permissions
async function createRole() {
    const allPermissions = await fetchPermissions();
    populatePermissionCheckboxes('new-role-permissions', allPermissions);
    openModal('create-role-modal');
}

// Handle Create Role Form Submission
async function handleCreateRole(e) {
    e.preventDefault();
    const accessToken = localStorage.getItem('access_token');
    const name = document.getElementById('new-role-name').value;
    const description = document.getElementById('new-role-description').value;
    const selectedPermissions = Array.from(document.querySelectorAll('#new-role-permissions input[type="checkbox"]:checked'))
        .map(checkbox => parseInt(checkbox.value));

    try {
        const response = await fetch('http://localhost:5000/api/roles', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ name, description, permissions: selectedPermissions })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to create role');
        }
        showToast('Role created successfully!', 'success');
        closeModal('create-role-modal');
        document.getElementById('create-role-form').reset();
        fetchRoles(); // Refresh the list
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error creating role:', error);
    }
}

// Function to open edit role modal and populate permissions
async function editRole(roleId) {
    const accessToken = localStorage.getItem('access_token');
    try {
        // Fetch role details
        const roleResponse = await fetch(`http://localhost:5000/api/roles/${roleId}`, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!roleResponse.ok) {
            throw new Error('Failed to fetch role details');
        }
        const role = await roleResponse.json();

        // Fetch permissions assigned to this role
        const assignedPermissionsResponse = await fetch(`http://localhost:5000/api/roles/${roleId}/permissions`, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!assignedPermissionsResponse.ok) {
            throw new Error('Failed to fetch assigned permissions');
        }
        const assignedPermissions = await assignedPermissionsResponse.json();
        const assignedPermissionIds = assignedPermissions.map(p => p.id);

        // Fetch all available permissions
        const allPermissions = await fetchPermissions();

        // Populate modal fields
        document.getElementById('edit-role-id').value = role.id;
        document.getElementById('edit-role-name').value = role.name;
        document.getElementById('edit-role-description').value = role.description || '';
        populatePermissionCheckboxes('edit-role-permissions', allPermissions, assignedPermissionIds);

        openModal('edit-role-modal');
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error loading role for edit:', error);
    }
}

// Handle Edit Role Form Submission
async function handleEditRole(e) {
    e.preventDefault();
    const accessToken = localStorage.getItem('access_token');
    const roleId = document.getElementById('edit-role-id').value;
    const name = document.getElementById('edit-role-name').value;
    const description = document.getElementById('edit-role-description').value;
    const selectedPermissions = Array.from(document.querySelectorAll('#edit-role-permissions input[type="checkbox"]:checked'))
        .map(checkbox => parseInt(checkbox.value));

    try {
        const response = await fetch(`http://localhost:5000/api/roles/${roleId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ name, description, permissions: selectedPermissions })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to update role');
        }
        showToast('Role updated successfully!', 'success');
        closeModal('edit-role-modal');
        fetchRoles(); // Refresh the list
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error updating role:', error);
    }
}


const createRoleBtn = document.querySelector('#roles-permissions .header-actions .btn-primary');
if (createRoleBtn) {
    createRoleBtn.addEventListener('click', () => createRole());
}

// Add event listener for Create Role Form Submission
const createRoleForm = document.getElementById('create-role-form');
if (createRoleForm) {
    createRoleForm.addEventListener('submit', handleCreateRole);
}

// Add event listener for Edit Role Form Submission
const editRoleForm = document.getElementById('edit-role-form');
if (editRoleForm) {
    editRoleForm.addEventListener('submit', handleEditRole);
}

// Function to fetch all permissions
async function fetchPermissions() {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch('http://localhost:5000/api/permissions', {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            throw new Error('Failed to fetch permissions');
        }
        const permissions = await response.json();
        return permissions;
    } catch (error) {
        console.error('Error fetching permissions:', error);
        showToast('Failed to load permissions.', 'error');
        return [];
    }
}

// Function to populate permission checkboxes in a given container
function populatePermissionCheckboxes(containerId, allPermissions, assignedPermissionIds = []) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = ''; // Clear existing checkboxes

    allPermissions.forEach(perm => {
        const checkboxDiv = document.createElement('div');
        checkboxDiv.className = 'permission-item';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `perm-${containerId}-${perm.id}`;
        checkbox.name = 'permissions';
        checkbox.value = perm.id;
        if (assignedPermissionIds.includes(perm.id)) {
            checkbox.checked = true;
        }

        const label = document.createElement('label');
        label.htmlFor = `perm-${containerId}-${perm.id}`;
        label.textContent = perm.name;

        checkboxDiv.appendChild(checkbox);
        checkboxDiv.appendChild(label);
        container.appendChild(checkboxDiv);
    });
}





// Function to open Edit User Modal and pre-fill data
async function editUser(userId) {
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch(`http://localhost:5000/api/users/${userId}`, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            throw new Error('Failed to fetch user details');
        }
        const user = await response.json();
        document.getElementById('edit-user-id').value = user.id;
        document.getElementById('edit-username').value = user.username;
        document.getElementById('edit-email').value = user.email;
        document.getElementById('edit-role').value = user.role.toLowerCase(); // Ensure role matches option value
        openModal('edit-user-modal');
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error loading user for edit:', error);
    }
}

// Handle Edit User Form Submission
async function handleEditUser(e) {
    e.preventDefault();
    const accessToken = localStorage.getItem('access_token');
    const userId = document.getElementById('edit-user-id').value;
    const username = document.getElementById('edit-username').value;
    const email = document.getElementById('edit-email').value;
    const role = document.getElementById('edit-role').value;

    try {
        const response = await fetch(`http://localhost:5000/api/users/${userId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ username, email, role })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to update user');
        }
        showToast('User updated successfully!', 'success');
        closeModal('edit-user-modal');
        fetchUsers(); // Refresh the list
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error updating user:', error);
    }
}

// Toggle User Status (Activate/Deactivate)
async function toggleUserStatus(userId, currentStatus) {
    const newStatus = !currentStatus;
    const action = newStatus ? 'activate' : 'deactivate';
    if (!confirm(`Are you sure you want to ${action} this user?`)) {
        return;
    }

    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch(`http://localhost:5000/api/users/${userId}/status`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ is_active: newStatus })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to update user status');
        }
        showToast(`User ${action}d successfully!`, 'success');
        fetchUsers(); // Refresh the list
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error updating user status:', error);
    }
}

// Delete User
async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
        return;
    }
    const accessToken = localStorage.getItem('access_token');
    try {
        const response = await fetch(`http://localhost:5000/api/users/${userId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message || 'Failed to delete user');
        }
        showToast('User deleted successfully!', 'success');
        fetchUsers(); // Refresh the list
    } catch (error) {
        showToast(error.message, 'error');
        console.error('Error deleting user:', error);
    }
}