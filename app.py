from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, abort
import os
import yt_dlp
import threading
from queue import Queue
import uuid
import time
import zipfile
import re
from datetime import datetime
import shutil
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor
from werkzeug.utils import secure_filename

# Add missing imports for cross-platform folder opening
import sys
import subprocess

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'Uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB max file size

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Download status storage
download_status = {}
download_queue = Queue()
active_downloads = {}
download_history = []
current_folder = None # This will store the folder name for the current batch of downloads

# Initialize ThreadPoolExecutor with a lock
executor_lock = threading.Lock()
executor = None

def initialize_executor(max_workers=5):
    global executor
    with executor_lock:
        # Only re-create executor if it's None or max_workers has changed
        if executor is None:
            logger.info(f"Initializing new ThreadPoolExecutor with {max_workers} workers.")
            executor = ThreadPoolExecutor(max_workers=max_workers)
        elif hasattr(executor, '_max_workers') and executor._max_workers != max_workers:
            # If max_workers changes, it's safer to recreate the executor
            # This will wait for current tasks to finish before creating a new pool.
            # For a web app, dynamic worker count changes are often handled by restarting the app
            # or using a more complex task queue like Celery.
            logger.info(f"Max workers changed from {executor._max_workers} to {max_workers}. Shutting down old executor and initializing new one.")
            executor.shutdown(wait=True) # This will block only if there are tasks in the *old* executor
            executor = ThreadPoolExecutor(max_workers=max_workers)

# Initialize executor at startup
initialize_executor()

# Register a function to run when the application context is torn down (for graceful shutdown)
@app.teardown_appcontext
def shutdown_executor(exception=None):
    global executor
    with executor_lock:
        if executor:
            logger.info("Triggering ThreadPoolExecutor shutdown (non-blocking) on app teardown...")
            # CRITICAL FIX: Do NOT wait for tasks to complete here for UI responsiveness
            # In a production setup, you'd use a proper process manager (e.g., Gunicorn)
            # which handles graceful shutdown of worker processes.
            # For development, this prevents the main request thread from blocking.
            executor.shutdown(wait=False) # Changed to wait=False
            executor = None # Reset executor reference

class DownloadTask:
    def __init__(self, url, folder, cookie_file=None, filename_pattern=None):
        self.url = url
        self.folder = folder
        self.cookie_file = cookie_file
        self.filename_pattern = filename_pattern or "%(title)s.%(ext)s"
        self.status = "pending"
        self.progress = 0 # Percentage
        self.error = None
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.start_time = None
        self.task_id = str(uuid.uuid4())
        self.filename = None # Actual filename after download

def sanitize_folder_name(folder):
    """Sanitizes a string to be a safe folder name."""
    return re.sub(r'[^\w\s-]', '', folder).strip()

def validate_url(url):
    """Basic URL validation."""
    url_pattern = re.compile(
        r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*$'
    )
    return bool(url_pattern.match(url))

def is_social_media_url(url):
    """Checks if the URL belongs to a known social media platform requiring cookies."""
    return any(domain in url.lower() for domain in ['instagram.com', 'facebook.com'])

def download_video(task):
    """Executes the video download using yt-dlp."""
    try:
        task.start_time = time.time()
        output_path = os.path.join(app.config['DOWNLOAD_FOLDER'], task.folder)
        os.makedirs(output_path, exist_ok=True)
        
        ydl_opts = {
            'outtmpl': os.path.join(output_path, task.filename_pattern),
            'progress_hooks': [lambda d: update_progress(task, d)],
            'retries': 3,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True, # Disable yt-dlp's own progress bar in console
            'logger': logger,
        }
        
        if task.cookie_file:
            ydl_opts['cookiefile'] = task.cookie_file

        logger.info(f"Starting download for task {task.task_id}: {task.url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(task.url, download=True)
            # yt-dlp might return a list of files for playlists/multiple formats
            if '_type' in info and info['_type'] == 'playlist':
                # For playlists, filename might be complex, just use folder
                task.filename = f"Multiple files in {task.folder}"
            else:
                # Use the actual filename prepared by yt-dlp
                task.filename = ydl.prepare_filename(info)

            task.status = "completed"
            task.progress = 100
            logger.info(f"Completed download for task {task.task_id}: {task.url}")
            download_history.append({
                'url': task.url,
                'filename': task.filename,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), # Formatted timestamp
                'status': 'completed',
                'error': None
            })
            
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        task.progress = 0
        logger.error(f"Error downloading {task.url} (Task ID: {task.task_id}): {str(e)}")
        download_history.append({
            'url': task.url,
            'filename': task.filename,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), # Formatted timestamp
            'status': 'error',
            'error': str(e)
        })
    finally:
        # Clean up cookie file if it was uploaded for this task
        if task.cookie_file and os.path.exists(task.cookie_file):
            try:
                os.remove(task.cookie_file)
                logger.info(f"Deleted cookie file: {task.cookie_file}")
            except Exception as e:
                logger.error(f"Error deleting cookie file {task.cookie_file}: {e}")
        # Remove task from active_downloads once it's done (completed or error)
        if task.task_id in active_downloads:
            del active_downloads[task.task_id]


def update_progress(task, d):
    """Updates the progress of a download task."""
    if d['status'] == 'downloading':
        if d.get('total_bytes'):
            task.progress = d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 100
        elif d.get('total_bytes_estimate'):
            task.progress = d.get('downloaded_bytes', 0) / d.get('total_bytes_estimate', 1) * 100
        else:
            task.progress = d.get('downloaded_bytes', 0) / (task.downloaded_bytes + 1) * 100 # Fallback, not ideal
        
        task.downloaded_bytes = d.get('downloaded_bytes', 0)
        task.total_bytes = d.get('total_bytes', d.get('total_bytes_estimate', 0))
        task.status = "downloading" # Ensure status is 'downloading' during progress
    elif d['status'] == 'finished':
        task.progress = 100
        task.status = "completed"

def create_zip(folder):
    """Creates a ZIP archive of the specified download folder."""
    folder_path = os.path.join(app.config['DOWNLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        logger.warning(f"Attempted to zip non-existent folder: {folder_path}")
        return None
    
    zip_path = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{folder}.zip")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path) # Path inside the zip
                    zipf.write(file_path, arcname)
        logger.info(f"Successfully created zip file: {zip_path}")
        return zip_path
    except Exception as e:
        logger.error(f"Error creating zip for folder {folder}: {e}")
        return None

@app.route('/')
def index():
    """Renders the main index page."""
    return render_template('index.html')

@app.route('/start_download', methods=['POST'])
def start_download():
    """Initiates video downloads based on user input."""
    global download_status, download_history, current_folder, executor
    
    # Clear previous download status for a new batch, but keep history cumulative
    download_status = {}
    # download_history = [] # Keep this if you want history to be cleared on each new batch

    urls = request.form.get('urls', '').splitlines()
    # Use a default folder name if none is provided, ensuring it's unique
    folder = sanitize_folder_name(request.form.get('folder', f'streamsaver_downloads_{int(time.time())}'))
    filename_pattern = request.form.get('filename_pattern', '%(title)s.%(ext)s')
    auto_zip = 'auto_zip' in request.form
    skip_invalid = 'skip_invalid' in request.form
    max_workers = int(request.form.get('parallel_downloads', 5))
    
    # Reinitialize executor with new max_workers if needed (non-blocking here)
    initialize_executor(max_workers=max_workers)
    
    # Handle cookie file upload
    cookie_file = None
    has_social_media = any(is_social_media_url(url) for url in urls)
    if 'cookie_file' in request.files and request.files['cookie_file'].filename:
        file = request.files['cookie_file']
        filename = secure_filename(file.filename)
        cookie_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(cookie_path)
        cookie_file = cookie_path
    elif has_social_media:
        # If social media URL detected and no cookie file provided
        return jsonify({'status': 'error', 'message': 'Cookie file is required for Instagram or Facebook URLs'}), 400

    current_folder = folder # Set the current active download folder
    tasks_to_start = []
    for url_str in urls:
        url_str = url_str.strip()
        if not url_str:
            continue
        if not validate_url(url_str):
            if skip_invalid:
                download_history.append({
                    'url': url_str,
                    'filename': None,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'skipped',
                    'error': 'Invalid URL'
                })
                continue
            else:
                # If not skipping, return error immediately
                return jsonify({'status': 'error', 'message': f'Invalid URL: {url_str}'}), 400
                
        task = DownloadTask(url_str, folder, cookie_file, filename_pattern)
        download_status[task.task_id] = task # Add to global status dict
        tasks_to_start.append(task)

    if not tasks_to_start:
        return jsonify({'status': 'error', 'message': 'No valid URLs provided to start download'}), 400

    # Submit each download task directly to the ThreadPoolExecutor
    for task in tasks_to_start:
        active_downloads[task.task_id] = task # Add to active_downloads for real-time monitoring
        executor.submit(download_video, task) # Submit the task to run in a separate thread

    # If auto_zip is requested, record it for later processing (e.g., in get_progress)
    # The actual zip creation will happen when all downloads are complete.
    if auto_zip:
        # Store auto_zip preference for the current folder
        # This is a simple way; for multi-user, you'd need a more robust way
        # to associate auto_zip with a specific batch/folder.
        # For now, we'll just rely on `get_progress` to check for completion and then zip.
        pass

    return jsonify({
        'status': 'started',
        'task_ids': [task.task_id for task in tasks_to_start],
        'folder': current_folder # Return the folder name to the frontend
    })

@app.route('/progress')
def progress():
    """Renders the download progress page."""
    return render_template('progress.html')

@app.route('/get_progress')
def get_progress():
    """Provides real-time download statistics and task progress."""
    global current_folder
    
    # Calculate overall download speed for active downloads
    total_download_speed = 0
    for task in active_downloads.values():
        if task.status == 'downloading' and task.start_time:
            time_elapsed = time.time() - task.start_time
            if time_elapsed > 0:
                total_download_speed += task.downloaded_bytes / time_elapsed

    stats = {
        'total': len(download_status),
        'completed': sum(1 for task in download_status.values() if task.status == 'completed'),
        'skipped': sum(1 for item in download_history if item['status'] == 'skipped'),
        'errors': sum(1 for task in download_status.values() if task.status == 'error'),
        'pending': sum(1 for task in download_status.values() if task.status == 'pending' or task.status == 'downloading'), # Pending includes downloading
        'download_speed': total_download_speed / 1024 / 1024, # Convert to MB/s
        'tasks': [{
            'id': task.task_id,
            'url': task.url,
            'status': task.status,
            'progress': round(task.progress, 1), # Round progress for display
            'error': task.error,
            'filename': task.filename,
            'downloaded_bytes': task.downloaded_bytes,
            'total_bytes': task.total_bytes
        } for task in download_status.values()], # Send all tasks, not just active
        'folder': current_folder # Send the current folder name
    }

    # Check if all tasks for the current folder are completed to trigger auto-zip
    # This assumes auto_zip was requested for this batch.
    # A more robust solution would store auto_zip preference per folder/batch.
    # We'll check if the auto_zip checkbox was checked in the initial request
    # and if the zip file doesn't already exist.
    if current_folder and 'auto_zip' in request.form and \
       stats['total'] > 0 and \
       stats['completed'] + stats['errors'] + stats['skipped'] == stats['total']:
        
        zip_path_for_folder = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{current_folder}.zip")
        if not os.path.exists(zip_path_for_folder): # Prevent re-zipping
            logger.info(f"All downloads for folder '{current_folder}' complete. Attempting auto-zip.")
            created_zip = create_zip(current_folder)
            if created_zip:
                download_history.append({
                    'url': None,
                    'filename': created_zip,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'zip_created',
                    'error': None
                })
                logger.info(f"Auto-zip for '{current_folder}' completed.")
            else:
                download_history.append({
                    'url': None,
                    'filename': None,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'error',
                    'error': f'Failed to auto-create ZIP for {current_folder}'
                })
                logger.error(f"Auto-zip for '{current_folder}' failed.")
        
    return jsonify(stats)

@app.route('/clear_status', methods=['POST'])
def clear_status():
    """Clears all in-memory download status and history."""
    global download_status, download_history, current_folder
    download_status = {}
    download_history = []
    current_folder = None
    logger.info("Download status and history cleared.")
    return jsonify({'status': 'cleared'})

@app.route('/history')
def history():
    """Renders the download history page."""
    return render_template('history.html', history=download_history)

@app.route('/download_zip/<folder>')
def download_zip(folder):
    """Serves a ZIP archive of a specified download folder."""
    folder_path = os.path.join(app.config['DOWNLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        logger.warning(f"Download request for non-existent folder: {folder_path}")
        return jsonify({'error': 'Folder not found'}), 404
        
    zip_path = create_zip(folder)
    if zip_path:
        # Ensure the file exists before sending
        if os.path.exists(zip_path):
            return send_file(zip_path, as_attachment=True, download_name=f"{folder}.zip")
        else:
            logger.error(f"ZIP file was supposed to be created but not found: {zip_path}")
            return jsonify({'error': 'Failed to create ZIP file or file not found'}), 500
    logger.error(f"Failed to create ZIP for folder: {folder}")
    return jsonify({'error': 'Failed to create ZIP'}), 500

@app.route('/open_folder/<folder>')
def open_folder(folder):
    """Attempts to open the specified download folder on the user's system."""
    folder_path = os.path.join(app.config['DOWNLOAD_FOLDER'], folder)
    
    # Security check: Ensure the path is within the designated download folder
    abs_folder_path = os.path.abspath(folder_path)
    abs_download_root = os.path.abspath(app.config['DOWNLOAD_FOLDER'])
    
    if not abs_folder_path.startswith(abs_download_root):
        logger.warning(f"Attempted path traversal detected: {folder_path}")
        return jsonify({'error': 'Invalid folder path'}), 403 # Forbidden
    
    if not os.path.exists(folder_path):
        logger.warning(f"Attempted to open non-existent folder: {folder_path}")
        return jsonify({'error': 'Folder not found'}), 404
    
    try:
        if sys.platform == 'win32':
            os.startfile(folder_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder_path])
        else: # Linux/Unix
            subprocess.Popen(['xdg-open', folder_path])
        logger.info(f"Successfully attempted to open folder: {folder_path}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Failed to open folder {folder_path}: {e}")
        return jsonify({'error': f'Failed to open folder: {str(e)}'}), 500

# Add filename pattern validation (already present, keeping it)
def validate_filename_pattern(pattern):
    """Validates filename pattern to prevent path traversal."""
    if '../' in pattern or '..\\' in pattern:
        raise ValueError("Invalid filename pattern")

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False) # Set use_reloader to False in production for ThreadPoolExecutor
