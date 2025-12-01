// Production API base URL - update this for your deployment
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? '' // Local development - use relative paths
    : 'https://pims.fmcabuja.gov.ng'; // Production - use full URL

document.getElementById("loginForm").addEventListener("submit", function (e) {
    e.preventDefault();

    const usernameInput = document.getElementById("username");
    const passwordInput = document.getElementById("password");
    const errorMessageDiv = document.getElementById('errorMessage');
    const loginButton = document.querySelector(".btn");

    const originalButtonText = loginButton.textContent;
    loginButton.textContent = "Authenticating...";
    loginButton.disabled = true;

    const username = usernameInput.value;
    const password = passwordInput.value;

    fetch(`${API_BASE}/api/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    })
        .then(response => response.json())
        .then(data => {
            if (data.access_token) {
                localStorage.setItem('access_token', data.access_token);
                loginButton.textContent = "Login Successful ✓";
                loginButton.style.background = "#0da76e";

                console.log("Fetching user role...");
                fetch(`${API_BASE}/api/me`, {
                    headers: { 'Authorization': `Bearer ${data.access_token}` }
                })
                    .then(res => {
                        if (!res.ok) throw new Error(`Failed to fetch user info: ${res.status}`);
                        return res.json();
                    })
                    .then(user => {
                        console.log("User info received:", user);
                        setTimeout(() => {
                            // Redirect based on role
                            const role = user.role_name || user.role;
                            if (role === 'Admin') {
                                window.location.href = '../admin/dashboard.html';
                            } else if (role === 'HOD') {
                                window.location.href = '../hod/hod.html';
                            } else if (role === 'Registry') {
                                window.location.href = '../registry/registry-dashboard.html';
                            } else {
                                // Default to staff dashboard
                                window.location.href = '../staff/staff-dashboard.html';
                            }
                        }, 500);
                    })
                    .catch(err => {
                        console.error("Error fetching user info:", err);
                        loginButton.textContent = "Login Error";
                        loginButton.style.background = "#ff3333";
                        if (document.getElementById('errorMessage')) {
                            errorMessageDiv.textContent = "Login successful but failed to load user profile. Please try again.";
                        }
                    });
            } else {
                loginButton.textContent = originalButtonText;
                loginButton.disabled = false;
                loginButton.style.background = "#ff3333";
                if (document.getElementById('errorMessage')) {
                    errorMessageDiv.textContent = data.msg || data.error || 'Login failed. Please check your credentials.';
                }
                setTimeout(() => {
                    loginButton.style.background = "var(--fmc-green)";
                }, 2000);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            loginButton.textContent = originalButtonText;
            loginButton.disabled = false;
            loginButton.style.background = "#ff3333";
            if (document.getElementById('errorMessage')) {
                errorMessageDiv.textContent = 'An error occurred. Please try again later.';
            }
            setTimeout(() => {
                loginButton.style.background = "var(--fmc-green)";
            }, 2000);
        });
});

function togglePasswordVisibility() {
    const passwordInput = document.getElementById("password");
    const togglePasswordIcon = document.querySelector(".toggle-password");

    if (passwordInput.type === "password") {
        passwordInput.type = "text";
        togglePasswordIcon.classList.remove("fa-eye");
        togglePasswordIcon.classList.add("fa-eye-slash");
    } else {
        passwordInput.type = "password";
        togglePasswordIcon.classList.remove("fa-eye-slash");
        togglePasswordIcon.classList.add("fa-eye");
    }
}