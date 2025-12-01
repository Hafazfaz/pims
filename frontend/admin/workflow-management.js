document.addEventListener('DOMContentLoaded', function () {
    const createWorkflowBtn = document.getElementById('createWorkflowBtn');
    const workflowModal = document.getElementById('workflowModal');
    const closeModal = document.querySelector('#workflowModal .close');
    const addStepBtn = document.getElementById('addStepBtn');
    const workflowSteps = document.getElementById('workflowSteps');
    const visualizationContainer = document.getElementById('visualizationContainer');

    // Open modal for creating workflow
    createWorkflowBtn.addEventListener('click', () => {
        workflowModal.style.display = 'block';
    });

    // Close modal
    closeModal.addEventListener('click', () => {
        workflowModal.style.display = 'none';
    });

    // Close modal on outside click
    window.addEventListener('click', (event) => {
        if (event.target == workflowModal) {
            workflowModal.style.display = 'none';
        }
    });

    // Add new step to workflow
    addStepBtn.addEventListener('click', () => {
        const stepCount = workflowSteps.children.length;
        const newStep = document.createElement('div');
        newStep.classList.add('step');
        newStep.innerHTML = `
            <span>${stepCount}.</span>
            <input type="text" placeholder="e.g., HOD Approval">
            <button class="btn-remove-step"><i class="fas fa-minus"></i></button>
        `;
        workflowSteps.appendChild(newStep);
    });

    // Remove step from workflow
    workflowSteps.addEventListener('click', (e) => {
        if (e.target.closest('.btn-remove-step')) {
            e.target.closest('.step').remove();
            // Re-number steps
            const steps = workflowSteps.querySelectorAll('.step');
            steps.forEach((step, index) => {
                step.querySelector('span').textContent = `${index + 1}.`;
            });
        }
    });

    // Show visualization
    document.querySelectorAll('.btn-visualize').forEach(btn => {
        btn.addEventListener('click', () => {
            visualizationContainer.style.display = 'block';
        });
    });
});
