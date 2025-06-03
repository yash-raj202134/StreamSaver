let progressInterval;
const POLLING_TIMEOUT = 300000; // 5 minutes

async function updateProgress() {
    try {
        const response = await fetch('/get_progress');
        const data = await response.json();
        
        console.log('Progress data:', data);

        document.getElementById('total').textContent = data.total;
        document.getElementById('completed').textContent = data.completed;
        document.getElementById('skipped').textContent = data.skipped;
        document.getElementById('errors').textContent = data.errors;
        document.getElementById('pending').textContent = data.pending;
        document.getElementById('speed').textContent = data.download_speed.toFixed(2);

        const container = document.getElementById('progress-container');
        container.innerHTML = '';
        
        data.tasks.forEach(task => {
            const progressBar = `
                <div class="progress-container">
                    <div class="mb-1">${task.url}</div>
                    <div class="progress">
                        <div class="progress-bar status-${task.status}" 
                             role="progressbar" 
                             style="width: ${task.progress}%"
                             aria-valuenow="${task.progress}"
                             aria-valuemin="0" 
                             aria-valuemax="100">
                            ${task.status === 'error' ? task.error : `${Math.round(task.progress)}%`}
                        </div>
                    </div>
                </div>
            `;
            container.innerHTML += progressBar;
        });

        document.getElementById('loading-spinner').style.display = 'none';

        const allDone = data.pending === 0 && (data.completed > 0 || data.errors > 0 || data.skipped > 0);
        if (allDone) {
            console.log('All tasks done, showing toast:', data);
            clearInterval(progressInterval);
            try {
                const toastElement = document.getElementById('completionToast');
                const toastCompleted = toastElement.querySelector('#toast-completed');
                const toastFolder = toastElement.querySelector('#toast-folder');
                toastCompleted.textContent = data.completed;
                toastFolder.textContent = data.folder || 'downloads';
                const toast = new bootstrap.Toast(toastElement, { autohide: false });
                toast.show();
            } catch (e) {
                console.error('Toast failed:', e);
                alert(`Downloads completed! ${data.completed} videos to ${data.folder || 'downloads'}.`);
            }
            await fetch('/clear_status', { method: 'POST' });
        }
    } catch (error) {
        console.error('Error updating progress:', error);
    }
}

progressInterval = setInterval(updateProgress, 1000);
setTimeout(() => {
    if (progressInterval) {
        console.log('Polling timeout, stopping');
        clearInterval(progressInterval);
        alert('Download timed out. Check results or try again.');
        fetch('/clear_status', { method: 'POST' });
    }
}, POLLING_TIMEOUT);

document.getElementById('downloadZip').addEventListener('click', () => {
    const folder = document.getElementById('folder')?.value || 'downloads';
    window.location.href = `/download_zip/${folder}`;
});

document.getElementById('openFolder').addEventListener('click', async () => {
    const folder = document.getElementById('folder')?.value || 'downloads';
    try {
        const response = await fetch(`/open_folder/${folder}`);
        const data = await response.json();
        if (data.status !== 'success') {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        alert('Error opening folder: ' + error.message);
    }
});