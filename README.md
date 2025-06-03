# StreamSaver
 Video Downloader - Support for YouTube, Instagram, Facebook and more

StreamSaver is a powerful and user-friendly web application designed to simplify video downloading from various online platforms. Built with Flask on the backend and a modern Bootstrap 5 frontend, it offers parallel downloads, real-time progress tracking, and robust error handling to ensure a smooth downloading experience.

## Features

- Fast Downloads: Leverages yt-dlp for rapid video retrieval.

- Parallel Downloading: Configure up to 10 simultaneous downloads for maximum efficiency.

- Reliable: Automatic retries and comprehensive error handling for failed downloads.

- Real-time Progress: Live progress tracking with detailed statistics and individual progress bars for each download task.

- Wide Platform Support: Download videos from popular platforms like YouTube, Instagram, Facebook, and many more sites supported by yt-dlp.

- Output Customization: Specify a custom output folder and filename pattern for your downloads.

- Cookie Support: Upload cookies.txt files to download content from private or restricted social media accounts (e.g., Instagram, Facebook).

- Automatic ZIP Archiving: Option to auto-create a ZIP archive of all downloaded files in a batch upon completion.

- Invalid URL Skipping: Choose to skip invalid URLs in a batch instead of stopping the entire process.

- Download History: View a comprehensive history of all your past downloads.

- Cross-platform Folder Opening: Directly open the download directory from the web interface (Windows, macOS, Linux).

- Clean & Responsive UI: A modern, intuitive, and mobile-friendly user interface powered by Bootstrap 5.

## How to Run This Project

Follow these steps to get StreamSaver up and running on your local machine.

Prerequisites
```
Python 3.8+
pip (Python package installer)
```

#### 1. Clone the Repository
First, clone the StreamSaver repository to your local machine:
```bash
git clone https://github.com/yash-raj202134/StreamSaver.git
```
#### 2. Install Dependencies
It's highly recommended to create a virtual environment to manage dependencies:
```bash
pip install -r requirements.txt
```

#### 3. Download the cookies.txt Browser Extension (Optional, for Social Media)
If you plan to download videos from platforms like Instagram or Facebook that require a login, you'll need to provide a cookies.txt file.

- Install the Chrome Extension:
Go to the Chrome Web Store and install: Get cookies.txt Locally
Download Your Cookie File:

- Log in to your Instagram/Facebook account (or any other platform requiring cookies) in your Chrome browser.

- Navigate to the page you want to download from.

- Click on the "Get cookies.txt Locally" extension icon in your browser toolbar.

- Click the "Export" button to download the cookies.txt file. You will upload this file in the StreamSaver application.

#### 4. Run the Flask Application
Start the Flask development server:
```bash
python app.py
```
You will see output indicating that the server is running, typically on http://127.0.0.1:5000/.

#### 5. Using StreamSaver
1. Open in Browser: Open your web browser and navigate to http://127.0.0.1:5000/.

2. Enter URLs: In the "Video URLs" text area, paste the links to the videos you want to download, with one URL per line. You can paste multiple links at once (e.g., 1000 links). The URL counter will update automatically.

3. Configure Options (Optional):

    - Output Folder Name: Provide a custom name for the folder where your downloads will be saved.

    - Filename Pattern: Customize how downloaded files are named using yt-dlp's format codes.

    - Cookie File: If downloading from Instagram, Facebook, or other restricted sites, click "Choose File" and upload the cookies.txt file you downloaded earlier.

    - Advanced Settings: Adjust options like "Auto-create ZIP archive," "Skip invalid URLs," and "Parallel Downloads."

4. Start Download: Click the "Start Download" button.

5. Monitor Progress: You will be immediately redirected to the progress page, where you can see real-time statistics and individual progress bars for each download.

6. Completion Notification: Once all downloads are complete, a popup will appear in the center of the screen, notifying you. You can click "OK" to dismiss it or "View Details" to go to the download history page.

7. Access Downloads: Use the "Download as ZIP" or "Open Folder" buttons on the progress page to retrieve your downloaded content.

Feel free to contribute, report issues, or suggest new features!