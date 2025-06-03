document.getElementById('downloadForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const formData = new FormData(this);
    
    try {
        const response = await fetch('/start_download', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (data.status === 'started') {
            window.location.href = '/progress';
        }
    } catch (error) {
        alert('Error starting download: ' + error.message);
    }
});