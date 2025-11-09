"""
Face Recognition Event System

A Flask-based web application for event photography management with
AI-powered face recognition for easy photo discovery.
"""

import os
import uuid
import qrcode
import sqlite3
import base64
import io
import json
import numpy as np
import face_recognition
import tempfile
import logging
import traceback
import time
from datetime import datetime
from PIL import Image
from functools import wraps

from flask import Flask, redirect, request, session, url_for, render_template, jsonify, g
from flask_executor import Executor
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from googleapiclient.http import MediaIoBaseDownload

# Import configuration
from config import get_config, ConfigError

# ============================================
# Flask App Initialization
# ============================================

app = Flask(__name__)

# Load configuration based on environment
try:
    Config = get_config()
    Config.init_app(app)
except ConfigError as e:
    print(f"\n{'='*60}")
    print("CONFIGURATION ERROR")
    print(f"{'='*60}")
    print(str(e))
    print(f"{'='*60}\n")
    print("Please check your .env file and environment variables.")
    print("See .env.example for reference.\n")
    exit(1)

# Database path from config
DATABASE = Config.DATABASE_PATH

# ============================================
# Logging Configuration
# ============================================

def setup_logging():
    """Configure structured logging for the application"""
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    # Configure logging format
    log_format = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)

    # File handler for all logs
    file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)

    # File handler for errors only
    error_handler = logging.FileHandler(os.path.join(log_dir, 'error.log'))
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(log_format)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if Config.DEBUG else logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    # Reduce noise from third-party libraries
    logging.getLogger('googleapiclient').setLevel(logging.WARNING)
    logging.getLogger('google.auth').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    return logging.getLogger(__name__)

# Initialize logging
logger = setup_logging()
logger.info("="*60)
logger.info("Face Recognition Event System - Starting")
logger.info("="*60)

# ============================================
# Custom Exceptions
# ============================================

class FaceRecognitionError(Exception):
    """Base exception for face recognition errors"""
    pass

class ImageProcessingError(FaceRecognitionError):
    """Error during image processing"""
    pass

class DatabaseError(Exception):
    """Database operation error"""
    pass

class ValidationError(Exception):
    """Input validation error"""
    pass

class GoogleDriveError(Exception):
    """Google Drive API error"""
    pass

# ============================================
# Error Handlers
# ============================================

@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    return render_template('error.html', error_message="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}", exc_info=True)
    return render_template('error.html', error_message="Internal server error"), 500

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Unhandled exception: {error}", exc_info=True)
    return render_template('error.html', error_message="An unexpected error occurred"), 500

# ============================================
# Utility Functions
# ============================================

def retry_on_error(max_retries=3, delay=1, backoff=2, exceptions=(Exception,)):
    """
    Decorator for retrying functions that may fail transiently

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {str(e)}"
                        )
                        time.sleep(_delay)
                        _delay *= backoff
                    else:
                        logger.error(
                            f"Max retries exceeded for {func.__name__}: {str(e)}"
                        )

            raise last_exception
        return wrapper
    return decorator

def validate_event_id(event_id):
    """Validate event ID format"""
    if not event_id or not isinstance(event_id, str):
        raise ValidationError("Invalid event ID")
    try:
        uuid.UUID(event_id)
    except ValueError:
        raise ValidationError(f"Invalid event ID format: {event_id}")
    return event_id

def validate_folder_id(folder_id):
    """Validate Google Drive folder ID"""
    if not folder_id or not isinstance(folder_id, str):
        raise ValidationError("Invalid folder ID")
    # Basic validation - should be alphanumeric with possible special chars
    if len(folder_id) < 10 or len(folder_id) > 100:
        raise ValidationError(f"Invalid folder ID length: {folder_id}")
    return folder_id

def validate_image_file(file):
    """Validate uploaded image file"""
    if not file or file.filename == '':
        raise ValidationError("No file provided")

    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    if ext not in allowed_extensions:
        raise ValidationError(f"Invalid file type: {ext}. Allowed: {allowed_extensions}")

    return file

def validate_file_size(file, max_size_mb=10):
    """
    Validate file size

    Args:
        file: File object from request.files
        max_size_mb: Maximum file size in MB (default: 10MB)

    Raises:
        ValidationError: If file is too large
    """
    if not file:
        return

    # Seek to end to get file size
    file.seek(0, 2)  # Seek to end
    size = file.tell()  # Get position (size in bytes)
    file.seek(0)  # Reset to beginning

    max_size_bytes = max_size_mb * 1024 * 1024

    if size > max_size_bytes:
        size_mb = size / (1024 * 1024)
        raise ValidationError(
            f"File too large: {size_mb:.1f}MB. Maximum allowed: {max_size_mb}MB"
        )

    return file

def validate_event_name(name):
    """
    Validate event name

    Args:
        name: Event name string

    Returns:
        str: Sanitized event name

    Raises:
        ValidationError: If name is invalid
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Event name is required")

    # Strip whitespace
    name = name.strip()

    # Check length
    if len(name) < 3:
        raise ValidationError("Event name must be at least 3 characters long")

    if len(name) > 100:
        raise ValidationError("Event name must not exceed 100 characters")

    # Check for valid characters (allow letters, numbers, spaces, basic punctuation)
    import re
    if not re.match(r'^[\w\s\-\.\,\!\?\(\)]+$', name, re.UNICODE):
        raise ValidationError(
            "Event name contains invalid characters. Only letters, numbers, spaces, and basic punctuation allowed."
        )

    return name

def sanitize_string(text, max_length=None):
    """
    Sanitize user input string

    Args:
        text: Input string
        max_length: Maximum length (optional)

    Returns:
        str: Sanitized string
    """
    if not text:
        return ''

    # Strip whitespace
    text = text.strip()

    # Remove null bytes
    text = text.replace('\x00', '')

    # Limit length if specified
    if max_length and len(text) > max_length:
        text = text[:max_length]

    return text

def validate_google_drive_access(drive_service, folder_id):
    """
    Validate that we have access to a Google Drive folder

    Args:
        drive_service: Google Drive service instance
        folder_id: Google Drive folder ID

    Returns:
        bool: True if accessible

    Raises:
        GoogleDriveError: If folder is not accessible
    """
    try:
        # Try to get folder metadata
        folder = drive_service.files().get(
            fileId=folder_id,
            fields='id,name,mimeType,capabilities'
        ).execute()

        # Check if it's actually a folder
        if folder.get('mimeType') != 'application/vnd.google-apps.folder':
            raise GoogleDriveError(f"ID {folder_id} is not a folder")

        # Check if we have read permission
        capabilities = folder.get('capabilities', {})
        if not capabilities.get('canListChildren', False):
            raise GoogleDriveError(f"No permission to read folder contents")

        logger.info(f"Validated access to Google Drive folder: {folder.get('name')}")
        return True

    except HttpError as e:
        if e.resp.status == 404:
            raise GoogleDriveError(f"Folder not found: {folder_id}") from e
        elif e.resp.status == 403:
            raise GoogleDriveError(f"Access denied to folder: {folder_id}") from e
        else:
            raise GoogleDriveError(f"Error accessing folder: {e}") from e
    except Exception as e:
        raise GoogleDriveError(f"Unexpected error validating folder access: {e}") from e

# ============================================
# Background Task Executor
# ============================================

executor = Executor(app)

# ============================================
# GPU/CPU Detection and Configuration
# ============================================

def detect_gpu_availability():
    """
    ตรวจสอบว่ามี GPU (CUDA) ให้ใช้งานหรือไม่
    Returns: True ถ้ามี GPU, False ถ้าไม่มี
    """
    try:
        import torch
        if torch.cuda.is_available():
            logger.info(f"✓ GPU detected: {torch.cuda.get_device_name(0)}")
            return True
        else:
            logger.info("○ No GPU detected, using CPU")
            return False
    except ImportError:
        # ถ้าไม่มี PyTorch ลองเช็คด้วยวิธีอื่น
        try:
            # เช็คว่า dlib ถูก compile ด้วย CUDA support หรือไม่
            import dlib
            if dlib.DLIB_USE_CUDA:
                logger.info("✓ GPU detected: dlib with CUDA support")
                return True
            else:
                logger.info("○ dlib without CUDA support, using CPU")
                return False
        except (ImportError, AttributeError):
            logger.info("○ No GPU detection available, defaulting to CPU")
            return False

def get_optimal_face_recognition_config():
    """
    กำหนด config ที่เหมาะสมตามฮาร์ดแวร์ที่มี
    Uses values from environment variables (Config class)

    Returns:
        dict: Face recognition configuration
    """
    has_gpu = detect_gpu_availability()

    # Get model setting from config
    model_config = Config.FACE_MODEL.lower()

    # Determine model based on setting
    if model_config == 'auto':
        # Auto-detect based on GPU availability
        model = 'cnn' if has_gpu else 'hog'
    elif model_config in ['hog', 'cnn']:
        # Use specified model
        model = model_config
    else:
        # Default to hog if invalid
        logger.warning(f"Invalid FACE_MODEL '{Config.FACE_MODEL}', defaulting to 'hog'")
        model = 'hog'

    # Build configuration dictionary
    config = {
        'tolerance': Config.FACE_TOLERANCE,
        'batch_size': Config.BATCH_SIZE,
        'model': model,
        'use_gpu': has_gpu and (model == 'cnn'),
        'num_jitters': Config.NUM_JITTERS,
    }

    # แสดงข้อมูล config
    logger.info("="*50)
    logger.info("Face Recognition Configuration:")
    logger.info("="*50)
    logger.info(f"Device:       {'GPU (CUDA)' if config['use_gpu'] else 'CPU'}")
    logger.info(f"Model:        {config['model'].upper()} ({'CNN - High Accuracy' if config['model'] == 'cnn' else 'HOG - Fast Processing'})")
    logger.info(f"  (Setting: {Config.FACE_MODEL})")
    logger.info(f"Tolerance:    {config['tolerance']} (lower = stricter)")
    logger.info(f"Batch Size:   {config['batch_size']} images")
    logger.info(f"Num Jitters:  {config['num_jitters']}")
    logger.info("="*50)

    return config

# สร้าง config อัตโนมัติตอน startup
FACE_RECOGNITION_CONFIG = get_optimal_face_recognition_config()

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
            logger.error("schema.sql not found in the project directory")
            logger.error("Please make sure the file exists and is named correctly")
            return False

        with app.app_context():
            db = get_db()
            with open(schema_path, 'r', encoding='utf-8') as f:
                db.cursor().executescript(f.read())
            db.commit()

        logger.info("Database initialized successfully")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error during initialization: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error during DB initialization: {e}", exc_info=True)
        return False
    

# --- Helper Functions for Face Recognition ---
@retry_on_error(max_retries=3, delay=1, exceptions=(HttpError, IOError))
def download_image_temp(drive_service, photo_id):
    """
    Download image from Google Drive to temp file with retry logic

    Args:
        drive_service: Google Drive service instance
        photo_id: Google Drive file ID

    Returns:
        str: Path to temp file, or None if failed

    Raises:
        GoogleDriveError: If download fails after retries
    """
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

        logger.debug(f"Downloaded image {photo_id} to {temp_file.name}")
        return temp_file.name
    except HttpError as e:
        logger.error(f"Google Drive API error downloading {photo_id}: {e}")
        raise GoogleDriveError(f"Failed to download image {photo_id}") from e
    except Exception as e:
        logger.error(f"Unexpected error downloading image {photo_id}: {e}")
        return None

def extract_face_encodings(image_path):
    """
    Extract face encodings from an image
    ใช้ config ที่ detect GPU/CPU อัตโนมัติ

    Args:
        image_path: Path to image file

    Returns:
        list: List of face data (encoding and location)

    Raises:
        ImageProcessingError: If image processing fails
    """
    try:
        # Validate image file exists
        if not os.path.exists(image_path):
            raise ImageProcessingError(f"Image file not found: {image_path}")

        # Load image
        try:
            image = face_recognition.load_image_file(image_path)
        except Exception as e:
            raise ImageProcessingError(f"Failed to load image: {e}") from e

        # ใช้ model ที่เหมาะสมตาม GPU/CPU
        face_locations = face_recognition.face_locations(
            image,
            model=FACE_RECOGNITION_CONFIG['model']
        )

        if not face_locations:
            logger.debug(f"No faces found in {image_path}")
            return []

        # ใช้ num_jitters สำหรับความแม่นยำ (GPU จะใช้ค่าสูงกว่า)
        face_encodings = face_recognition.face_encodings(
            image,
            face_locations,
            num_jitters=FACE_RECOGNITION_CONFIG['num_jitters']
        )

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

        logger.debug(f"Extracted {len(results)} face(s) from {image_path}")
        return results

    except ImageProcessingError:
        raise
    except Exception as e:
        logger.error(f"Error extracting faces from {image_path}: {e}", exc_info=True)
        raise ImageProcessingError(f"Face extraction failed: {e}") from e

def create_average_encoding(encodings):
    """Create average encoding from multiple face encodings"""
    if len(encodings) == 0:
        return None
    elif len(encodings) == 1:
        return encodings[0]
    else:
        return np.mean(encodings, axis=0)

# ============================================
# Background Task Management
# ============================================

def create_task(event_id, task_type='indexing'):
    """
    Create a new background task

    Args:
        event_id: Event ID
        task_type: Type of task (default: 'indexing')

    Returns:
        str: Task ID
    """
    task_id = str(uuid.uuid4())
    db = get_db()
    db.execute(
        'INSERT INTO tasks (id, event_id, task_type, status, created_at) VALUES (?, ?, ?, ?, ?)',
        (task_id, event_id, task_type, 'pending', datetime.now())
    )
    db.commit()
    return task_id

def update_task_status(task_id, status, progress=None, total=None, current_item=None, error=None):
    """
    Update task status

    Args:
        task_id: Task ID
        status: New status ('pending', 'running', 'completed', 'failed')
        progress: Current progress count
        total: Total items to process
        current_item: Current item being processed
        error: Error message if failed
    """
    db = get_db()

    updates = ['status = ?']
    params = [status]

    if progress is not None:
        updates.append('progress = ?')
        params.append(progress)

    if total is not None:
        updates.append('total = ?')
        params.append(total)

    if current_item is not None:
        updates.append('current_item = ?')
        params.append(current_item)

    if error is not None:
        updates.append('error = ?')
        params.append(error)

    if status == 'running' and progress == 0:
        updates.append('started_at = ?')
        params.append(datetime.now())

    if status in ['completed', 'failed']:
        updates.append('completed_at = ?')
        params.append(datetime.now())

    params.append(task_id)

    query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
    db.execute(query, params)
    db.commit()

def get_task_status(task_id):
    """
    Get task status

    Args:
        task_id: Task ID

    Returns:
        dict: Task information or None if not found
    """
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()

    if task is None:
        return None

    return {
        'id': task['id'],
        'event_id': task['event_id'],
        'task_type': task['task_type'],
        'status': task['status'],
        'progress': task['progress'],
        'total': task['total'],
        'current_item': task['current_item'],
        'error': task['error'],
        'started_at': task['started_at'],
        'completed_at': task['completed_at'],
        'created_at': task['created_at'],
    }

def get_event_latest_task(event_id):
    """
    Get latest task for an event

    Args:
        event_id: Event ID

    Returns:
        dict: Task information or None
    """
    db = get_db()
    task = db.execute(
        'SELECT * FROM tasks WHERE event_id = ? ORDER BY created_at DESC LIMIT 1',
        (event_id,)
    ).fetchone()

    if task is None:
        return None

    return {
        'id': task['id'],
        'status': task['status'],
        'progress': task['progress'],
        'total': task['total'],
        'current_item': task['current_item'],
        'error': task['error'],
    }

@app.cli.command('init-db')
def init_db_command():
    """Clears the existing data and creates new tables."""
    if init_db():
        logger.info('Successfully initialized the database.')
        print('Successfully initialized the database.')
    else:
        logger.error('Failed to initialize the database.')
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
        # Validate and sanitize event name
        event_name_raw = request.form.get('event_name', '').strip()
        event_name = validate_event_name(event_name_raw)

        # Generate event ID and link
        event_id = str(uuid.uuid4())
        event_link = url_for('event_page', event_id=event_id, _external=True)

        # Generate QR code
        qr_img_filename = f'qr_{event_id}.png'
        qr_img_path_for_saving = os.path.join('static', qr_img_filename)
        os.makedirs('static', exist_ok=True)
        img = qrcode.make(event_link)
        img.save(qr_img_path_for_saving)

        # Save to database
        db = get_db()
        db.execute(
            'INSERT INTO events (id, name, link, qr_path, indexing_status) VALUES (?, ?, ?, ?, ?)',
            (event_id, event_name, event_link, qr_img_filename, 'Not Started')
        )
        db.commit()

        logger.info(f"Created event: {event_name} (ID: {event_id})")
        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.warning(f"Validation error creating event: {e}")
        return render_template('error.html', error_message=str(e)), 400
    except Exception as e:
        logger.error(f"Error creating event: {e}", exc_info=True)
        return render_template('error.html', error_message="Failed to create event"), 500

def run_face_indexing_task(event_id, task_id, credentials_dict, folder_id):
    """
    Background task for face indexing

    Args:
        event_id: Event ID
        task_id: Task ID for tracking
        credentials_dict: Google OAuth credentials dictionary
        folder_id: Google Drive folder ID
    """
    # Create new database connection for background thread
    db_conn = sqlite3.connect(DATABASE)
    db_conn.row_factory = sqlite3.Row

    indexed_photos = 0
    total_faces = 0
    temp_files = []
    task_logger = logging.getLogger(f"task.{task_id}")

    try:
        # Update task to running
        update_task_status(task_id, 'running', progress=0, total=0)

        # Build Google Drive service
        creds = Credentials(**credentials_dict)
        drive_service = build('drive', 'v3', credentials=creds)

        task_logger.info(f"Starting Face Indexing for Event: {event_id}")

        # Get all images from the folder
        query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"

        try:
            results = drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=100
            ).execute()
            photos = results.get('files', [])
        except HttpError as e:
            raise GoogleDriveError(f"Failed to list files from folder {folder_id}") from e

        total_photos = len(photos)
        task_logger.info(f"Found {total_photos} photos to process")

        if total_photos == 0:
            task_logger.warning(f"No photos found in folder {folder_id}")
            update_task_status(task_id, 'completed', progress=0, total=0)
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Completed', event_id))
            db_conn.commit()
            return

        # Update task with total
        update_task_status(task_id, 'running', progress=0, total=total_photos)
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('In Progress', event_id))
        db_conn.commit()

        # Process photos in batches
        batch_size = FACE_RECOGNITION_CONFIG['batch_size']
        for i in range(0, len(photos), batch_size):
            batch = photos[i:i+batch_size]
            batch_num = i//batch_size + 1
            task_logger.info(f"Processing batch {batch_num} ({len(batch)} photos)...")

            for photo in batch:
                photo_id = photo['id']
                photo_name = photo['name']
                task_logger.debug(f"Processing: {photo_name}")

                # Update current item
                update_task_status(
                    task_id,
                    'running',
                    progress=indexed_photos,
                    current_item=photo_name
                )

                # Download image to temp file with error handling
                try:
                    temp_path = download_image_temp(drive_service, photo_id)
                    if not temp_path:
                        task_logger.warning(f"Skipping {photo_name}: download failed")
                        continue

                    temp_files.append(temp_path)

                    # Extract face encodings
                    faces = extract_face_encodings(temp_path)

                    if faces:
                        task_logger.debug(f"Found {len(faces)} face(s) in {photo_name}")
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
                        task_logger.debug(f"No faces found in {photo_name}")

                    indexed_photos += 1

                    # Update progress in events table
                    db_conn.execute(
                        "UPDATE events SET indexed_photos = ?, total_faces = ? WHERE id = ?",
                        (indexed_photos, total_faces, event_id)
                    )
                    db_conn.commit()

                except (GoogleDriveError, ImageProcessingError) as e:
                    task_logger.warning(f"Error processing {photo_name}: {e}")
                    # Continue with next photo
                    continue
                except Exception as e:
                    task_logger.error(f"Unexpected error processing {photo_name}: {e}", exc_info=True)
                    # Continue with next photo
                    continue

        # Update final status
        db_conn.execute(
            "UPDATE events SET indexing_status = ?, indexed_photos = ?, total_faces = ? WHERE id = ?",
            ('Completed', indexed_photos, total_faces, event_id)
        )
        db_conn.commit()

        update_task_status(task_id, 'completed', progress=indexed_photos, total=total_photos)
        task_logger.info(f"Completed. Photos: {indexed_photos}, Faces: {total_faces}")

    except GoogleDriveError as e:
        error_msg = f'Google Drive error: {str(e)}'
        task_logger.error(error_msg, exc_info=True)
        try:
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
            db_conn.commit()
            update_task_status(task_id, 'failed', error=error_msg)
        except Exception as db_error:
            task_logger.error(f"Failed to update failure status: {db_error}")

    except Exception as e:
        error_msg = f'Unexpected error: {str(e)}'
        task_logger.error(error_msg, exc_info=True)
        try:
            db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
            db_conn.commit()
            update_task_status(task_id, 'failed', error=error_msg)
        except Exception as db_error:
            task_logger.error(f"Failed to update failure status: {db_error}")

    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    task_logger.debug(f"Cleaned up temp file: {temp_file}")
            except Exception as e:
                task_logger.warning(f"Failed to delete temp file {temp_file}: {e}")

        # Close database connection
        try:
            db_conn.close()
        except Exception as e:
            task_logger.error(f"Error closing database connection: {e}")

@app.route('/start_indexing/<event_id>')
def start_indexing(event_id):
    """Start face indexing as a background task"""
    try:
        # Validate event ID
        validate_event_id(event_id)

        # Check authentication
        if 'credentials' not in session:
            logger.warning(f"Unauthenticated user attempted to start indexing for event {event_id}")
            return redirect(url_for('photographer_dashboard'))

        # Get event data
        db = get_db()
        event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()

        if not event_data:
            logger.warning(f"Event not found: {event_id}")
            return redirect(url_for('photographer_dashboard'))

        # Validate folder ID
        folder_id = event_data['drive_folder_id']
        if not folder_id:
            logger.warning(f"No folder ID set for event {event_id}")
            return redirect(url_for('photographer_dashboard'))

        # Create background task
        task_id = create_task(event_id, 'indexing')

        # Get credentials from session
        credentials_dict = session['credentials']

        # Submit task to background executor
        executor.submit(run_face_indexing_task, event_id, task_id, credentials_dict, folder_id)

        logger.info(f"✓ Face indexing task created: {task_id} for event: {event_data['name']}")

        # Redirect to dashboard (task runs in background)
        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.error(f"Validation error in start_indexing: {e}")
        return redirect(url_for('photographer_dashboard'))
    except Exception as e:
        logger.error(f"Error starting indexing for event {event_id}: {e}", exc_info=True)
        return redirect(url_for('photographer_dashboard'))

@app.route('/delete_event/<event_id>', methods=['POST'])
def delete_event(event_id):
    try:
        validate_event_id(event_id)

        db = get_db()
        event_to_delete = db.execute('SELECT qr_path FROM events WHERE id = ?', (event_id,)).fetchone()

        if event_to_delete:
            qr_path = os.path.join('static', event_to_delete['qr_path'])
            if os.path.exists(qr_path):
                try:
                    os.remove(qr_path)
                    logger.debug(f"Deleted QR code: {qr_path}")
                except OSError as e:
                    logger.warning(f"Failed to delete QR code {qr_path}: {e}")

            db.execute('DELETE FROM faces WHERE event_id = ?', (event_id,))
            db.execute('DELETE FROM events WHERE id = ?', (event_id,))
            db.commit()
            logger.info(f"Deleted event and associated faces: {event_id}")
        else:
            logger.warning(f"Attempted to delete non-existent event: {event_id}")

        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.error(f"Validation error in delete_event: {e}")
        return redirect(url_for('photographer_dashboard'))
    except Exception as e:
        logger.error(f"Error deleting event {event_id}: {e}", exc_info=True)
        return redirect(url_for('photographer_dashboard'))

@app.route('/set_folder/<event_id>/<folder_id>')
def set_folder(event_id, folder_id):
    try:
        # Validate IDs
        validate_event_id(event_id)
        validate_folder_id(folder_id)

        # Check authentication
        if 'credentials' not in session:
            logger.warning(f"Unauthenticated user attempted to set folder")
            return redirect(url_for('login_temp'))

        # Validate Google Drive access
        try:
            creds = Credentials(**session['credentials'])
            drive_service = build('drive', 'v3', credentials=creds)
            validate_google_drive_access(drive_service, folder_id)
        except GoogleDriveError as e:
            logger.error(f"Google Drive validation error: {e}")
            return render_template('error.html',
                error_message=f"Cannot access folder: {str(e)}"
            ), 403

        # Update database
        db = get_db()
        db.execute('UPDATE events SET drive_folder_id = ? WHERE id = ?', (folder_id, event_id))
        db.commit()
        logger.info(f"Set folder {folder_id} for event {event_id}")
        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.error(f"Validation error in set_folder: {e}")
        return render_template('error.html', error_message=str(e)), 400
    except Exception as e:
        logger.error(f"Error setting folder for event {event_id}: {e}", exc_info=True)
        return render_template('error.html', error_message="Failed to link folder"), 500

@app.route('/set_folder_from_link/<event_id>', methods=['POST'])
def set_folder_from_link(event_id):
    try:
        # Validate event ID
        validate_event_id(event_id)

        # Check authentication
        if 'credentials' not in session:
            logger.warning(f"Unauthenticated user attempted to set folder")
            return redirect(url_for('login_temp'))

        # Get and validate folder link
        link = request.form.get('folder_link', '').strip()
        if not link:
            raise ValidationError("Folder link is required")

        # Parse folder ID from link
        try:
            if '/folders/' in link:
                folder_id = link.split('/folders/')[-1]
            else:
                folder_id = link.split('/')[-1]

            # Clean up parameters
            if '?' in folder_id:
                folder_id = folder_id.split('?')[0]
            if '#' in folder_id:
                folder_id = folder_id.split('#')[0]

            validate_folder_id(folder_id)

        except (IndexError, AttributeError, ValidationError) as e:
            logger.warning(f"Invalid folder link format: {link}")
            return render_template('error.html',
                error_message="Invalid Google Drive folder URL format."
            ), 400

        # Validate Google Drive access
        try:
            creds = Credentials(**session['credentials'])
            drive_service = build('drive', 'v3', credentials=creds)
            validate_google_drive_access(drive_service, folder_id)
        except GoogleDriveError as e:
            logger.error(f"Google Drive validation error: {e}")
            return render_template('error.html',
                error_message=f"Cannot access folder: {str(e)}"
            ), 403

        # Update database
        db = get_db()
        db.execute('UPDATE events SET drive_folder_id = ? WHERE id = ?', (folder_id, event_id))
        db.commit()
        logger.info(f"Set folder {folder_id} for event {event_id} via link")
        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.error(f"Validation error in set_folder_from_link: {e}")
        return render_template('error.html', error_message=str(e)), 400
    except Exception as e:
        logger.error(f"Error setting folder from link for event {event_id}: {e}", exc_info=True)
        return render_template('error.html', error_message="Failed to link folder"), 500
    
# --- API Endpoints and Auth Routes (เหมือนเดิม) ---
@app.route('/api/check_auth')
def check_auth():
    if 'credentials' in session: return jsonify({'authenticated': True})
    else: return jsonify({'authenticated': False}), 401

@app.route('/api/folders')
def get_folders():
    if 'credentials' not in session:
        logger.warning("Unauthenticated request to /api/folders")
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        creds = Credentials(**session['credentials'])
        drive_service = build('drive', 'v3', credentials=creds)
        results = drive_service.files().list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            pageSize=100, fields="files(id, name)", orderBy="name"
        ).execute()
        folders = results.get('files', [])
        logger.debug(f"Retrieved {len(folders)} folders from Google Drive")
        return jsonify(folders), 200
    except HttpError as error:
        logger.error(f'Google Drive API error in get_folders: {error}', exc_info=True)
        return jsonify({'error': 'Failed to fetch folders'}), 500
    except Exception as error:
        logger.error(f'Unexpected error in get_folders: {error}', exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500
        
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
    """Initialize Google OAuth flow"""
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/cloud-platform'
    ]
    flow = Flow.from_client_secrets_file(
        Config.GOOGLE_CLIENT_SECRETS,
        scopes=SCOPES,
        redirect_uri=url_for('callback_temp', _external=True)
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback_temp')
def callback_temp():
    """Handle Google OAuth callback"""
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/cloud-platform'
    ]
    state = session['state']
    flow = Flow.from_client_secrets_file(
        Config.GOOGLE_CLIENT_SECRETS,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for('callback_temp', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    session['credentials'] = {'token': credentials.token, 'refresh_token': credentials.refresh_token, 'token_uri': credentials.token_uri, 'client_id': credentials.client_id, 'client_secret': credentials.client_secret, 'scopes': credentials.scopes}
    # แก้ให้ redirect ไปที่หน้า dashboard หลักเสมอหลัง login
    return redirect(url_for('photographer_dashboard'))

@app.route('/search_faces/<event_id>', methods=['POST'])
def search_faces(event_id):
    temp_files = []

    try:
        # Validate event ID
        validate_event_id(event_id)

        # Validate file upload
        if 'selfie_images' not in request.files:
            logger.warning(f"No images uploaded for event {event_id}")
            return "No images uploaded.", 400

        files = request.files.getlist('selfie_images')
        if len(files) == 0 or files[0].filename == '':
            logger.warning(f"No files selected for event {event_id}")
            return "No selected files.", 400

        if len(files) > 3:
            logger.warning(f"Too many files uploaded for event {event_id}: {len(files)}")
            return "Maximum 3 images allowed.", 400

        # Validate each file (type and size)
        for file in files:
            if file and file.filename:
                try:
                    validate_image_file(file)
                    validate_file_size(file, max_size_mb=10)
                except ValidationError as e:
                    logger.warning(f"File validation error: {e}")
                    return render_template('error.html', error_message=str(e)), 400

        logger.info(f"Processing {len(files)} uploaded image(s) for event {event_id}")

        # Process uploaded images
        uploaded_encodings = []

        # Extract face encodings from uploaded images
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
                    else:
                        logger.debug(f"No face found in uploaded image: {file.filename}")
                except ImageProcessingError as e:
                    logger.warning(f"Failed to process {file.filename}: {e}")
                    continue

        if not uploaded_encodings:
            logger.warning(f"No faces detected in any uploaded photos for event {event_id}")
            return "No faces detected in uploaded photos. Please try again with clear face photos.", 400

        # Create average encoding from uploaded faces
        search_encoding = create_average_encoding(uploaded_encodings)
        logger.info(f"Created average encoding from {len(uploaded_encodings)} face(s)")

        # Search in database
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

        logger.info(f"Checked {faces_checked} faces, found {len(matching_photos)} matching photos")

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

    except ValidationError as e:
        logger.error(f"Validation error in search_faces: {e}")
        return str(e), 400
    except Exception as e:
        logger.error(f"Error in search_faces for event {event_id}: {e}", exc_info=True)
        return f"An error occurred while processing: {str(e)}", 500

    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"Cleaned up temp file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file}: {e}")

# ============================================
# API Endpoints for Task Status
# ============================================

@app.route('/api/task/<task_id>')
def api_get_task_status(task_id):
    """
    Get task status by ID

    Returns:
        JSON: Task status information
    """
    task = get_task_status(task_id)

    if task is None:
        return jsonify({'error': 'Task not found'}), 404

    # Calculate progress percentage
    if task['total'] and task['total'] > 0:
        progress_percent = int((task['progress'] / task['total']) * 100)
    else:
        progress_percent = 0

    return jsonify({
        'id': task['id'],
        'status': task['status'],
        'progress': task['progress'],
        'total': task['total'],
        'progress_percent': progress_percent,
        'current_item': task['current_item'],
        'error': task['error'],
        'started_at': task['started_at'],
        'completed_at': task['completed_at'],
    })

@app.route('/api/event/<event_id>/task')
def api_get_event_task(event_id):
    """
    Get latest task for an event with event stats

    Returns:
        JSON: Task status information with event statistics
    """
    try:
        validate_event_id(event_id)
    except ValidationError:
        return jsonify({'error': 'Invalid event ID'}), 400

    task = get_event_latest_task(event_id)

    if task is None:
        return jsonify({'error': 'No task found for this event'}), 404

    # Get event statistics
    db = get_db()
    event = db.execute('SELECT indexed_photos, total_faces FROM events WHERE id = ?', (event_id,)).fetchone()

    # Calculate progress percentage
    if task['total'] and task['total'] > 0:
        progress_percent = int((task['progress'] / task['total']) * 100)
    else:
        progress_percent = 0

    response = {
        'id': task['id'],
        'status': task['status'],
        'progress': task['progress'],
        'total': task['total'],
        'progress_percent': progress_percent,
        'current_item': task['current_item'],
        'error': task['error'],
    }

    # Add event statistics if available
    if event:
        response['indexed_photos'] = event['indexed_photos'] or 0
        response['total_faces'] = event['total_faces'] or 0

    return jsonify(response)

if __name__ == '__main__':
    # Run Flask development server
    app.run(
        debug=Config.DEBUG,
        host=Config.HOST,
        port=Config.PORT
    )