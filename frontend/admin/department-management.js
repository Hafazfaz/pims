document.addEventListener('DOMContentLoaded', () => {
    const departmentsSection = document.getElementById('departments-units');
    if (!departmentsSection) return;

    const addDepartmentBtn = departmentsSection.querySelector('.btn-primary');
    const departmentModal = document.getElementById('add-department-modal');
    const closeModalBtn = departmentModal.querySelector('.close-button');
    const departmentForm = document.getElementById('add-department-form');
    const departmentsTableBody = departmentsSection.querySelector('#departments-table tbody');
    const modalTitle = departmentModal.querySelector('.modal-header h2');
    const saveDepartmentBtn = departmentModal.querySelector('.btn-primary');
    const departmentSearch = document.getElementById('department-search');

    let editingDepartmentId = null;
    let allDepartments = [];

    const fetchDepartments = async () => {
        try {
            const response = await fetch('/api/departments', {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
                }
            });
            if (!response.ok) {
                throw new Error('Failed to fetch departments');
            }
            allDepartments = await response.json();
            renderDepartments(allDepartments);
        } catch (error) {
            console.error('Error fetching departments:', error);
        }
    };

    const renderDepartments = (departments) => {
        departmentsTableBody.innerHTML = '';
        departments.forEach(department => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${department.name}</td>
                <td>${department.code}</td>
                <td>${department.head_name || 'N/A'}</td>
                <td class="action-buttons">
                    <button class="btn-edit" data-id="${department.id}"><i class="fas fa-edit"></i></button>
                    <button class="btn-delete" data-id="${department.id}"><i class="fas fa-trash"></i></button>
                </td>
            `;
            departmentsTableBody.appendChild(row);
        });
    };

    const openDepartmentModal = (title, department = null) => {
        modalTitle.textContent = title;
        if (department) {
            editingDepartmentId = department.id;
            departmentForm.querySelector('#department-name').value = department.name;
            departmentForm.querySelector('#department-code').value = department.code;
            saveDepartmentBtn.textContent = 'Update';
        } else {
            editingDepartmentId = null;
            departmentForm.reset();
            saveDepartmentBtn.textContent = 'Save';
        }
        departmentModal.style.display = 'block';
    };

    const closeDepartmentModal = () => {
        departmentModal.style.display = 'none';
    };

    addDepartmentBtn.addEventListener('click', () => openDepartmentModal('Add Department'));
    closeModalBtn.addEventListener('click', closeDepartmentModal);

    departmentForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const departmentData = {
            name: departmentForm.querySelector('#department-name').value,
            code: departmentForm.querySelector('#department-code').value
        };

        try {
            let response;
            const url = editingDepartmentId ? `/api/departments/${editingDepartmentId}` : '/api/departments';
            const method = editingDepartmentId ? 'PUT' : 'POST';

            response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
                },
                body: JSON.stringify(departmentData)
            });

            if (!response.ok) {
                throw new Error('Failed to save department');
            }

            closeDepartmentModal();
            fetchDepartments();
        } catch (error) {
            console.error('Error saving department:', error);
        }
    });

    departmentsTableBody.addEventListener('click', async (event) => {
        const target = event.target.closest('button');
        if (!target) return;

        const departmentId = target.dataset.id;

        if (target.classList.contains('btn-edit')) {
            const response = await fetch(`/api/departments/${departmentId}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
                }
            });
            const department = await response.json();
            openDepartmentModal('Edit Department', department);
        } else if (target.classList.contains('btn-delete')) {
            if (confirm('Are you sure you want to delete this department?')) {
                try {
                    const response = await fetch(`/api/departments/${departmentId}`, {
                        method: 'DELETE',
                        headers: {
                            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
                        }
                    });
                    if (!response.ok) {
                        throw new Error('Failed to delete department');
                    }
                    fetchDepartments();
                } catch (error) {
                    console.error('Error deleting department:', error);
                }
            }
        }
    });

    departmentSearch.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const filteredDepartments = allDepartments.filter(department =>
            department.name.toLowerCase().includes(searchTerm) ||
            department.code.toLowerCase().includes(searchTerm)
        );
        renderDepartments(filteredDepartments);
    });

    // Only fetch departments if the departments section is visible
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.attributeName === 'class' && departmentsSection.classList.contains('active')) {
                fetchDepartments();
            }
        });
    });

    observer.observe(departmentsSection, { attributes: true });

    // Initial fetch if the section is already active
    if (departmentsSection.classList.contains('active')) {
        fetchDepartments();
    }
});