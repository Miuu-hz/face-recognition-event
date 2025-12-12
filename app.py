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

# Import face recognition services
from services import face_encoder, face_matcher, face_database, indexing_service, search_service
from services.face_encoder import ImageProcessingError as ServiceImageProcessingError
from services.face_matcher import FaceMatcherError
from services.face_database import FaceDatabaseError
from services.indexing_service import IndexingError
from services.search_service import SearchError

# Optional PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    from psycopg2 import pool
    HAS_POSTGRESQL = True
except ImportError:
    HAS_POSTGRESQL = False

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

# Alias service exception for backward compatibility
ImageProcessingError = ServiceImageProcessingError

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

# --- Database Configuration ---
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'sqlite').lower()  # 'sqlite' or 'postgresql'

# SQLite Configuration
DATABASE = os.getenv('DATABASE_PATH', 'database.db')

# PostgreSQL Configuration
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', '5432')),
    'database': os.getenv('POSTGRES_DB', 'face_recognition'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
}

# PostgreSQL Connection Pool (initialized later)
pg_pool = None

def init_postgres_pool():
    """Initialize PostgreSQL connection pool"""
    global pg_pool
    if DATABASE_TYPE == 'postgresql' and HAS_POSTGRESQL:
        try:
            pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                **POSTGRES_CONFIG
            )
            logger.info("✅ PostgreSQL connection pool initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize PostgreSQL pool: {e}")
            return False
    return True

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

# --- In-Memory Encoding Cache (delegated to services) ---
# Use face_matcher.cache for all cache operations

def get_cached_encodings(event_id):
    """Get encodings from cache or database (backward compatibility wrapper)"""
    cache_data = face_matcher.cache.get(event_id)
    if cache_data:
        return cache_data

    # Load from database if not in cache
    db = get_db()
    return face_matcher.load_encodings_from_db(db, event_id)

def invalidate_cache(event_id):
    """Invalidate cache when event is re-indexed (backward compatibility wrapper)"""
    face_matcher.cache.invalidate(event_id)

# Print configuration on startup
def print_config():
    """Print face recognition and database configuration"""
    print("\n" + "="*50)
    print("Face Recognition Configuration:")
    print("="*50)
    print(f"Device:       {'GPU (CUDA)' if has_gpu else 'CPU'}")
    print(f"Model:        {FACE_RECOGNITION_CONFIG['model'].upper()} ({'CNN - High Accuracy' if face_model == 'cnn' else 'HOG - Fast'})")
    print(f"Tolerance:    {FACE_RECOGNITION_CONFIG['tolerance']} (lower = stricter)")
    print(f"Batch Size:   {FACE_RECOGNITION_CONFIG['batch_size']} images")
    print(f"Num Jitters:  {FACE_RECOGNITION_CONFIG['num_jitters']}")
    print("="*50)

    print("\nDatabase Configuration:")
    print("="*50)
    print(f"Type:         {DATABASE_TYPE.upper()}")
    if DATABASE_TYPE == 'postgresql':
        if HAS_POSTGRESQL:
            print(f"Host:         {POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}")
            print(f"Database:     {POSTGRES_CONFIG['database']}")
            print(f"User:         {POSTGRES_CONFIG['user']}")
            print(f"Pool:         {'✅ Enabled' if pg_pool else '⏳ Initializing...'}")
        else:
            print("Status:       ❌ psycopg2 not installed (falling back to SQLite)")
    else:
        print(f"Path:         {DATABASE}")
    print("="*50 + "\n")

# --- Checkpoint Management Functions (delegated to services) ---
def ensure_checkpoint_table(db_conn):
    """Ensure indexing_checkpoints table exists (backward compatibility wrapper)"""
    return face_database.ensure_checkpoint_table(db_conn)

def get_checkpoints(db_conn, event_id):
    """Get all processed photo IDs from checkpoints (backward compatibility wrapper)"""
    return face_database.get_checkpoints(db_conn, event_id)

def save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_found):
    """Save a checkpoint after processing a photo (backward compatibility wrapper)"""
    face_database.save_checkpoint(db_conn, event_id, photo_id, photo_name, faces_found)

def clear_checkpoints(db_conn, event_id):
    """Clear all checkpoints for an event (backward compatibility wrapper)"""
    face_database.clear_checkpoints(db_conn, event_id)

def count_checkpoints(db_conn, event_id):
    """Count number of checkpoints for an event (backward compatibility wrapper)"""
    return face_database.count_checkpoints(db_conn, event_id)

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

# --- Database Wrapper Class ---
class DatabaseWrapper:
    """Wrapper to provide unified interface for SQLite and PostgreSQL"""

    def __init__(self, conn, db_type):
        self.conn = conn
        self.db_type = db_type

        # Set row_factory for dict-like access
        if db_type == 'sqlite':
            conn.row_factory = sqlite3.Row
        elif db_type == 'postgresql':
            # PostgreSQL cursor will use RealDictCursor
            pass

    def execute(self, query, params=()):
        """Execute query with automatic parameter substitution"""
        if self.db_type == 'postgresql':
            # Convert SQLite ? placeholders to PostgreSQL %s
            query = query.replace('?', '%s')
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cursor = self.conn.cursor()

        cursor.execute(query, params)
        return cursor

    def commit(self):
        """Commit transaction"""
        self.conn.commit()

    def rollback(self):
        """Rollback transaction"""
        self.conn.rollback()

    def close(self):
        """Close connection"""
        if self.db_type == 'postgresql' and pg_pool:
            # Return connection to pool instead of closing
            pg_pool.putconn(self.conn)
        else:
            self.conn.close()

    def __getattr__(self, name):
        """Forward unknown attributes to underlying connection"""
        return getattr(self.conn, name)

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
    """Get database connection (SQLite or PostgreSQL based on config)"""
    db = getattr(g, '_database', None)
    if db is None:
        if DATABASE_TYPE == 'postgresql' and HAS_POSTGRESQL:
            # Get connection from PostgreSQL pool
            if not pg_pool:
                init_postgres_pool()

            if pg_pool:
                conn = pg_pool.getconn()
                db = g._database = DatabaseWrapper(conn, 'postgresql')
                logger.debug("PostgreSQL connection acquired from pool")
            else:
                # Fallback to SQLite if PostgreSQL pool failed
                logger.warning("PostgreSQL pool not available, falling back to SQLite")
                conn = sqlite3.connect(DATABASE)
                db = g._database = DatabaseWrapper(conn, 'sqlite')
        else:
            # Use SQLite
            conn = sqlite3.connect(DATABASE)
            db = g._database = DatabaseWrapper(conn, 'sqlite')
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection (return to pool for PostgreSQL)"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def get_db_connection():
    """Get raw database connection for background threads (not Flask context-aware)"""
    if DATABASE_TYPE == 'postgresql' and HAS_POSTGRESQL and pg_pool:
        conn = pg_pool.getconn()
        return DatabaseWrapper(conn, 'postgresql')
    else:
        conn = sqlite3.connect(DATABASE)
        return DatabaseWrapper(conn, 'sqlite')


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
    

# --- Helper Functions for Face Recognition (delegated to services) ---
def download_image_temp(drive_service, photo_id):
    """Download image from Google Drive to temp file (backward compatibility wrapper)"""
    try:
        return indexing_service.download_image_from_drive(drive_service, photo_id, max_retries=3)
    except IndexingError as e:
        raise GoogleDriveError(str(e))

# --- Face Encoding Functions (delegated to services) ---
def extract_face_encodings(image_path):
    """Extract face encodings from an image (backward compatibility wrapper)"""
    return face_encoder.extract_face_encodings(
        image_path,
        model=FACE_RECOGNITION_CONFIG['model'],
        num_jitters=FACE_RECOGNITION_CONFIG['num_jitters']
    )

def create_average_encoding(encodings):
    """Create average encoding from multiple face encodings (backward compatibility wrapper)"""
    return face_encoder.create_average_encoding(encodings)

def run_incremental_indexing_background(task, event_id, folder_id, credentials_dict):
    """Run INCREMENTAL face indexing (delegated to services)"""
    db_conn = get_db_connection()
    try:
        indexing_service.run_incremental_indexing(
            task, event_id, folder_id, credentials_dict, db_conn, FACE_RECOGNITION_CONFIG
        )
        # Invalidate cache after successful indexing
        invalidate_cache(event_id)
    finally:
        db_conn.close()

def run_indexing_background(task, event_id, folder_id, credentials_dict):
    """Run full face indexing (delegated to services)"""
    db_conn = get_db_connection()
    try:
        indexing_service.run_full_indexing(
            task, event_id, folder_id, credentials_dict, db_conn, FACE_RECOGNITION_CONFIG
        )
        # Invalidate cache after successful indexing
        invalidate_cache(event_id)
    finally:
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
            q="mimeType='application/vnd.google-apps.folder' and trashed=false and 'me' in owners",
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
    """Ensure drive_page_token column exists (backward compatibility wrapper)"""
    return indexing_service.ensure_drive_token_column(db_conn)

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

        # Validate uploaded files
        if 'selfie_images' not in request.files:
            raise ValidationError("No images uploaded")

        files = request.files.getlist('selfie_images')
        search_service.validate_uploaded_files(files, max_files=3, max_size_mb=10)

        # Perform search using service
        db = get_db()
        result = search_service.search_faces_by_selfies(
            db,
            event_id,
            files,
            tolerance=FACE_RECOGNITION_CONFIG['tolerance'],
            config=FACE_RECOGNITION_CONFIG
        )

        # Extract URLs for template
        photo_urls = [match['url'] for match in result['matches']]

        logger.info(f"Search completed: {result['total_matches']} matches found")

        return render_template('results_page.html',
                             photo_links=photo_urls,
                             event_id=event_id,
                             matches_count=result['total_matches'])

    except SearchError as e:
        logger.error(f"Search error: {e}")
        return str(e), 400
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
    # Initialize PostgreSQL connection pool if needed
    if DATABASE_TYPE == 'postgresql':
        if not init_postgres_pool():
            print("⚠️  Warning: Failed to initialize PostgreSQL pool, falling back to SQLite")

    print_config()
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('DEBUG', 'True').lower() == 'true'
    app.run(host=host, port=port, debug=debug)