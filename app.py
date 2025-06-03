from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
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

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'Uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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
current_folder = None

# Initialize ThreadPoolExecutor with a lock
executor_lock = threading.Lock()
executor = None

def initialize_executor(max_workers=5):
    global executor
    with executor_lock:
        if executor is None:
            executor = ThreadPoolExecutor(max_workers=max_workers)

# Initialize executor at startup
initialize_executor()

class DownloadTask:
    def __init__(self, url, folder, cookie_file=None, filename_pattern=None):
        self.url = url
        self.folder = folder
        self.cookie_file = cookie_file
        self.filename_pattern = filename_pattern or "%(title)s.%(ext)s"
        self.status = "pending"
        self.progress = 0
        self.error = None
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.start_time = None
        self.task_id = str(uuid.uuid4())
        self.filename = None

def sanitize_folder_name(folder):
    return re.sub(r'[^\w\s-]', '', folder).strip()

def validate_url(url):
    url_pattern = re.compile(
        r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*$'
    )
    return bool(url_pattern.match(url))

def is_social_media_url(url):
    return any(domain in url.lower() for domain in ['instagram.com', 'facebook.com'])

def download_video(task):
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
            'noprogress': True,
            'logger': logger,
        }
        
        if task.cookie_file:
            ydl_opts['cookiefile'] = task.cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(task.url, download=True)
            task.filename = ydl.prepare_filename(info)
            task.status = "completed"
            task.progress = 100
            download_history.append({
                'url': task.url,
                'filename': task.filename,
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            })
            
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        task.progress = 0
        logger.error(f"Error downloading {task.url}: {str(e)}")
        download_history.append({
            'url': task.url,
            'filename': task.filename,
            'timestamp': datetime.now().isoformat(),
            'status': 'error',
            'error': str(e)
        })

def update_progress(task, d):
    if d['status'] == 'downloading':
        task.progress = d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 100
        task.downloaded_bytes = d.get('downloaded_bytes', 0)
        task.total_bytes = d.get('total_bytes', 0)
    elif d['status'] == 'finished':
        task.progress = 100
        task.status = "completed"

def create_zip(folder):
    folder_path = os.path.join(app.config['DOWNLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        return None
    zip_path = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{folder}.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                zipf.write(os.path.join(root, file), 
                         os.path.relpath(os.path.join(root, file), folder_path))
    return zip_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_download', methods=['POST'])
def start_download():
    global download_status, download_history, current_folder
    download_status = {}
    download_history = []
    
    urls = request.form.get('urls', '').splitlines()
    folder = sanitize_folder_name(request.form.get('folder', f'downloads_{int(time.time())}'))
    filename_pattern = request.form.get('filename_pattern', '%(title)s.%(ext)s')
    auto_zip = 'auto_zip' in request.form
    skip_invalid = 'skip_invalid' in request.form
    max_workers = int(request.form.get('parallel_downloads', 5))
    
    # Reinitialize executor with new max_workers
    initialize_executor(max_workers=max_workers)
    
    # Handle cookie file
    cookie_file = None
    has_social_media = any(is_social_media_url(url) for url in urls)
    if 'cookie_file' in request.files and request.files['cookie_file'].filename:
        file = request.files['cookie_file']
        filename = secure_filename(file.filename)
        cookie_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(cookie_path)
        cookie_file = cookie_path
    elif has_social_media:
        return jsonify({'status': 'error', 'message': 'Cookie file is required for Instagram or Facebook URLs'}), 400

    current_folder = folder
    tasks = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        if not validate_url(url):
            if skip_invalid:
                download_history.append({
                    'url': url,
                    'filename': None,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'skipped',
                    'error': 'Invalid URL'
                })
                continue
            else:
                return jsonify({'status': 'error', 'message': f'Invalid URL: {url}'}), 400
                
        task = DownloadTask(url, folder, cookie_file, filename_pattern)
        download_status[task.task_id] = task
        tasks.append(task)
        download_queue.put(task)

    if not tasks:
        return jsonify({'status': 'error', 'message': 'No valid URLs provided'}), 400

    with executor_lock:
        for _ in range(min(max_workers, len(tasks))):
            executor.submit(process_queue)

    # Auto-create ZIP if requested
    if auto_zip:
        zip_path = create_zip(folder)
        if zip_path:
            download_history.append({
                'url': None,
                'filename': zip_path,
                'timestamp': datetime.now().isoformat(),
                'status': 'zip_created',
                'error': None
            })

    return jsonify({
        'status': 'started',
        'task_ids': [task.task_id for task in tasks]
    })

def process_queue():
    while not download_queue.empty():
        task = download_queue.get()
        active_downloads[task.task_id] = task
        download_video(task)
        del active_downloads[task.task_id]

@app.route('/progress')
def progress():
    return render_template('progress.html')

@app.route('/get_progress')
def get_progress():
    stats = {
        'total': len(download_status),
        'completed': sum(1 for task in download_status.values() if task.status == 'completed'),
        'skipped': sum(1 for item in download_history if item['status'] == 'skipped'),
        'errors': sum(1 for task in download_status.values() if task.status == 'error'),
        'pending': sum(1 for task in download_status.values() if task.status == 'pending'),
        'download_speed': sum(task.downloaded_bytes / (time.time() - task.start_time + 1)
                            for task in active_downloads.values() if task.start_time) / 1024 / 1024,
        'tasks': [{
            'id': task.task_id,
            'url': task.url,
            'status': task.status,
            'progress': task.progress,
            'error': task.error,
            'filename': task.filename
        } for task in download_status.values()],
        'folder': current_folder
    }
    return jsonify(stats)

@app.route('/clear_status', methods=['POST'])
def clear_status():
    global download_status, download_history, current_folder
    download_status = {}
    download_history = []
    current_folder = None
    return jsonify({'status': 'cleared'})

@app.route('/history')
def history():
    return render_template('history.html', history=download_history)

@app.route('/download_zip/<folder>')
def download_zip(folder):
    folder_path = os.path.join(app.config['DOWNLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404
        
    zip_path = create_zip(folder)
    if zip_path:
        return send_file(zip_path, as_attachment=True)
    return jsonify({'error': 'Failed to create ZIP'}), 500

@app.route('/open_folder/<folder>')
def open_folder(folder):
    folder_path = os.path.join(app.config['DOWNLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404
    try:
        os.startfile(folder_path)  # Windows-specific
        return jsonify({'status': 'success', 'path': folder_path})
    except Exception as e:
        return jsonify({'error': f'Failed to open folder: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)