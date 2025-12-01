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
