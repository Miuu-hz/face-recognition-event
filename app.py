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
import threading
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv

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

    Returns True if:
    1. dlib was compiled with CUDA support, OR
    2. nvidia-smi detects GPU (as fallback check)
    """
    # Method 1: Check if dlib has CUDA support (most accurate)
    try:
        import dlib
        if hasattr(dlib, 'DLIB_USE_CUDA') and dlib.DLIB_USE_CUDA:
            return True
    except:
        pass

    # Method 2: Check nvidia-smi as fallback
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi'],
            capture_output=True,
            text=True,
            timeout=2
        )
        return result.returncode == 0
    except:
        pass

    return False

has_gpu = detect_gpu()

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

# --- In-Memory Encoding Cache ---
# Cache structure: {event_id: {'encodings': np.array, 'photo_ids': list, 'photo_names': list, 'timestamp': datetime}}
encoding_cache = {}
cache_lock = threading.Lock()  # Thread-safe cache access

def get_cached_encodings(event_id):
    """Get encodings from cache or database"""
    with cache_lock:
        if event_id in encoding_cache:
            logger.debug(f"Cache HIT for event {event_id}")
            return encoding_cache[event_id]

    logger.debug(f"Cache MISS for event {event_id}, loading from database...")

    # Load from database
    db = get_db()
    cursor = db.execute(
        'SELECT photo_id, photo_name, face_encoding FROM faces WHERE event_id = ? ORDER BY indexed_at',
        (event_id,)
    )
    rows = cursor.fetchall()

    if not rows:
        return None

    # Convert to arrays
    photo_ids = []
    photo_names = []
    stored_encodings = []

    for row in rows:
        photo_ids.append(row['photo_id'])
        photo_names.append(row['photo_name'])
        stored_encodings.append(np.frombuffer(row['face_encoding'], dtype=np.float64))

    # Stack into 2D array
    stored_encodings = np.array(stored_encodings)

    # Cache it
    cache_data = {
        'encodings': stored_encodings,
        'photo_ids': photo_ids,
        'photo_names': photo_names,
        'timestamp': datetime.now()
    }

    with cache_lock:
        encoding_cache[event_id] = cache_data
        logger.info(f"Cached {len(photo_ids)} encodings for event {event_id}")

    return cache_data

def invalidate_cache(event_id):
    """Invalidate cache when event is re-indexed"""
    with cache_lock:
        if event_id in encoding_cache:
            del encoding_cache[event_id]
            logger.info(f"Cache invalidated for event {event_id}")

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

# --- Checkpoint Management Functions ---
def ensure_checkpoint_table(db_conn):
    """Ensure indexing_checkpoints table exists, create if missing (auto-migration)"""
    try:
        # Check if table exists
        cursor = db_conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='indexing_checkpoints'
        """)

        if not cursor.fetchone():
            logger.info("Creating indexing_checkpoints table (auto-migration)...")
            # Create the table
            db_conn.execute("""
                CREATE TABLE indexing_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    photo_id TEXT NOT NULL,
                    photo_name TEXT NOT NULL,
                    faces_found INTEGER DEFAULT 0,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
                )
            """)

            # Create indexes
            db_conn.execute("""
                CREATE INDEX idx_checkpoints_event ON indexing_checkpoints(event_id)
            """)

            db_conn.execute("""
                CREATE INDEX idx_checkpoints_photo ON indexing_checkpoints(event_id, photo_id)
            """)

            db_conn.commit()
            logger.info("✅ Successfully created indexing_checkpoints table - Resume feature is now available!")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Error ensuring checkpoint table: {e}")
        return False

def get_checkpoints(db_conn, event_id):
    """Get all processed photo IDs from checkpoints for an event"""
    try:
        if not ensure_checkpoint_table(db_conn):
            return {}

        cursor = db_conn.execute(
            'SELECT photo_id, photo_name, faces_found FROM indexing_checkpoints WHERE event_id = ?',
            (event_id,)
        )
        checkpoints = cursor.fetchall()
        processed_ids = {row['photo_id']: {'name': row['photo_name'], 'faces': row['faces_found']} for row in checkpoints}
        return processed_ids
    except Exception as e:
        logger.warning(f"Error getting checkpoints: {e}. Continuing without resume functionality.")
        return {}

def save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_found):
    """Save a checkpoint after processing a photo"""
    try:
        if not ensure_checkpoint_table(db_conn):
            return

        db_conn.execute(
            'INSERT INTO indexing_checkpoints (event_id, photo_id, photo_name, faces_found) VALUES (?, ?, ?, ?)',
            (event_id, photo_id, photo_name, faces_found)
        )
        db_conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save checkpoint for {photo_name}: {e}")

def clear_checkpoints(db_conn, event_id):
    """Clear all checkpoints for an event (called on completion)"""
    try:
        if not ensure_checkpoint_table(db_conn):
            return

        db_conn.execute('DELETE FROM indexing_checkpoints WHERE event_id = ?', (event_id,))
        db_conn.commit()
        logger.info(f"Cleared checkpoints for event {event_id}")
    except Exception as e:
        logger.warning(f"Failed to clear checkpoints: {e}")

def count_checkpoints(db_conn, event_id):
    """Count number of checkpoints for an event"""
    try:
        if not ensure_checkpoint_table(db_conn):
            return 0

        cursor = db_conn.execute(
            'SELECT COUNT(*) as count FROM indexing_checkpoints WHERE event_id = ?',
            (event_id,)
        )
        return cursor.fetchone()['count']
    except Exception as e:
        logger.warning(f"Error counting checkpoints: {e}")
        return 0

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

def extract_face_encodings(image_path):
    """Extract face encodings from an image"""
    try:
        image = face_recognition.load_image_file(image_path)
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

def run_incremental_indexing_background(task, event_id, folder_id, credentials_dict):
    """Run INCREMENTAL face indexing (only NEW photos) using Drive Changes API"""
    db_conn = sqlite3.connect(DATABASE)
    db_conn.row_factory = sqlite3.Row

    try:
        task.start()

        # Validate credentials
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
        ensure_drive_token_column(db_conn)
        event_data = db_conn.execute(
            'SELECT name, drive_page_token FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()

        if not event_data:
            task.fail("Event not found")
            return

        logger.info(f"INCREMENTAL Task {task.id}: Starting incremental indexing for Event: {event_data['name']}")

        temp_files = []
        page_token = event_data['drive_page_token']

        # Get already indexed photos
        indexed_photos_rows = db_conn.execute(
            'SELECT DISTINCT photo_id FROM faces WHERE event_id = ?',
            (event_id,)
        ).fetchall()
        indexed_ids = {row['photo_id'] for row in indexed_photos_rows}

        # Also check checkpoints
        checkpoints_rows = db_conn.execute(
            'SELECT DISTINCT photo_id FROM indexing_checkpoints WHERE event_id = ?',
            (event_id,)
        ).fetchall()
        checkpoint_ids = {row['photo_id'] for row in checkpoints_rows}

        processed_ids = indexed_ids | checkpoint_ids

        # Get NEW photos using Drive Changes API
        new_photos = []

        if not page_token:
            # First time: get start token and do full list
            logger.info(f"Task {task.id}: Initializing Drive Changes API...")
            response = drive_service.changes().getStartPageToken().execute()
            new_page_token = response.get('startPageToken')

            # Do full list to get all photos
            query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
            results = drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=1000
            ).execute()
            all_photos = results.get('files', [])

            # Filter for unprocessed photos
            new_photos = [p for p in all_photos if p['id'] not in processed_ids]

            # Save token
            db_conn.execute(
                'UPDATE events SET drive_page_token = ? WHERE id = ?',
                (new_page_token, event_id)
            )
            db_conn.commit()

        else:
            # Use Changes API to get only changed files
            logger.info(f"Task {task.id}: Using Drive Changes API to find new photos...")
            new_page_token = page_token

            while True:
                try:
                    response = drive_service.changes().list(
                        pageToken=new_page_token,
                        spaces='drive',
                        fields='nextPageToken, newStartPageToken, changes(fileId, file(id, name, mimeType, parents, trashed))',
                        includeRemoved=True
                    ).execute()

                    changes = response.get('changes', [])

                    # Filter for new images in our folder
                    for change in changes:
                        file_info = change.get('file')
                        if not file_info:
                            continue

                        if (file_info.get('mimeType') in ['image/jpeg', 'image/png', 'image/jpg'] and
                            folder_id in file_info.get('parents', []) and
                            not file_info.get('trashed', False)):

                            file_id = file_info['id']
                            if file_id not in processed_ids:
                                new_photos.append({'id': file_id, 'name': file_info['name']})

                    # Update token
                    if 'newStartPageToken' in response:
                        new_page_token = response['newStartPageToken']
                        break

                    new_page_token = response.get('nextPageToken')
                    if not new_page_token:
                        break

                except HttpError as e:
                    if e.resp.status == 400:
                        # Token expired, reinitialize
                        logger.warning(f"Task {task.id}: Page token invalid, reinitializing...")
                        response = drive_service.changes().getStartPageToken().execute()
                        new_page_token = response.get('startPageToken')
                        break
                    raise

            # Save new token
            db_conn.execute(
                'UPDATE events SET drive_page_token = ? WHERE id = ?',
                (new_page_token, event_id)
            )
            db_conn.commit()

        total_new_photos = len(new_photos)

        if total_new_photos == 0:
            logger.info(f"Task {task.id}: No new photos found. Incremental indexing complete.")
            db_conn.execute(
                "UPDATE events SET indexing_status = ? WHERE id = ?",
                ('Completed', event_id)
            )
            db_conn.commit()
            task.complete()
            return

        logger.info(f"Task {task.id}: Found {total_new_photos} NEW photos to index")

        # Get current counts
        current_data = db_conn.execute(
            'SELECT indexed_photos, total_faces FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()
        indexed_photos = current_data['indexed_photos'] or 0
        total_faces = current_data['total_faces'] or 0

        # Process NEW photos only
        new_indexed = 0
        new_faces = 0

        for i, photo in enumerate(new_photos):
            photo_id = photo['id']
            photo_name = photo['name']

            task.update_progress(i, total_new_photos, photo_name, faces_found=total_faces + new_faces)
            logger.debug(f"Task {task.id}: Processing NEW photo {i+1}/{total_new_photos}: {photo_name}")

            faces_in_this_photo = 0
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
                    new_indexed += 1
                    continue

                if faces:
                    logger.debug(f"Task {task.id}: Found {len(faces)} faces in {photo_name}")
                    for face_data in faces:
                        encoding_blob = face_data['encoding'].tobytes()
                        location_json = json.dumps(face_data['location'])

                        db_conn.execute(
                            'INSERT INTO faces (event_id, photo_id, photo_name, face_encoding, face_location) VALUES (?, ?, ?, ?, ?)',
                            (event_id, photo_id, photo_name, encoding_blob, location_json)
                        )
                        new_faces += 1
                        faces_in_this_photo += 1
                else:
                    logger.debug(f"Task {task.id}: No faces found in {photo_name}")

            except Exception as e:
                logger.error(f"Task {task.id}: Error processing {photo_name}: {e}")

            new_indexed += 1

            # Save checkpoint
            save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_in_this_photo)

            # Update database progress
            db_conn.execute(
                "UPDATE events SET indexed_photos = ?, total_faces = ? WHERE id = ?",
                (indexed_photos + new_indexed, total_faces + new_faces, event_id)
            )
            db_conn.commit()

        # Update final status
        db_conn.execute(
            "UPDATE events SET indexing_status = ?, indexed_photos = ?, total_faces = ? WHERE id = ?",
            ('Completed', indexed_photos + new_indexed, total_faces + new_faces, event_id)
        )
        db_conn.commit()

        # Clear checkpoints
        clear_checkpoints(db_conn, event_id)

        # Invalidate cache
        invalidate_cache(event_id)

        task.complete()
        logger.info(f"Task {task.id}: INCREMENTAL indexing completed. New Photos: {new_indexed}, New Faces: {new_faces}")

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
        db_conn.close()

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
            # Check for existing checkpoints (resume functionality)
            processed_photos = get_checkpoints(db_conn, event_id)
            resuming = len(processed_photos) > 0

            if resuming:
                # Resume from previous progress
                logger.info(f"Task {task.id}: Resuming from checkpoint - {len(processed_photos)} photos already processed")
                # Count faces from checkpoints
                total_faces = sum(p['faces'] for p in processed_photos.values())
                indexed_photos = len(processed_photos)
            else:
                logger.info(f"Task {task.id}: Starting fresh indexing (no checkpoints found)")

            # Get all images from the folder
            query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
            results = drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=100
            ).execute()
            photos = results.get('files', [])

            total_photos = len(photos)
            task.update_progress(indexed_photos, total_photos, None, faces_found=total_faces)

            if resuming:
                logger.info(f"Task {task.id}: Found {total_photos} total photos ({len(processed_photos)} already done, {total_photos - len(processed_photos)} remaining)")
            else:
                logger.info(f"Task {task.id}: Found {total_photos} photos to process")

            # Process photos in batches
            batch_size = FACE_RECOGNITION_CONFIG['batch_size']
            for i in range(0, len(photos), batch_size):
                batch = photos[i:i+batch_size]
                logger.debug(f"Task {task.id}: Processing batch {i//batch_size + 1} ({len(batch)} photos)")

                for photo in batch:
                    photo_id = photo['id']
                    photo_name = photo['name']

                    # Skip if already processed (resume functionality)
                    if photo_id in processed_photos:
                        logger.debug(f"Task {task.id}: Skipping {photo_name} (already processed)")
                        continue

                    # Update task progress
                    task.update_progress(indexed_photos, total_photos, photo_name, faces_found=total_faces)
                    logger.debug(f"Task {task.id}: Processing {photo_name}")

                    faces_in_this_photo = 0
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
                                faces_in_this_photo += 1
                        else:
                            logger.debug(f"Task {task.id}: No faces found in {photo_name}")

                    except Exception as e:
                        logger.error(f"Task {task.id}: Error processing {photo_name}: {e}")
                        # Continue with next photo

                    indexed_photos += 1

                    # Save checkpoint for resume functionality
                    save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_in_this_photo)

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

            # Clear checkpoints on successful completion
            clear_checkpoints(db_conn, event_id)

            # Invalidate cache so next search will use fresh data
            invalidate_cache(event_id)

            task.complete()
            logger.info(f"Task {task.id}: Indexing completed successfully. Photos: {indexed_photos}, Faces: {total_faces}")

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
    """Landing page for public users"""
    return render_template('index.html')

@app.route('/events')
def events_list():
    """List all completed events for public users"""
    db = get_db()
    # Only show completed events to public
    events_from_db = db.execute(
        "SELECT * FROM events WHERE indexing_status = 'Completed' ORDER BY created_at DESC"
    ).fetchall()

    events = [dict(event) for event in events_from_db]
    return render_template('events.html', events=events)

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

        # Reset status if stuck (In Progress but no active task)
        if event_data['indexing_status'] == 'In Progress':
            task_id = event_data['task_id']
            if task_id:
                task = get_task(task_id)
                if not task or task.status in ['completed', 'failed']:
                    # Task is dead, reset to Failed so we can restart
                    logger.info(f"Resetting stuck event {event_id} from 'In Progress' to 'Failed'")
                    db.execute("UPDATE events SET indexing_status = 'Failed' WHERE id = ?", (event_id,))
                    db.commit()

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

        # Invalidate cache before starting new indexing
        invalidate_cache(event_id)

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

@app.route('/start_incremental_indexing/<event_id>')
def start_incremental_indexing(event_id):
    """Start incremental indexing for NEW photos only (much faster!)"""
    try:
        event_id = validate_event_id(event_id)

        db = get_db()
        event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()

        if not event_data:
            raise ValidationError('Event not found')

        if 'credentials' not in session:
            logger.warning("User not authenticated, redirecting to login")
            return redirect(url_for('login_temp'))

        credentials_dict = session['credentials']
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if field not in credentials_dict or not credentials_dict[field]]

        if missing_fields:
            logger.warning(f"Credentials missing fields: {missing_fields}. Forcing re-authentication.")
            session.pop('credentials', None)
            return redirect(url_for('login_temp'))

        folder_id = event_data['drive_folder_id']
        if not folder_id:
            raise ValidationError('No Google Drive folder linked')

        folder_id = validate_folder_id(folder_id)

        # Create background task
        task = create_task('incremental_indexing')

        # Update status to In Progress
        db.execute(
            "UPDATE events SET indexing_status = ?, task_id = ? WHERE id = ?",
            ('In Progress', task.id, event_id)
        )
        db.commit()

        # Start background thread for INCREMENTAL indexing
        thread = threading.Thread(
            target=run_incremental_indexing_background,
            args=(task, event_id, folder_id, credentials_dict)
        )
        thread.daemon = True
        thread.start()

        logger.info(f"Started INCREMENTAL indexing task {task.id} for event {event_id}")

        return redirect(url_for('photographer_dashboard'))

    except ValidationError as e:
        logger.warning(f"Validation error in start_incremental_indexing: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error starting incremental indexing: {e}", exc_info=True)
        return jsonify({'error': 'Failed to start incremental indexing'}), 500

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

@app.route('/api/event/<event_id>/checkpoint/status')
def get_checkpoint_status(event_id):
    """Get checkpoint status for an event (for resume indicator)"""
    db = get_db()
    try:
        checkpoint_count = count_checkpoints(db, event_id)
        event_data = db.execute('SELECT indexing_status, task_id FROM events WHERE id = ?', (event_id,)).fetchone()

        if not event_data:
            return jsonify({'error': 'Event not found'}), 404

        # Check if event is stuck (In Progress but no active task)
        is_stuck = False
        if event_data['indexing_status'] == 'In Progress' and event_data['task_id']:
            task = get_task(event_data['task_id'])
            if not task or task.status in ['completed', 'failed']:
                is_stuck = True

        return jsonify({
            'has_checkpoints': checkpoint_count > 0,
            'checkpoint_count': checkpoint_count,
            'indexing_status': event_data['indexing_status'],
            'is_stuck': is_stuck,
            'can_resume': checkpoint_count > 0 and event_data['indexing_status'] in ['Not Started', 'Failed']
        })
    except Exception as e:
        logger.error(f"Error getting checkpoint status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/reset_event/<event_id>', methods=['POST'])
def reset_event(event_id):
    """Reset a stuck event back to Failed status"""
    try:
        event_id = validate_event_id(event_id)
        db = get_db()

        event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event_data:
            return jsonify({'error': 'Event not found'}), 404

        # Reset to Failed so user can restart/resume
        db.execute("UPDATE events SET indexing_status = 'Failed' WHERE id = ?", (event_id,))
        db.commit()

        logger.info(f"Manually reset event {event_id} to Failed status")
        return redirect(url_for('photographer_dashboard'))

    except Exception as e:
        logger.error(f"Error resetting event: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pause_indexing/<event_id>', methods=['POST'])
def pause_indexing(event_id):
    """Pause ongoing indexing task"""
    try:
        event_id = validate_event_id(event_id)
        db = get_db()

        event_data = db.execute('SELECT task_id FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event_data:
            return jsonify({'error': 'Event not found'}), 404

        # Mark task as failed to stop it
        task_id = event_data['task_id']
        if task_id:
            task = get_task(task_id)
            if task:
                task.fail("Paused by user")

        # Change status to Paused (keep checkpoint data)
        db.execute("UPDATE events SET indexing_status = 'Paused' WHERE id = ?", (event_id,))
        db.commit()

        logger.info(f"Paused indexing for event {event_id}")
        return redirect(url_for('photographer_dashboard'))

    except Exception as e:
        logger.error(f"Error pausing indexing: {e}")
        return jsonify({'error': str(e)}), 500

def ensure_drive_token_column(db_conn):
    """Ensure drive_page_token column exists in events table"""
    try:
        cursor = db_conn.execute("PRAGMA table_info(events)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'drive_page_token' not in columns:
            logger.info("Adding drive_page_token column to events table (auto-migration)...")
            db_conn.execute("ALTER TABLE events ADD COLUMN drive_page_token TEXT")
            db_conn.commit()
            logger.info("✅ Successfully added drive_page_token column")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Error ensuring drive_page_token column: {e}")
        return False

@app.route('/api/event/<event_id>/new_photos')
def check_new_photos(event_id):
    """Check for new photos using Google Drive Changes API (much faster!)"""
    try:
        event_id = validate_event_id(event_id)

        if 'credentials' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        db = get_db()

        # Ensure column exists
        ensure_drive_token_column(db)

        event_data = db.execute(
            'SELECT drive_folder_id, drive_page_token, indexing_status FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()

        if not event_data or not event_data['drive_folder_id']:
            return jsonify({'error': 'Event or folder not found'}), 404

        # Only check if indexing is completed or paused
        if event_data['indexing_status'] not in ['Completed', 'Paused']:
            return jsonify({'new_photos': 0, 'total_photos': 0})

        # Build Google Drive service
        credentials_dict = session['credentials']
        creds = Credentials(**credentials_dict)
        drive_service = build('drive', 'v3', credentials=creds)

        folder_id = event_data['drive_folder_id']
        page_token = event_data['drive_page_token']

        # Get indexed photo IDs from database
        indexed_photos = db.execute(
            'SELECT DISTINCT photo_id FROM faces WHERE event_id = ?',
            (event_id,)
        ).fetchall()
        indexed_ids = {row['photo_id'] for row in indexed_photos}

        # Also check checkpoints
        checkpoints = db.execute(
            'SELECT DISTINCT photo_id FROM indexing_checkpoints WHERE event_id = ?',
            (event_id,)
        ).fetchall()
        checkpoint_ids = {row['photo_id'] for row in checkpoints}

        processed_ids = indexed_ids | checkpoint_ids

        # If no page token, initialize with current state
        if not page_token:
            logger.info(f"Initializing Drive Changes API for event {event_id}")
            # Get start page token for this folder
            response = drive_service.changes().getStartPageToken().execute()
            new_page_token = response.get('startPageToken')

            # Save token
            db.execute(
                'UPDATE events SET drive_page_token = ? WHERE id = ?',
                (new_page_token, event_id)
            )
            db.commit()

            # First time: do full check
            query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
            results = drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=1000
            ).execute()
            drive_photos = results.get('files', [])
            new_photos = [photo for photo in drive_photos if photo['id'] not in processed_ids]

            return jsonify({
                'new_photos': len(new_photos),
                'total_photos': len(drive_photos),
                'indexed_photos': len(processed_ids),
                'has_new': len(new_photos) > 0
            })

        # Use Changes API to get only changed files
        logger.debug(f"Checking Drive changes for event {event_id} with token {page_token}")

        new_photo_ids = set()
        new_page_token = page_token

        while True:
            try:
                response = drive_service.changes().list(
                    pageToken=new_page_token,
                    spaces='drive',
                    fields='nextPageToken, newStartPageToken, changes(fileId, file(id, name, mimeType, parents, trashed))',
                    includeRemoved=True
                ).execute()

                changes = response.get('changes', [])

                # Filter for new images in our folder
                for change in changes:
                    file_info = change.get('file')
                    if not file_info:
                        continue

                    # Check if it's an image in our folder
                    if (file_info.get('mimeType') in ['image/jpeg', 'image/png', 'image/jpg'] and
                        folder_id in file_info.get('parents', []) and
                        not file_info.get('trashed', False)):

                        file_id = file_info['id']
                        # Check if not already processed
                        if file_id not in processed_ids:
                            new_photo_ids.add(file_id)

                # Update token
                if 'newStartPageToken' in response:
                    new_page_token = response['newStartPageToken']
                    break

                new_page_token = response.get('nextPageToken')
                if not new_page_token:
                    break

            except HttpError as e:
                if e.resp.status == 400:
                    # Token expired or invalid, reinitialize
                    logger.warning(f"Page token invalid for event {event_id}, reinitializing...")
                    response = drive_service.changes().getStartPageToken().execute()
                    new_page_token = response.get('startPageToken')
                    db.execute(
                        'UPDATE events SET drive_page_token = ? WHERE id = ?',
                        (new_page_token, event_id)
                    )
                    db.commit()
                    return jsonify({'new_photos': 0, 'total_photos': len(processed_ids), 'has_new': False})
                raise

        # Save new token
        if new_page_token != page_token:
            db.execute(
                'UPDATE events SET drive_page_token = ? WHERE id = ?',
                (new_page_token, event_id)
            )
            db.commit()
            logger.debug(f"Updated page token for event {event_id}")

        return jsonify({
            'new_photos': len(new_photo_ids),
            'total_photos': len(processed_ids) + len(new_photo_ids),
            'indexed_photos': len(processed_ids),
            'has_new': len(new_photo_ids) > 0
        })

    except Exception as e:
        logger.error(f"Error checking new photos: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/event/<event_id>')
def event_page(event_id):
    db = get_db()
    event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event_data:
        return "Event not found.", 404
    # ส่ง event_id ไปให้ template ด้วย
    return render_template('event_page.html', event_name=event_data['name'], event_id=event_id)

@app.route('/login')
def login():
    """Photographer login page"""
    return render_template('login.html')

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

@app.route('/logout')
def logout():
    """Logout route - clears session and redirects to landing page"""
    session.clear()
    logger.info("User logged out successfully")
    return redirect(url_for('index'))

@app.route('/search_faces/<event_id>', methods=['POST'])
def search_faces(event_id):
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

        # Process uploaded images
        uploaded_encodings = []
        temp_files = []

        try:
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
                    except ImageProcessingError as e:
                        logger.warning(f"Skipping {file.filename}: {e}")
        
            if not uploaded_encodings:
                raise ValidationError("No faces detected in uploaded photos. Please try again with clear face photos")

            # Create average encoding from uploaded faces
            search_encoding = create_average_encoding(uploaded_encodings)
            logger.info(f"Created average encoding from {len(uploaded_encodings)} face(s) for event {event_id}")

            # Search in database - OPTIMIZED with cache + vectorized comparison
            cache_data = get_cached_encodings(event_id)

            if not cache_data:
                logger.info(f"No faces found for event {event_id}")
                matching_photos = {}
                faces_checked = 0
            else:
                # Get data from cache (already in optimal format!)
                stored_encodings = cache_data['encodings']
                photo_ids = cache_data['photo_ids']
                photo_names = cache_data['photo_names']
                faces_checked = len(photo_ids)

                # Vectorized distance calculation (10-50x faster than loop!)
                distances = face_recognition.face_distance(stored_encodings, search_encoding)

                # Find matches
                matching_photos = {}
                tolerance = FACE_RECOGNITION_CONFIG['tolerance']

                for idx, distance in enumerate(distances):
                    if distance <= tolerance:
                        photo_id = photo_ids[idx]
                        photo_name = photo_names[idx]

                        # Keep best match for each photo
                        if photo_id not in matching_photos:
                            matching_photos[photo_id] = {
                                'name': photo_name,
                                'distance': float(distance)
                            }
                        else:
                            if distance < matching_photos[photo_id]['distance']:
                                matching_photos[photo_id]['distance'] = float(distance)

                        logger.debug(f"Match found: {photo_name} (distance: {distance:.3f})")

            logger.info(f"Search completed for event {event_id}: Checked {faces_checked} faces, found {len(matching_photos)} matching photos (cached + vectorized)")

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

# Error Handlers
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors with custom page"""
    logger.warning(f"404 error: {request.url}")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors with custom page"""
    logger.error(f"500 error: {str(e)}", exc_info=True)
    return render_template('500.html'), 500

if __name__ == '__main__':
    print_config()
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('DEBUG', 'True').lower() == 'true'
    app.run(host=host, port=port, debug=debug)