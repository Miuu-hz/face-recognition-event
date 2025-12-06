import os
import uuid
import qrcode
import sqlite3
import base64
import io
import json
import numpy as np
import face_recognition
import dlib
import tempfile
import threading
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv
import urllib.request
import bz2

from flask import Flask, redirect, request, session, url_for, render_template, jsonify, g
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from googleapiclient.http import MediaIoBaseDownload

# Load environment variables from .env file
load_dotenv()

# --- Logging Setup ---
def setup_logging():
    """Configure structured logging"""
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Create logger
    logger = logging.getLogger('face_recognition_app')
    logger.setLevel(logging.DEBUG if os.getenv('DEBUG', 'True').lower() == 'true' else logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(console_format)

    # File handler for all logs
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_format)

    # Error file handler
    error_handler = RotatingFileHandler('logs/error.log', maxBytes=10*1024*1024, backupCount=5)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_format)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)

    return logger

logger = setup_logging()

# --- Custom Exceptions ---
class FaceRecognitionError(Exception):
    """Base exception for face recognition errors"""
    pass

class ImageProcessingError(FaceRecognitionError):
    """Exception raised when image processing fails"""
    pass

class GoogleDriveError(FaceRecognitionError):
    """Exception raised when Google Drive operations fail"""
    pass

class ValidationError(FaceRecognitionError):
    """Exception raised when input validation fails"""
    pass

class DatabaseError(FaceRecognitionError):
    """Exception raised when database operations fail"""
    pass

# --- Input Validation Functions ---
def sanitize_html(text):
    """Remove potentially dangerous HTML/script characters"""
    import html
    import re

    # HTML escape to prevent XSS
    text = html.escape(text)

    # Remove any remaining suspicious patterns
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)  # Remove onclick, onload, etc.

    return text

def validate_event_name(name):
    """Validate and sanitize event name"""
    if not name or not isinstance(name, str):
        raise ValidationError("Event name is required")

    # Strip whitespace and sanitize
    name = name.strip()
    name = sanitize_html(name)

    if len(name) < 3:
        raise ValidationError("Event name must be at least 3 characters long")

    if len(name) > 100:
        raise ValidationError("Event name must not exceed 100 characters")

    # Check for basic alphanumeric and common punctuation (after HTML escaping)
    import re
    # Allow HTML entities like &amp; &lt; &gt; from sanitization
    if not re.match(r'^[\w\s\-\(\)\[\].,!?&;#]+$', name, re.UNICODE):
        raise ValidationError("Event name contains invalid characters")

    return name

def validate_folder_id(folder_id):
    """Validate Google Drive folder ID"""
    if not folder_id or not isinstance(folder_id, str):
        raise ValidationError("Folder ID is required")

    folder_id = folder_id.strip()

    if len(folder_id) < 10 or len(folder_id) > 100:
        raise ValidationError("Invalid folder ID format")

    return folder_id

def validate_event_id(event_id):
    """Validate event ID (UUID format)"""
    if not event_id or not isinstance(event_id, str):
        raise ValidationError("Event ID is required")

    try:
        uuid.UUID(event_id)
    except ValueError:
        raise ValidationError("Invalid event ID format")

    return event_id

def validate_image_file(file):
    """Validate uploaded image file"""
    if not file:
        raise ValidationError("No file provided")

    if file.filename == '':
        raise ValidationError("Empty filename")

    # Check file extension
    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif'}
    filename = file.filename.lower()
    if not any(filename.endswith(f'.{ext}') for ext in allowed_extensions):
        raise ValidationError(f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}")

    # Check file size (10MB limit)
    max_size = 10 * 1024 * 1024  # 10MB
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset to beginning

    if size > max_size:
        raise ValidationError(f"File size exceeds {max_size // (1024*1024)}MB limit")

    return True

def check_drive_folder_access(drive_service, folder_id):
    """Check if we have access to the Google Drive folder"""
    try:
        # Try to get folder metadata
        folder = drive_service.files().get(
            fileId=folder_id,
            fields='id, name, mimeType, capabilities'
        ).execute()

        # Check if it's actually a folder
        if folder.get('mimeType') != 'application/vnd.google-apps.folder':
            raise ValidationError("The provided ID is not a folder")

        # Check if we can read the folder
        capabilities = folder.get('capabilities', {})
        if not capabilities.get('canListChildren', False):
            raise ValidationError("No permission to access this folder. Please check sharing settings.")

        logger.info(f"Successfully verified access to folder: {folder.get('name')} (ID: {folder_id})")
        return True

    except HttpError as e:
        if e.resp.status == 404:
            raise ValidationError("Folder not found. Please check the folder ID or link.")
        elif e.resp.status == 403:
            raise ValidationError("Access denied. Please share the folder with your Google account.")
        else:
            raise GoogleDriveError(f"Failed to access folder: {e}")
    except Exception as e:
        raise GoogleDriveError(f"Error checking folder access: {e}")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_super_secret_key_change_this')
app.config['DEBUG'] = os.getenv('DEBUG', 'True').lower() == 'true'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Configuration from environment
DATABASE = os.getenv('DATABASE_PATH', 'database.db')

# GPU/CPU Detection
def detect_gpu():
    """Detect if GPU is available for face recognition

    Returns True ONLY if dlib was compiled with CUDA support.
    Having an NVIDIA GPU is not enough - dlib must be compiled with CUDA!

    Note: nvidia-smi showing GPU does NOT mean dlib can use it.
    """
    try:
        import dlib
        if hasattr(dlib, 'DLIB_USE_CUDA') and dlib.DLIB_USE_CUDA:
            logger.info("GPU (CUDA) detected: dlib compiled with CUDA support")
            return True
        else:
            # Check if NVIDIA GPU exists but dlib doesn't have CUDA
            try:
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    logger.warning("⚠️  NVIDIA GPU detected but dlib is NOT compiled with CUDA!")
                    logger.warning("    Face recognition will use CPU (slower than optimal)")
                    logger.warning("    To use GPU: recompile dlib with CUDA, or set FACE_MODEL=hog in .env")
            except:
                pass

            logger.info("GPU not available: using CPU")
            return False
    except ImportError:
        logger.warning("dlib not installed")
        return False
    except Exception as e:
        logger.error(f"Error detecting GPU: {e}")
        return False

has_gpu = detect_gpu()

# --- dlib Model Files Setup ---
MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
os.makedirs(MODELS_DIR, exist_ok=True)

DLIB_MODELS = {
    'cnn_face_detector': {
        'filename': 'mmod_human_face_detector.dat',
        'url': 'http://dlib.net/files/mmod_human_face_detector.dat.bz2'
    },
    'shape_predictor': {
        'filename': 'shape_predictor_5_face_landmarks.dat',
        'url': 'http://dlib.net/files/shape_predictor_5_face_landmarks.dat.bz2'
    },
    'face_recognition': {
        'filename': 'dlib_face_recognition_resnet_model_v1.dat',
        'url': 'http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2'
    }
}

def download_dlib_model(model_name):
    """ดาวน์โหลด dlib model files ถ้ายังไม่มี"""
    if model_name not in DLIB_MODELS:
        raise ValueError(f"Unknown model: {model_name}")

    model_info = DLIB_MODELS[model_name]
    model_path = os.path.join(MODELS_DIR, model_info['filename'])

    # ถ้ามีไฟล์อยู่แล้วก็ไม่ต้องโหลดใหม่
    if os.path.exists(model_path):
        logger.debug(f"Model {model_name} already exists at {model_path}")
        return model_path

    logger.info(f"Downloading {model_name} model from {model_info['url']}...")

    try:
        # ดาวน์โหลดไฟล์ .bz2
        compressed_path = model_path + '.bz2'
        urllib.request.urlretrieve(model_info['url'], compressed_path)

        # แตกไฟล์
        logger.info(f"Extracting {model_name} model...")
        with bz2.open(compressed_path, 'rb') as f_in:
            with open(model_path, 'wb') as f_out:
                f_out.write(f_in.read())

        # ลบไฟล์ .bz2
        os.remove(compressed_path)

        logger.info(f"Successfully downloaded {model_name} model to {model_path}")
        return model_path
    except Exception as e:
        logger.error(f"Failed to download {model_name} model: {e}")
        raise

# โหลด dlib models ถ้ามี GPU
dlib_cnn_detector = None
dlib_shape_predictor = None
dlib_face_encoder = None

if has_gpu:
    try:
        logger.info("Loading dlib models for GPU face detection...")

        # ดาวน์โหลด models ถ้ายังไม่มี
        cnn_model_path = download_dlib_model('cnn_face_detector')
        shape_model_path = download_dlib_model('shape_predictor')
        face_rec_model_path = download_dlib_model('face_recognition')

        # โหลด models
        dlib_cnn_detector = dlib.cnn_face_detection_model_v1(cnn_model_path)
        dlib_shape_predictor = dlib.shape_predictor(shape_model_path)
        dlib_face_encoder = dlib.face_recognition_model_v1(face_rec_model_path)

        logger.info("Successfully loaded dlib models for GPU")
    except Exception as e:
        logger.error(f"Failed to load dlib models: {e}")
        logger.warning("Falling back to face_recognition library (CPU mode)")
        has_gpu = False
        dlib_cnn_detector = None
        dlib_shape_predictor = None
        dlib_face_encoder = None

# Face Recognition Configuration
# Auto-select model based on GPU availability if not explicitly set
default_model = 'cnn' if has_gpu else 'hog'
face_model = os.getenv('FACE_MODEL', default_model)

FACE_RECOGNITION_CONFIG = {
    'tolerance': float(os.getenv('FACE_TOLERANCE', '0.5')),
    'model': face_model,
    'batch_size': int(os.getenv('BATCH_SIZE', '20')),
    'num_jitters': int(os.getenv('NUM_JITTERS', '1')),
}

# Print configuration on startup
def print_config():
    """Print face recognition configuration"""
    print("\n" + "="*50)
    print("Face Recognition Configuration:")
    print("="*50)
    print(f"Device:       {'GPU (CUDA)' if has_gpu else 'CPU'}")
    print(f"Model:        {FACE_RECOGNITION_CONFIG['model'].upper()} ({'CNN - High Accuracy' if face_model == 'cnn' else 'HOG - Fast'})")
    print(f"Tolerance:    {FACE_RECOGNITION_CONFIG['tolerance']} (lower = stricter)")
    print(f"Batch Size:   {FACE_RECOGNITION_CONFIG['batch_size']} images")
    print(f"Num Jitters:  {FACE_RECOGNITION_CONFIG['num_jitters']}")
    print("="*50 + "\n")

# --- Auto-Sync Configuration ---
AUTO_SYNC_CONFIG = {
    'default_interval_minutes': int(os.getenv('AUTO_SYNC_INTERVAL', '2')),  # Check every 2 minutes by default
    'min_interval_seconds': 30,  # Minimum 30 seconds between checks
}

# Store for auto-sync threads
auto_sync_threads = {}
auto_sync_threads_lock = threading.Lock()

# --- Drive Changes API Functions ---
def get_start_page_token(drive_service, folder_id):
    """Get the initial page token for tracking changes"""
    try:
        # Get the start page token for the entire drive
        response = drive_service.changes().getStartPageToken().execute()
        start_page_token = response.get('startPageToken')
        logger.info(f"Retrieved start page token: {start_page_token}")
        return start_page_token
    except Exception as e:
        logger.error(f"Error getting start page token: {e}")
        raise GoogleDriveError(f"Failed to get start page token: {e}")

def check_drive_changes(drive_service, folder_id, start_page_token):
    """Check for new files in the folder since last sync

    Returns:
        tuple: (new_photos, new_page_token)
        - new_photos: list of new photo files
        - new_page_token: updated page token for next check
    """
    try:
        new_photos = []
        page_token = start_page_token

        while page_token is not None:
            # Get changes since last token
            response = drive_service.changes().list(
                pageToken=page_token,
                spaces='drive',
                fields='nextPageToken, newStartPageToken, changes(fileId, file(id, name, mimeType, parents, trashed))',
                pageSize=100
            ).execute()

            # Process changes
            for change in response.get('changes', []):
                file_info = change.get('file')
                if not file_info:
                    continue

                # Check if file is in our folder and is an image
                parents = file_info.get('parents', [])
                mime_type = file_info.get('mimeType', '')
                is_trashed = file_info.get('trashed', False)

                if (folder_id in parents and
                    mime_type in ['image/jpeg', 'image/png', 'image/jpg'] and
                    not is_trashed):

                    new_photos.append({
                        'id': file_info['id'],
                        'name': file_info['name']
                    })
                    logger.debug(f"New photo detected: {file_info['name']}")

            # Get next page token
            page_token = response.get('nextPageToken')

            # If no more pages, get the new start page token
            if page_token is None:
                new_start_page_token = response.get('newStartPageToken')
                return new_photos, new_start_page_token

        return new_photos, start_page_token

    except HttpError as e:
        if e.resp.status == 400:
            # Invalid page token - need to reset
            logger.warning("Invalid page token, resetting...")
            return None, None
        else:
            logger.error(f"HTTP error checking changes: {e}")
            raise GoogleDriveError(f"Failed to check drive changes: {e}")
    except Exception as e:
        logger.error(f"Error checking drive changes: {e}")
        raise GoogleDriveError(f"Failed to check drive changes: {e}")

def index_new_photos(event_id, new_photos, drive_service, db_conn):
    """Index only new photos (incremental indexing)

    Args:
        event_id: Event ID
        new_photos: List of new photo dicts with 'id' and 'name'
        drive_service: Google Drive service
        db_conn: Database connection

    Returns:
        tuple: (photos_indexed, faces_found)
    """
    photos_indexed = 0
    faces_found = 0
    temp_files = []

    try:
        for photo in new_photos:
            photo_id = photo['id']
            photo_name = photo['name']

            # Check if already synced
            existing = db_conn.execute(
                'SELECT 1 FROM synced_photos WHERE event_id = ? AND photo_id = ?',
                (event_id, photo_id)
            ).fetchone()

            if existing:
                logger.debug(f"Photo {photo_name} already synced, skipping")
                continue

            try:
                # Download image
                temp_path = download_image_temp(drive_service, photo_id)
                if not temp_path:
                    logger.warning(f"Failed to download {photo_name}, skipping")
                    continue

                temp_files.append(temp_path)

                # Extract faces
                try:
                    faces = extract_face_encodings(temp_path)
                except ImageProcessingError as e:
                    logger.warning(f"Skipping {photo_name}: {e}")
                    # Mark as synced even if no faces found
                    db_conn.execute(
                        'INSERT INTO synced_photos (event_id, photo_id, photo_name) VALUES (?, ?, ?)',
                        (event_id, photo_id, photo_name)
                    )
                    db_conn.commit()
                    continue

                if faces:
                    logger.info(f"Found {len(faces)} face(s) in {photo_name}")
                    for face_data in faces:
                        encoding_blob = face_data['encoding'].tobytes()
                        location_json = json.dumps(face_data['location'])

                        db_conn.execute(
                            'INSERT INTO faces (event_id, photo_id, photo_name, face_encoding, face_location) VALUES (?, ?, ?, ?, ?)',
                            (event_id, photo_id, photo_name, encoding_blob, location_json)
                        )
                        faces_found += 1

                # Mark as synced
                db_conn.execute(
                    'INSERT INTO synced_photos (event_id, photo_id, photo_name) VALUES (?, ?, ?)',
                    (event_id, photo_id, photo_name)
                )
                db_conn.commit()
                photos_indexed += 1

            except Exception as e:
                logger.error(f"Error processing {photo_name}: {e}")
                continue

        # Update event stats
        current_stats = db_conn.execute(
            'SELECT indexed_photos, total_faces FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()

        if current_stats:
            new_indexed = current_stats['indexed_photos'] + photos_indexed
            new_total_faces = current_stats['total_faces'] + faces_found

            db_conn.execute(
                'UPDATE events SET indexed_photos = ?, total_faces = ?, last_sync_at = ? WHERE id = ?',
                (new_indexed, new_total_faces, datetime.now(), event_id)
            )
            db_conn.commit()

        return photos_indexed, faces_found

    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass

def run_auto_sync_loop(event_id, folder_id, credentials_dict, sync_interval_minutes):
    """Background loop that checks for new photos and indexes them

    This runs in a separate thread for each event with auto-sync enabled.
    """
    db_conn = sqlite3.connect(DATABASE)
    db_conn.row_factory = sqlite3.Row

    logger.info(f"Starting auto-sync loop for event {event_id} (interval: {sync_interval_minutes} min)")

    try:
        # Build Drive service
        creds = Credentials(**credentials_dict)
        drive_service = build('drive', 'v3', credentials=creds)

        # Get initial page token if not exists
        event_data = db_conn.execute(
            'SELECT drive_start_page_token FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()

        page_token = event_data['drive_start_page_token']
        if not page_token:
            page_token = get_start_page_token(drive_service, folder_id)
            db_conn.execute(
                'UPDATE events SET drive_start_page_token = ? WHERE id = ?',
                (page_token, event_id)
            )
            db_conn.commit()
            logger.info(f"Initialized page token for event {event_id}: {page_token}")

        # Main sync loop
        while True:
            # Check if auto-sync is still enabled
            event_status = db_conn.execute(
                'SELECT auto_sync_enabled FROM events WHERE id = ?',
                (event_id,)
            ).fetchone()

            if not event_status or not event_status['auto_sync_enabled']:
                logger.info(f"Auto-sync disabled for event {event_id}, stopping loop")
                break

            try:
                # Check for changes
                logger.debug(f"Checking for changes in event {event_id}...")
                new_photos, new_page_token = check_drive_changes(drive_service, folder_id, page_token)

                if new_page_token is None:
                    # Invalid token, need to reset
                    logger.warning(f"Resetting page token for event {event_id}")
                    page_token = get_start_page_token(drive_service, folder_id)
                    db_conn.execute(
                        'UPDATE events SET drive_start_page_token = ? WHERE id = ?',
                        (page_token, event_id)
                    )
                    db_conn.commit()
                else:
                    page_token = new_page_token
                    db_conn.execute(
                        'UPDATE events SET drive_start_page_token = ? WHERE id = ?',
                        (page_token, event_id)
                    )
                    db_conn.commit()

                if new_photos:
                    logger.info(f"Found {len(new_photos)} new photo(s) for event {event_id}")
                    photos_indexed, faces_found = index_new_photos(
                        event_id, new_photos, drive_service, db_conn
                    )
                    logger.info(f"Auto-sync completed: {photos_indexed} photos, {faces_found} faces")
                else:
                    logger.debug(f"No new photos for event {event_id}")

            except GoogleDriveError as e:
                logger.error(f"Drive error in auto-sync loop for event {event_id}: {e}")
                # Continue loop despite error
            except Exception as e:
                logger.error(f"Unexpected error in auto-sync loop for event {event_id}: {e}", exc_info=True)
                # Continue loop despite error

            # Sleep for the configured interval
            import time
            sleep_seconds = max(sync_interval_minutes * 60, AUTO_SYNC_CONFIG['min_interval_seconds'])
            time.sleep(sleep_seconds)

    except Exception as e:
        logger.error(f"Fatal error in auto-sync loop for event {event_id}: {e}", exc_info=True)
    finally:
        db_conn.close()
        # Remove thread from registry
        with auto_sync_threads_lock:
            if event_id in auto_sync_threads:
                del auto_sync_threads[event_id]
        logger.info(f"Auto-sync loop stopped for event {event_id}")

def start_auto_sync(event_id, folder_id, credentials_dict, sync_interval_minutes=None):
    """Start auto-sync background thread for an event"""
    if sync_interval_minutes is None:
        sync_interval_minutes = AUTO_SYNC_CONFIG['default_interval_minutes']

    with auto_sync_threads_lock:
        # Check if already running
        if event_id in auto_sync_threads and auto_sync_threads[event_id].is_alive():
            logger.warning(f"Auto-sync already running for event {event_id}")
            return False

        # Start new thread
        thread = threading.Thread(
            target=run_auto_sync_loop,
            args=(event_id, folder_id, credentials_dict, sync_interval_minutes),
            daemon=True
        )
        thread.start()
        auto_sync_threads[event_id] = thread

        logger.info(f"Started auto-sync thread for event {event_id}")
        return True

def stop_auto_sync(event_id):
    """Stop auto-sync for an event (it will stop on next check)"""
    # Update database to disable auto-sync
    # The thread will check this flag and stop itself
    logger.info(f"Stopping auto-sync for event {event_id}")
    return True

def restore_auto_sync_on_startup():
    """Restore auto-sync threads for events that had auto-sync enabled

    This should be called on server startup to resume auto-sync
    for events that were running before server restart.
    """
    logger.info("Restoring auto-sync threads on startup...")

    # Note: We can't access session credentials here since this runs at startup
    # Auto-sync will need to be manually re-enabled after server restart
    # This is a limitation of using session-based credentials

    # For now, we'll just log which events had auto-sync enabled
    try:
        db_conn = sqlite3.connect(DATABASE)
        db_conn.row_factory = sqlite3.Row

        events = db_conn.execute(
            'SELECT id, name FROM events WHERE auto_sync_enabled = 1'
        ).fetchall()

        if events:
            logger.info(f"Found {len(events)} event(s) with auto-sync enabled:")
            for event in events:
                logger.info(f"  - {event['name']} (ID: {event['id']})")
            logger.warning("Auto-sync threads cannot be automatically restored due to session credentials.")
            logger.warning("Photographer will need to re-enable auto-sync for these events after logging in.")
        else:
            logger.info("No events with auto-sync enabled")

        db_conn.close()

    except Exception as e:
        logger.error(f"Error restoring auto-sync on startup: {e}", exc_info=True)

# --- Background Task Management ---
class Task:
    """Represents a background task with progress tracking"""
    def __init__(self, task_id, task_type):
        self.id = task_id
        self.type = task_type
        self.status = 'pending'  # pending, running, completed, failed
        self.progress = 0
        self.total = 0
        self.current_item = None
        self.faces_found = 0
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            self.status = 'running'
            self.started_at = datetime.now()

    def update_progress(self, progress, total, current_item=None, faces_found=None):
        with self.lock:
            self.progress = progress
            self.total = total
            self.current_item = current_item
            if faces_found is not None:
                self.faces_found = faces_found

    def complete(self):
        with self.lock:
            self.status = 'completed'
            self.completed_at = datetime.now()

    def fail(self, error_message):
        with self.lock:
            self.status = 'failed'
            self.error = error_message
            self.completed_at = datetime.now()

    def to_dict(self):
        with self.lock:
            # Calculate ETA if task is running
            eta_seconds = None
            if self.status == 'running' and self.started_at and self.progress > 0:
                elapsed = (datetime.now() - self.started_at).total_seconds()
                avg_time_per_item = elapsed / self.progress
                remaining_items = self.total - self.progress
                eta_seconds = int(avg_time_per_item * remaining_items)

            return {
                'id': self.id,
                'type': self.type,
                'status': self.status,
                'progress': self.progress,
                'total': self.total,
                'progress_percent': int((self.progress / self.total * 100)) if self.total > 0 else 0,
                'current_item': self.current_item,
                'faces_found': self.faces_found,
                'eta_seconds': eta_seconds,
                'error': self.error,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'started_at': self.started_at.isoformat() if self.started_at else None,
                'completed_at': self.completed_at.isoformat() if self.completed_at else None
            }

# In-memory task store
tasks = {}
tasks_lock = threading.Lock()

def create_task(task_type):
    """Create a new task and add to task store"""
    task_id = str(uuid.uuid4())
    task = Task(task_id, task_type)
    with tasks_lock:
        tasks[task_id] = task
    return task

def get_task(task_id):
    """Get task by ID"""
    with tasks_lock:
        return tasks.get(task_id)

# --- ฟังก์ชันจัดการฐานข้อมูล (ฉบับสมบูรณ์) ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: # แก้ไข Syntax ที่ผิดพลาดจาก 'is not in None'
        db.close()


def init_db():
    """Initializes the database from the schema file."""
    try:
        schema_path = os.path.join(app.root_path, 'schema.sql')
        if not os.path.exists(schema_path):
            logger.error("'schema.sql' not found in the project directory")
            return False

        with app.app_context():
            db = get_db()
            with open(schema_path, 'r', encoding='utf-8') as f:
                db.cursor().executescript(f.read())
            db.commit()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error during DB initialization: {e}", exc_info=True)
        raise DatabaseError(f"Failed to initialize database: {e}")
    

# --- Helper Functions for Face Recognition ---
def download_image_temp(drive_service, photo_id):
    """Download image from Google Drive to temp file"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            request = drive_service.files().get_media(fileId=photo_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.write(fh.getvalue())
            temp_file.close()
            return temp_file.name
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Failed to download image {photo_id} (attempt {attempt + 1}/{max_retries}): {e}")
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Error downloading image {photo_id} after {max_retries} attempts: {e}")
                raise GoogleDriveError(f"Failed to download image {photo_id}: {e}")
    return None

def extract_face_encodings_gpu(image_path):
    """ใช้ dlib โดยตรงกับ GPU สำหรับ face detection และ encoding (เร็วกว่ามาก!)"""
    try:
        # โหลดรูป
        img = dlib.load_rgb_image(image_path)

        logger.info("Using dlib CNN detector with GPU for face detection")

        # ใช้ CNN detector บน GPU
        # upsample=1 หมายถึงขยายรูป 1 เท่า (สามารถปรับได้ถ้าต้องการหาใบหน้าเล็กๆ)
        detections = dlib_cnn_detector(img, 1)

        results = []
        for detection in detections:
            # ได้ bounding box จาก CNN detector
            rect = detection.rect

            # หา face landmarks (จุดสำคัญบนใบหน้า) สำหรับ alignment
            shape = dlib_shape_predictor(img, rect)

            # คำนวณ face encoding (128-d vector) ด้วย ResNet model
            face_encoding = np.array(dlib_face_encoder.compute_face_descriptor(img, shape))

            # แปลง rectangle เป็น format เดียวกับ face_recognition library
            results.append({
                'encoding': face_encoding,
                'location': {
                    'top': rect.top(),
                    'right': rect.right(),
                    'bottom': rect.bottom(),
                    'left': rect.left()
                }
            })

        logger.debug(f"Found {len(results)} face(s) using GPU")
        return results

    except Exception as e:
        logger.error(f"Error extracting faces with GPU from {image_path}: {e}")
        raise ImageProcessingError(f"Failed to extract faces with GPU from {image_path}: {e}")

def extract_face_encodings(image_path):
    """Extract face encodings from an image - ใช้ GPU ถ้ามี, ไม่งั้นใช้ CPU"""
    # ถ้ามี GPU และโหลด dlib models สำเร็จ ให้ใช้ GPU
    if has_gpu and dlib_cnn_detector is not None:
        return extract_face_encodings_gpu(image_path)

    # ไม่งั้นใช้ face_recognition library (CPU mode)
    try:
        image = face_recognition.load_image_file(image_path)
        logger.info(f"Using model: {FACE_RECOGNITION_CONFIG['model']} for face detection (CPU)")
        face_locations = face_recognition.face_locations(image, model=FACE_RECOGNITION_CONFIG['model'])
        face_encodings = face_recognition.face_encodings(image, face_locations)

        results = []
        for location, encoding in zip(face_locations, face_encodings):
            results.append({
                'encoding': encoding,
                'location': {
                    'top': location[0],
                    'right': location[1],
                    'bottom': location[2],
                    'left': location[3]
                }
            })
        return results
    except Exception as e:
        logger.error(f"Error extracting faces from {image_path}: {e}")
        raise ImageProcessingError(f"Failed to extract faces from {image_path}: {e}")

def create_average_encoding(encodings):
    """Create average encoding from multiple face encodings"""
    if len(encodings) == 0:
        return None
    elif len(encodings) == 1:
        return encodings[0]
    else:
        return np.mean(encodings, axis=0)

def run_indexing_background(task, event_id, folder_id, credentials_dict):
    """Run face indexing in background thread"""
    # Create new database connection for this thread
    db_conn = sqlite3.connect(DATABASE)
    db_conn.row_factory = sqlite3.Row

    try:
        task.start()

        # Validate credentials have all necessary fields
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if field not in credentials_dict or not credentials_dict[field]]

        if missing_fields:
            error_msg = f"Missing required credential fields: {', '.join(missing_fields)}. Please re-authenticate."
            logger.error(f"Task {task.id}: {error_msg}")
            task.fail(error_msg)
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
            db_conn.commit()
            return

        # Build Google Drive service
        creds = Credentials(**credentials_dict)
        drive_service = build('drive', 'v3', credentials=creds)

        # Get event data
        event_data = db_conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event_data:
            task.fail("Event not found")
            return

        logger.info(f"Background Task {task.id}: Starting Face Indexing for Event: {event_data['name']}")

        indexed_photos = 0
        total_faces = 0
        temp_files = []  # Track temp files for cleanup

        try:
            # Get all images from the folder
            query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
            results = drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=100
            ).execute()
            photos = results.get('files', [])

            total_photos = len(photos)
            task.update_progress(0, total_photos, None, faces_found=0)

            logger.info(f"Task {task.id}: Found {total_photos} photos to process")

            # Process photos in batches
            batch_size = FACE_RECOGNITION_CONFIG['batch_size']
            for i in range(0, len(photos), batch_size):
                batch = photos[i:i+batch_size]
                logger.debug(f"Task {task.id}: Processing batch {i//batch_size + 1} ({len(batch)} photos)")

                for photo in batch:
                    photo_id = photo['id']
                    photo_name = photo['name']

                    # Update task progress
                    task.update_progress(indexed_photos, total_photos, photo_name, faces_found=total_faces)
                    logger.debug(f"Task {task.id}: Processing {photo_name}")

                    try:
                        # Download image to temp file
                        temp_path = download_image_temp(drive_service, photo_id)
                        if not temp_path:
                            logger.warning(f"Task {task.id}: Skipping {photo_name} - download failed")
                            continue

                        temp_files.append(temp_path)

                        # Extract face encodings
                        try:
                            faces = extract_face_encodings(temp_path)
                        except ImageProcessingError as e:
                            logger.warning(f"Task {task.id}: Skipping {photo_name} - {e}")
                            indexed_photos += 1
                            continue

                        if faces:
                            logger.debug(f"Task {task.id}: Found {len(faces)} faces in {photo_name}")
                            for face_data in faces:
                                # Convert encoding to blob for storage
                                encoding_blob = face_data['encoding'].tobytes()
                                location_json = json.dumps(face_data['location'])

                                # Save to database
                                db_conn.execute(
                                    'INSERT INTO faces (event_id, photo_id, photo_name, face_encoding, face_location) VALUES (?, ?, ?, ?, ?)',
                                    (event_id, photo_id, photo_name, encoding_blob, location_json)
                                )
                                total_faces += 1
                        else:
                            logger.debug(f"Task {task.id}: No faces found in {photo_name}")

                    except Exception as e:
                        logger.error(f"Task {task.id}: Error processing {photo_name}: {e}")
                        # Continue with next photo

                    indexed_photos += 1

                    # Update database progress
                    db_conn.execute(
                        "UPDATE events SET indexed_photos = ?, total_faces = ? WHERE id = ?",
                        (indexed_photos, total_faces, event_id)
                    )
                    db_conn.commit()

            # Update final status
            db_conn.execute(
                "UPDATE events SET indexing_status = ?, indexed_photos = ?, total_faces = ? WHERE id = ?",
                ('Completed', indexed_photos, total_faces, event_id)
            )
            db_conn.commit()

            task.complete()
            logger.info(f"Task {task.id}: Indexing completed. Photos: {indexed_photos}, Faces: {total_faces}")

        except HttpError as error:
            error_msg = f'Google Drive API error: {error}'
            logger.error(f"Task {task.id}: {error_msg}")
            task.fail(error_msg)
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
            db_conn.commit()

        except Exception as e:
            error_msg = f'Unexpected error: {e}'
            logger.error(f"Task {task.id}: {error_msg}", exc_info=True)
            task.fail(error_msg)
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
            db_conn.commit()

        finally:
            # Clean up temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass

    finally:
        # Close database connection
        db_conn.close()

@app.cli.command('init-db')
def init_db_command():
    """Clears the existing data and creates new tables."""
    if init_db():
        print('Successfully initialized the database.')
    else:
        print('Failed to initialize the database.')


@app.route('/')
def index():
    return redirect(url_for('photographer_dashboard'))

@app.route('/dashboard/photographer')
def photographer_dashboard():
    db = get_db()
    events_from_db = db.execute(
        'SELECT *, indexed_photos, total_faces FROM events ORDER BY id DESC'
    ).fetchall()
    return render_template('photographer_dashboard.html', events=events_from_db)

@app.route('/create_event', methods=['POST'])
def create_event():
    try:
        # Validate event name
        event_name = validate_event_name(request.form.get('event_name', ''))

        event_id = str(uuid.uuid4())
        event_link = url_for('event_page', event_id=event_id, _external=True)
        qr_img_filename = f'qr_{event_id}.png'
        qr_img_path_for_saving = os.path.join('static', qr_img_filename)
        os.makedirs('static', exist_ok=True)
        img = qrcode.make(event_link)
        img.save(qr_img_path_for_saving)

        db = get_db()
        db.execute(
            'INSERT INTO events (id, name, link, qr_path, indexing_status) VALUES (?, ?, ?, ?, ?)',
            (event_id, event_name, event_link, qr_img_filename, 'Not Started')
        )
        db.commit()
        logger.info(f"Created event: {event_name} (ID: {event_id})")
        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.warning(f"Validation error in create_event: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating event: {e}", exc_info=True)
        return jsonify({'error': 'Failed to create event'}), 500

@app.route('/start_indexing/<event_id>')
def start_indexing(event_id):
    """Start face indexing in background thread"""
    try:
        # Validate event ID
        event_id = validate_event_id(event_id)

        db = get_db()
        event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()

        if not event_data:
            raise ValidationError('Event not found')

        if 'credentials' not in session:
            logger.warning("User not authenticated, redirecting to login")
            return redirect(url_for('login_temp'))

        # Validate credentials have refresh_token
        credentials_dict = session['credentials']
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if field not in credentials_dict or not credentials_dict[field]]

        if missing_fields:
            logger.warning(f"Credentials missing fields: {missing_fields}. Forcing re-authentication.")
            # Clear invalid credentials
            session.pop('credentials', None)
            return redirect(url_for('login_temp'))

        folder_id = event_data['drive_folder_id']
        if not folder_id:
            raise ValidationError('No Google Drive folder linked')

        # Validate folder ID
        folder_id = validate_folder_id(folder_id)

        # Create background task
        task = create_task('face_indexing')

        # Update status to In Progress and save task_id
        db.execute(
            "UPDATE events SET indexing_status = ?, task_id = ? WHERE id = ?",
            ('In Progress', task.id, event_id)
        )
        db.commit()

        # Start background thread
        thread = threading.Thread(
            target=run_indexing_background,
            args=(task, event_id, folder_id, credentials_dict)
        )
        thread.daemon = True
        thread.start()

        logger.info(f"Started background indexing task {task.id} for event {event_id}")

        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.warning(f"Validation error in start_indexing: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error starting indexing: {e}", exc_info=True)
        return jsonify({'error': 'Failed to start indexing'}), 500

@app.route('/delete_event/<event_id>', methods=['POST'])
def delete_event(event_id):
    db = get_db()
    event_to_delete = db.execute('SELECT qr_path FROM events WHERE id = ?', (event_id,)).fetchone()
    if event_to_delete:
        qr_path = os.path.join('static', event_to_delete['qr_path'])
        if os.path.exists(qr_path):
            os.remove(qr_path)
        
        db.execute('DELETE FROM faces WHERE event_id = ?', (event_id,))
        db.execute('DELETE FROM events WHERE id = ?', (event_id,))
        db.commit()
        print(f"Deleted event and associated faces: {event_id}")
    return redirect(url_for('photographer_dashboard'))

@app.route('/set_folder/<event_id>/<folder_id>')
def set_folder(event_id, folder_id):
    try:
        # Validate event ID
        event_id = validate_event_id(event_id)

        # Validate folder ID
        folder_id = validate_folder_id(folder_id)

        # Check if user is authenticated
        if 'credentials' not in session:
            logger.warning("User not authenticated when setting folder")
            return redirect(url_for('login_temp'))

        # Build Drive service and check folder access
        creds = Credentials(**session['credentials'])
        drive_service = build('drive', 'v3', credentials=creds)

        # Verify we can access the folder
        check_drive_folder_access(drive_service, folder_id)

        # If all validations pass, save folder ID
        db = get_db()
        db.execute('UPDATE events SET drive_folder_id = ? WHERE id = ?', (folder_id, event_id))
        db.commit()

        logger.info(f"Set folder {folder_id} for event {event_id}")
        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.warning(f"Validation error in set_folder: {e}")
        return f"❌ Error: {str(e)}", 400
    except GoogleDriveError as e:
        logger.error(f"Google Drive error in set_folder: {e}")
        return f"❌ Google Drive Error: {str(e)}", 500
    except Exception as e:
        logger.error(f"Unexpected error in set_folder: {e}", exc_info=True)
        return "❌ An unexpected error occurred. Please try again.", 500

@app.route('/set_folder_from_link/<event_id>', methods=['POST'])
def set_folder_from_link(event_id):
    try:
        # Validate event ID
        event_id = validate_event_id(event_id)

        # Get and validate folder link
        link = request.form.get('folder_link', '').strip()
        if not link:
            raise ValidationError("Folder link is required")

        # Extract folder ID from link
        try:
            if '/folders/' in link:
                folder_id = link.split('/folders/')[-1]
            else:
                folder_id = link.split('/')[-1]

            # Clean up query parameters and fragments
            if '?' in folder_id:
                folder_id = folder_id.split('?')[0]
            if '#' in folder_id:
                folder_id = folder_id.split('#')[0]

            # Validate extracted folder ID
            folder_id = validate_folder_id(folder_id)

        except (IndexError, AttributeError, ValidationError):
            raise ValidationError("Invalid Google Drive folder URL format. Please use a valid folder link.")

        # Check if user is authenticated
        if 'credentials' not in session:
            logger.warning("User not authenticated when setting folder from link")
            return redirect(url_for('login_temp'))

        # Build Drive service and check folder access
        creds = Credentials(**session['credentials'])
        drive_service = build('drive', 'v3', credentials=creds)

        # Verify we can access the folder
        check_drive_folder_access(drive_service, folder_id)

        # If all validations pass, save folder ID
        db = get_db()
        db.execute('UPDATE events SET drive_folder_id = ? WHERE id = ?', (folder_id, event_id))
        db.commit()

        logger.info(f"Set folder {folder_id} for event {event_id} via link")
        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.warning(f"Validation error in set_folder_from_link: {e}")
        return f"❌ Error: {str(e)}", 400
    except GoogleDriveError as e:
        logger.error(f"Google Drive error in set_folder_from_link: {e}")
        return f"❌ Google Drive Error: {str(e)}", 500
    except Exception as e:
        logger.error(f"Unexpected error in set_folder_from_link: {e}", exc_info=True)
        return "❌ An unexpected error occurred. Please try again.", 500
    
# --- API Endpoints and Auth Routes (เหมือนเดิม) ---
@app.route('/api/check_auth')
def check_auth():
    if 'credentials' in session: return jsonify({'authenticated': True})
    else: return jsonify({'authenticated': False}), 401

@app.route('/api/folders')
def get_folders():
    if 'credentials' not in session: return jsonify({'error': 'Not authenticated'}), 401
    try:
        creds = Credentials(**session['credentials'])
        drive_service = build('drive', 'v3', credentials=creds)
        results = drive_service.files().list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            pageSize=100, fields="files(id, name)", orderBy="name"
        ).execute()
        return jsonify(results.get('files', [])), 200
    except HttpError as error:
        print(f'An error occurred: {error}')
        return jsonify({'error': 'Failed to fetch folders'}), 500

@app.route('/api/task/<task_id>')
def get_task_status(task_id):
    """Get status of a background task"""
    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task.to_dict()), 200

@app.route('/api/event/<event_id>/task')
def get_event_task(event_id):
    """Get the latest task for an event"""
    db = get_db()
    event_data = db.execute('SELECT task_id FROM events WHERE id = ?', (event_id,)).fetchone()

    if not event_data:
        return jsonify({'error': 'Event not found'}), 404

    task_id = event_data['task_id']
    if not task_id:
        return jsonify({'error': 'No task found for this event'}), 404

    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify(task.to_dict()), 200

@app.route('/api/event/<event_id>/task/stream')
def stream_event_task(event_id):
    """Server-Sent Events endpoint for real-time task updates"""
    def event_stream():
        """Generator function that yields task updates"""
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row

        try:
            event_data = db.execute('SELECT task_id FROM events WHERE id = ?', (event_id,)).fetchone()

            if not event_data:
                yield f"data: {json.dumps({'error': 'Event not found'})}\n\n"
                return

            task_id = event_data['task_id']
            if not task_id:
                yield f"data: {json.dumps({'error': 'No task found'})}\n\n"
                return

            task = get_task(task_id)
            if not task:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                return

            # Stream updates until task completes or fails
            import time
            while True:
                task_data = task.to_dict()
                yield f"data: {json.dumps(task_data)}\n\n"

                # Stop streaming if task is done
                if task_data['status'] in ['completed', 'failed']:
                    break

                time.sleep(0.5)  # Update every 0.5 seconds

        finally:
            db.close()

    return app.response_class(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/event/<event_id>/auto-sync/enable', methods=['POST'])
def enable_auto_sync(event_id):
    """Enable auto-sync for an event"""
    try:
        # Validate event ID
        event_id = validate_event_id(event_id)

        # Check authentication
        if 'credentials' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        # Get event data
        db = get_db()
        event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()

        if not event_data:
            return jsonify({'error': 'Event not found'}), 404

        folder_id = event_data['drive_folder_id']
        if not folder_id:
            return jsonify({'error': 'No Google Drive folder linked'}), 400

        # Get sync interval from request (optional)
        data = request.get_json() or {}
        sync_interval = data.get('interval_minutes', AUTO_SYNC_CONFIG['default_interval_minutes'])

        # Validate interval
        if sync_interval < 1:
            return jsonify({'error': 'Interval must be at least 1 minute'}), 400

        # Enable auto-sync in database
        db.execute(
            'UPDATE events SET auto_sync_enabled = 1, sync_interval_minutes = ? WHERE id = ?',
            (sync_interval, event_id)
        )
        db.commit()

        # Start auto-sync thread
        credentials_dict = session['credentials']
        success = start_auto_sync(event_id, folder_id, credentials_dict, sync_interval)

        if success:
            logger.info(f"Auto-sync enabled for event {event_id} with interval {sync_interval} minutes")
            return jsonify({
                'message': 'Auto-sync enabled',
                'interval_minutes': sync_interval
            }), 200
        else:
            return jsonify({'error': 'Auto-sync already running'}), 400

    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error enabling auto-sync: {e}", exc_info=True)
        return jsonify({'error': 'Failed to enable auto-sync'}), 500

@app.route('/api/event/<event_id>/auto-sync/disable', methods=['POST'])
def disable_auto_sync(event_id):
    """Disable auto-sync for an event"""
    try:
        # Validate event ID
        event_id = validate_event_id(event_id)

        # Get event data
        db = get_db()
        event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()

        if not event_data:
            return jsonify({'error': 'Event not found'}), 404

        # Disable auto-sync in database
        db.execute(
            'UPDATE events SET auto_sync_enabled = 0 WHERE id = ?',
            (event_id,)
        )
        db.commit()

        stop_auto_sync(event_id)

        logger.info(f"Auto-sync disabled for event {event_id}")
        return jsonify({'message': 'Auto-sync disabled'}), 200

    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error disabling auto-sync: {e}", exc_info=True)
        return jsonify({'error': 'Failed to disable auto-sync'}), 500

@app.route('/api/event/<event_id>/auto-sync/status')
def get_auto_sync_status(event_id):
    """Get auto-sync status for an event"""
    try:
        # Validate event ID
        event_id = validate_event_id(event_id)

        db = get_db()
        event_data = db.execute(
            'SELECT auto_sync_enabled, sync_interval_minutes, last_sync_at FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()

        if not event_data:
            return jsonify({'error': 'Event not found'}), 404

        # Check if thread is actually running
        with auto_sync_threads_lock:
            is_running = event_id in auto_sync_threads and auto_sync_threads[event_id].is_alive()

        return jsonify({
            'enabled': bool(event_data['auto_sync_enabled']),
            'running': is_running,
            'interval_minutes': event_data['sync_interval_minutes'] or AUTO_SYNC_CONFIG['default_interval_minutes'],
            'last_sync_at': event_data['last_sync_at']
        }), 200

    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error getting auto-sync status: {e}", exc_info=True)
        return jsonify({'error': 'Failed to get auto-sync status'}), 500

@app.route('/event/<event_id>')
def event_page(event_id):
    db = get_db()
    event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event_data:
        return "Event not found.", 404
    # ส่ง event_id ไปให้ template ด้วย
    return render_template('event_page.html', event_name=event_data['name'], event_id=event_id)

@app.route('/login_temp')
def login_temp():
    CLIENT_SECRETS_FILE = "client_secrets.json"
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/cloud-platform']
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=url_for('callback_temp', _external=True))
    # Force consent prompt to always get refresh_token
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force re-consent to get refresh_token every time
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback_temp')
def callback_temp():
    CLIENT_SECRETS_FILE = "client_secrets.json"
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/cloud-platform']
    state = session['state']
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, state=state, redirect_uri=url_for('callback_temp', _external=True))
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    # Validate that we have all necessary credentials
    if not credentials.refresh_token:
        logger.error("No refresh_token received from Google OAuth")
        return "Authentication error: No refresh token received. Please revoke app access in Google Account settings and try again.", 500

    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    logger.info("Successfully authenticated and stored credentials with refresh_token")
    # แก้ให้ redirect ไปที่หน้า dashboard หลักเสมอหลัง login
    return redirect(url_for('photographer_dashboard'))

@app.route('/search_faces/<event_id>', methods=['POST'])
def search_faces(event_id):
    import time
    start_time = time.time()

    try:
        # Validate event ID
        event_id = validate_event_id(event_id)

        if 'selfie_images' not in request.files:
            raise ValidationError("No images uploaded")

        files = request.files.getlist('selfie_images')
        if len(files) == 0 or files[0].filename == '':
            raise ValidationError("No selected files")

        if len(files) > 3:
            raise ValidationError("Maximum 3 images allowed")

        # Validate each file
        for file in files:
            if file and file.filename != '':
                validate_image_file(file)

        logger.info(f"[TIMING] Validation took: {time.time() - start_time:.2f}s")

        # Process uploaded images
        uploaded_encodings = []
        temp_files = []

        try:
            # Extract face encodings from uploaded images
            extract_start = time.time()
            for file in files:
                if file and file.filename != '':
                    # Save uploaded file to temp
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                    file.save(temp_file.name)
                    temp_files.append(temp_file.name)

                    # Extract face encodings
                    try:
                        faces = extract_face_encodings(temp_file.name)
                        if faces:
                            # Use first face found in each image
                            uploaded_encodings.append(faces[0]['encoding'])
                            logger.debug(f"Found face in uploaded image: {file.filename}")
                    except ImageProcessingError as e:
                        logger.warning(f"Skipping {file.filename}: {e}")

            logger.info(f"[TIMING] Face extraction (GPU) took: {time.time() - extract_start:.2f}s")

            if not uploaded_encodings:
                raise ValidationError("No faces detected in uploaded photos. Please try again with clear face photos")

            # Create average encoding from uploaded faces
            search_encoding = create_average_encoding(uploaded_encodings)
            logger.info(f"Created average encoding from {len(uploaded_encodings)} face(s) for event {event_id}")

            # Search in database
            search_start = time.time()
            db = get_db()
            cursor = db.execute(
                'SELECT photo_id, photo_name, face_encoding FROM faces WHERE event_id = ?',
                (event_id,)
            )

            matching_photos = {}  # Use dict to avoid duplicates
            faces_checked = 0

            for row in cursor:
                photo_id = row['photo_id']
                photo_name = row['photo_name']

                # Convert blob back to numpy array
                stored_encoding = np.frombuffer(row['face_encoding'], dtype=np.float64)

                # Calculate face distance
                distance = face_recognition.face_distance([stored_encoding], search_encoding)[0]

                # Check if match (lower distance = better match)
                if distance <= FACE_RECOGNITION_CONFIG['tolerance']:
                    if photo_id not in matching_photos:
                        matching_photos[photo_id] = {
                            'name': photo_name,
                            'distance': distance
                        }
                    else:
                        # Keep the best match for each photo
                        if distance < matching_photos[photo_id]['distance']:
                            matching_photos[photo_id]['distance'] = distance

                    logger.debug(f"Match found: {photo_name} (distance: {distance:.3f})")

                faces_checked += 1

            logger.info(f"[TIMING] Database search took: {time.time() - search_start:.2f}s")
            logger.info(f"Search completed for event {event_id}: Checked {faces_checked} faces, found {len(matching_photos)} matching photos")
            logger.info(f"[TIMING] TOTAL TIME: {time.time() - start_time:.2f}s")

            # Convert to Google Drive links
            photo_links = []
            for photo_id, photo_info in matching_photos.items():
                photo_links.append({
                    'url': f"https://drive.google.com/file/d/{photo_id}/view",
                    'name': photo_info['name'],
                    'distance': photo_info['distance']
                })

            # Sort by best match (lowest distance)
            photo_links.sort(key=lambda x: x['distance'])

            # Return results
            return render_template('results_page.html',
                                 photo_links=[p['url'] for p in photo_links],
                                 event_id=event_id,
                                 matches_count=len(photo_links))

        except ImageProcessingError as e:
            logger.error(f"Image processing error in search_faces: {e}")
            return f"Failed to process images: {str(e)}", 400

        except Exception as e:
            logger.error(f"Error in search_faces: {e}", exc_info=True)
            return f"An error occurred while processing: {str(e)}", 500

        finally:
            # Clean up temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass

    except ValidationError as e:
        logger.warning(f"Validation error in search_faces: {e}")
        return str(e), 400
    except Exception as e:
        logger.error(f"Error in search_faces: {e}", exc_info=True)
        return "Failed to search faces", 500

if __name__ == '__main__':
    print_config()
    restore_auto_sync_on_startup()
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('DEBUG', 'True').lower() == 'true'
    app.run(host=host, port=port, debug=debug)