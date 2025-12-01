document.addEventListener('DOMContentLoaded', function () {
    const addStaffBtn = document.getElementById('addStaffBtn');
    const staffModal = document.getElementById('staffModal');
    const closeModal = document.querySelector('.modal .close');
    const modalTitle = document.getElementById('modalTitle');
    const staffForm = document.getElementById('staffForm');
    const statusToggle = document.getElementById('status');
    const statusLabel = document.getElementById('statusLabel');

    // Open modal for adding staff
    addStaffBtn.addEventListener('click', () => {
        modalTitle.textContent = 'Add New Staff';
        staffForm.reset();
        statusLabel.textContent = 'Active';
        staffModal.style.display = 'block';
    });

    // Close modal
    closeModal.addEventListener('click', () => {
        staffModal.style.display = 'none';
    });

    // Close modal on outside click
    window.addEventListener('click', (event) => {
        if (event.target == staffModal) {
            staffModal.style.display = 'none';
        }
    });

    // Handle status toggle
    statusToggle.addEventListener('change', () => {
        if (statusToggle.checked) {
            statusLabel.textContent = 'Active';
        } else {
            statusLabel.textContent = 'Inactive';
        }
    });

    // Handle form submission (for now, just prevents default)
    staffForm.addEventListener('submit', (event) => {
        event.preventDefault();
        // In a real application, you would handle form submission here (e.g., via AJAX)
        alert('Staff profile saved!');
        staffModal.style.display = 'none';
    });

    // Add event listeners for edit buttons (delegated from the table body)
    document.querySelector('.table-container tbody').addEventListener('click', function(event) {
        const editButton = event.target.closest('.btn-edit');
        if (editButton) {
            // In a real app, you would fetch the staff data and populate the form
            modalTitle.textContent = 'Edit Staff Profile';
            staffModal.style.display = 'block';
        }
    });
});
