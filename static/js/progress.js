document.addEventListener('DOMContentLoaded', () => {
    // Get references to DOM elements
    const totalSpan = document.getElementById('total');
    const completedSpan = document.getElementById('completed');
    const skippedSpan = document.getElementById('skipped');
    const errorsSpan = document.getElementById('errors');
    const pendingSpan = document.getElementById('pending');
    const speedSpan = document.getElementById('speed');
    const downloadZipBtn = document.getElementById('downloadZip');
    const openFolderBtn = document.getElementById('openFolder');
    const loadingSpinner = document.getElementById('loading-spinner');
    const noDownloadsMessage = document.getElementById('no-downloads-message');
    const taskList = document.getElementById('task-list');
    const completionToastElement = document.getElementById('completionToast');
    const toastCompletedSpan = document.getElementById('toast-completed');
    const toastFolderSpan = document.getElementById('toast-folder');

    let currentDownloadFolder = ''; // Stores the folder name for the current batch
    let allTasksCompleted = false; // Flag to ensure completion toast shows only once per batch
    let initialLoad = true; // Flag for initial page load state
    let progressInterval = null; // Variable to hold the interval ID

    // Function to display toast messages (reused from main.js for consistency)
    function showToast(message, type = 'success', title = 'Notification') {
        const toastContainer = document.getElementById('toastContainer'); // Assuming a global toastContainer
        if (!toastContainer) {
            console.error("Toast container with ID 'toastContainer' not found!");
            // Fallback to alert if container is missing, though it should be in progress.html
            alert(message); 
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

        const bsToast = new bootstrap.Toast(toastElement);
        bsToast.show();

        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }


    // Function to fetch and update progress data
    async function fetchProgress() {
        try {
            const response = await fetch('/get_progress');
            if (!response.ok) {
                console.error('Failed to fetch progress:', response.statusText);
                // Consider stopping polling or showing persistent error if backend is down
                return;
            }
            const data = await response.json();

            // Handle initial load state and "no downloads" message
            if (data.total === 0) { // No tasks at all
                loadingSpinner.classList.add('d-none');
                noDownloadsMessage.classList.remove('d-none');
                taskList.innerHTML = ''; // Clear tasks
                if (progressInterval) { // If polling is active, stop it
                    clearInterval(progressInterval);
                    progressInterval = null;
                    console.log("Polling stopped: No active downloads.");
                }
                allTasksCompleted = false; // Reset completion flag if no tasks
            } else { // There are tasks
                loadingSpinner.classList.add('d-none');
                noDownloadsMessage.classList.add('d-none');
                initialLoad = false;

                // Ensure polling is running if there are active tasks
                const currentlyActiveTasks = data.tasks.some(task => task.status === 'pending' || task.status === 'downloading');
                if (currentlyActiveTasks && !progressInterval) {
                    progressInterval = setInterval(fetchProgress, 2000);
                    console.log("Polling started/restarted: Active tasks detected.");
                }
            }


            // Update global statistics
            totalSpan.textContent = data.total;
            completedSpan.textContent = data.completed;
            skippedSpan.textContent = data.skipped;
            errorsSpan.textContent = data.errors;
            pendingSpan.textContent = data.pending;
            speedSpan.textContent = data.download_speed.toFixed(2); // Format to 2 decimal places

            currentDownloadFolder = data.folder; // Update current folder name

            // Enable/Disable and set links for action buttons
            if (currentDownloadFolder) {
                downloadZipBtn.disabled = false;
                openFolderBtn.disabled = false;
                downloadZipBtn.onclick = () => window.location.href = `/download_zip/${currentDownloadFolder}`;
                openFolderBtn.onclick = async () => {
                    try {
                        const openResponse = await fetch(`/open_folder/${currentDownloadFolder}`);
                        const result = await openResponse.json();
                        if (result.status !== 'success') {
                            console.error('Failed to open folder:', result.error);
                            showToast(`Failed to open folder: ${result.error}`, 'danger', 'Error');
                        } else {
                            showToast(`Attempting to open folder: ${currentDownloadFolder}`, 'info', 'Opening Folder');
                        }
                    } catch (err) {
                        console.error('Error opening folder:', err);
                        showToast(`Network error when trying to open folder: ${err.message}`, 'danger', 'Error');
                    }
                };
            } else {
                downloadZipBtn.disabled = true;
                openFolderBtn.disabled = true;
            }

            // Update individual task progress displays
            updateIndividualTasks(data.tasks);

            // Check for overall completion of the current batch
            const allTasksDone = data.total > 0 && (data.completed + data.errors + data.skipped) === data.total;
            if (allTasksDone && !allTasksCompleted) {
                allTasksCompleted = true; // Set flag to prevent multiple toasts
                
                // Stop polling when all tasks are done
                if (progressInterval) {
                    clearInterval(progressInterval);
                    progressInterval = null;
                    console.log("Polling stopped: All tasks completed.");
                }

                // Update toast content
                toastCompletedSpan.textContent = data.completed;
                toastFolderSpan.textContent = currentDownloadFolder || 'the downloads folder';

                // Show completion toast
                const bsToast = new bootstrap.Toast(completionToastElement);
                bsToast.show();
            } else if (!allTasksDone && allTasksCompleted) {
                // Reset completion flag if new tasks are added (e.g., user starts new downloads)
                allTasksCompleted = false;
                // If new tasks are detected after completion, restart polling
                if (!progressInterval && data.total > 0 && (data.completed + data.errors + data.skipped) < data.total) {
                    progressInterval = setInterval(fetchProgress, 2000);
                    console.log("Polling restarted: New tasks detected.");
                }
            }

        } catch (error) {
            console.error('Error fetching progress:', error);
            // Optionally show a general error toast here if polling fails repeatedly
            // Consider stopping polling if errors are persistent to avoid excessive requests
        }
    }

    // Function to update or create individual task elements
    function updateIndividualTasks(tasks) {
        // Use a map to keep track of existing task elements for efficient updates
        const existingTaskElements = new Map();
        taskList.querySelectorAll('.task-item').forEach(item => {
            existingTaskElements.set(item.dataset.taskId, item);
        });

        tasks.forEach(task => {
            let taskItem = existingTaskElements.get(task.id);

            if (!taskItem) {
                // Create new task item if it doesn't exist
                taskItem = document.createElement('div');
                taskItem.id = `task-${task.id}`;
                taskItem.className = 'card mb-3 task-item animate__fadeInUp'; // Add animation
                taskItem.dataset.taskId = task.id; // Store task ID for future lookup
                taskList.appendChild(taskItem);
            }

            // Determine badge class based on status
            let badgeClass = 'bg-secondary';
            if (task.status === 'completed') {
                badgeClass = 'bg-success';
            } else if (task.status === 'error') {
                badgeClass = 'bg-danger';
            } else if (task.status === 'downloading') {
                badgeClass = 'bg-primary';
            } else if (task.status === 'skipped') {
                badgeClass = 'bg-warning text-dark'; // Add text-dark for contrast on yellow
            } else if (task.status === 'zip_created') {
                badgeClass = 'bg-info';
            }

            // Determine progress bar text
            let progressBarText = `${task.progress.toFixed(1)}%`;
            if (task.status === 'completed') {
                progressBarText = 'Completed';
            } else if (task.status === 'error') {
                progressBarText = 'Error';
            } else if (task.status === 'pending') {
                progressBarText = 'Pending';
            } else if (task.status === 'skipped') {
                progressBarText = 'Skipped';
            } else if (task.status === 'zip_created') {
                progressBarText = 'ZIP Created';
            }

            // Format downloaded/total bytes
            const formatBytes = (bytes, decimals = 2) => {
                if (bytes === 0) return '0 Bytes';
                const k = 1024;
                const dm = decimals < 0 ? 0 : decimals;
                const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
            };

            const downloadedFormatted = formatBytes(task.downloaded_bytes);
            const totalFormatted = formatBytes(task.total_bytes);
            const sizeInfo = (task.status === 'downloading' || task.status === 'completed') && task.total_bytes > 0 ? `${downloadedFormatted} / ${totalFormatted}` : '';


            taskItem.innerHTML = `
                <div class="card-body">
                    <h6 class="card-title text-truncate" title="${task.url}">${task.url}</h6>
                    <p class="card-text text-muted small">${task.filename || 'Filename N/A'}</p>
                    <div class="progress mb-2" style="height: 25px; border-radius: 5px;">
                        <div class="progress-bar status-${task.status}" role="progressbar" 
                             style="width: ${task.progress}%;" 
                             aria-valuenow="${task.progress}" aria-valuemin="0" aria-valuemax="100">
                            ${progressBarText}
                        </div>
                    </div>
                    <div class="d-flex justify-content-between align-items-center small">
                        <span class="badge ${badgeClass}">
                            ${task.status.charAt(0).toUpperCase() + task.status.slice(1)}
                        </span>
                        <span class="text-muted">${sizeInfo}</span>
                        ${task.error ? `<span class="text-danger ms-2"><i class="bi bi-exclamation-triangle-fill"></i> ${task.error}</span>` : ''}
                    </div>
                </div>
            `;
            existingTaskElements.delete(task.id); // Remove from map as it's been processed
        });

        // Remove tasks that are no longer in the data (e.g., cleared)
        existingTaskElements.forEach(item => item.remove());
    }

    // Start polling immediately
    fetchProgress();
    // Do NOT set interval here directly. fetchProgress will manage it based on task status.
    // progressInterval = setInterval(fetchProgress, 2000); // Removed this line

    // Event listener for "View Details" button in completion toast
    completionToastElement.querySelector('.btn-primary').addEventListener('click', () => {
        // Navigate to history page
        window.location.href = '/history';
    });
});
