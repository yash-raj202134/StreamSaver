document.addEventListener('DOMContentLoaded', () => {
    const downloadForm = document.getElementById('downloadForm');
    const urlsTextarea = document.getElementById('urls');
    const urlCountSpan = document.getElementById('urlCount');

    // Function to display toast messages
    function showToast(message, type = 'success', title = 'Notification') {
        const toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) {
            console.error("Toast container with ID 'toastContainer' not found!");
            alert(message); // Fallback to alert if container is missing
            return;
        }

        const toastElement = document.createElement('div');
        toastElement.className = `toast align-items-center text-white bg-${type} border-0 show fade`;
        toastElement.setAttribute('role', 'alert');
        toastElement.setAttribute('aria-live', 'assertive');
        toastElement.setAttribute('aria-atomic', 'true');

        toastElement.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;

        toastContainer.appendChild(toastElement);

        // Initialize and show Bootstrap Toast
        const bsToast = new bootstrap.Toast(toastElement); // Assumes Bootstrap JavaScript is loaded
        bsToast.show();

        // Optional: Remove toast element from DOM after it hides
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }

    // Function to update URL count
    function updateUrlCount() {
        const urls = urlsTextarea.value.split('\n').filter(url => url.trim() !== '');
        urlCountSpan.textContent = urls.length;
    }

    // Event listener for URL textarea input
    if (urlsTextarea) {
        urlsTextarea.addEventListener('input', updateUrlCount);
        updateUrlCount(); // Initial count on page load
    }

    // Form submission handler
    if (downloadForm) {
        downloadForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitButton = this.querySelector('button[type="submit"]');
            const originalButtonContent = submitButton.innerHTML; // Store original HTML content

            // Client-side validation for URLs
            if (urlsTextarea && !urlsTextarea.value.trim()) {
                showToast('Please enter at least one URL to download.', 'warning', 'Validation Error');
                return; // Stop the function if no URLs are provided
            }

            // Show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Starting...`;

            const formData = new FormData(this);

            try {
                const response = await fetch('/start_download', {
                    method: 'POST',
                    body: formData
                });

                // Check for HTTP errors (e.g., 400, 500)
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || `Server error: ${response.status} ${response.statusText}`);
                }

                const data = await response.json();

                if (data.status === 'started') {
                    // Success, redirect to progress page
                    window.location.href = '/progress';
                } else {
                    // Handle unexpected successful responses from server
                    showToast('An unexpected issue occurred: ' + (data.message || 'Unknown response.'), 'danger', 'Error');
                    console.error('Unexpected server response:', data);
                }

            } catch (error) {
                // Catch network errors or errors thrown from response.ok check
                showToast('Error initiating download: ' + error.message, 'danger', 'Download Failed');
                console.error('Fetch error:', error);
            } finally {
                // Always reset button state
                submitButton.disabled = false;
                submitButton.innerHTML = originalButtonContent;
            }
        });
    } else {
        console.error("Download form with ID 'downloadForm' not found!");
    }
});
