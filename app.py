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
def validate_event_name(name):
    """Validate event name"""
    if not name or not isinstance(name, str):
        raise ValidationError("Event name is required")

    # Strip whitespace
    name = name.strip()

    if len(name) < 3:
        raise ValidationError("Event name must be at least 3 characters long")

    if len(name) > 100:
        raise ValidationError("Event name must not exceed 100 characters")

    # Check for basic alphanumeric and common punctuation
    import re
    if not re.match(r'^[\w\s\-\(\)\[\].,!?]+$', name, re.UNICODE):
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
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            self.status = 'running'
            self.started_at = datetime.now()

    def update_progress(self, progress, total, current_item=None):
        with self.lock:
            self.progress = progress
            self.total = total
            self.current_item = current_item

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
            return {
                'id': self.id,
                'type': self.type,
                'status': self.status,
                'progress': self.progress,
                'total': self.total,
                'progress_percent': int((self.progress / self.total * 100)) if self.total > 0 else 0,
                'current_item': self.current_item,
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

def run_indexing_background(task, event_id, folder_id, credentials_dict):
    """Run face indexing in background thread"""
    # Create new database connection for this thread
    db_conn = sqlite3.connect(DATABASE)
    db_conn.row_factory = sqlite3.Row

    try:
        task.start()

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
            task.update_progress(0, total_photos, None)

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
                    task.update_progress(indexed_photos, total_photos, photo_name)
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
            raise ValidationError('Not authenticated')

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

        # Get credentials from session
        credentials_dict = session['credentials']

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
    db = get_db()
    db.execute('UPDATE events SET drive_folder_id = ? WHERE id = ?', (folder_id, event_id))
    db.commit()
    print(f"Set folder {folder_id} for event {event_id}")
    return redirect(url_for('photographer_dashboard'))

@app.route('/set_folder_from_link/<event_id>', methods=['POST'])
def set_folder_from_link(event_id):
    link = request.form['folder_link']
    try:
        if '/folders/' in link: folder_id = link.split('/folders/')[-1]
        else: folder_id = link.split('/')[-1]
        if '?' in folder_id: folder_id = folder_id.split('?')[0]
        if '#' in folder_id: folder_id = folder_id.split('#')[0]
    except (IndexError, AttributeError):
        return "Invalid Google Drive Folder URL format.", 400
    
    db = get_db()
    db.execute('UPDATE events SET drive_folder_id = ? WHERE id = ?', (folder_id, event_id))
    db.commit()
    print(f"Set folder {folder_id} for event {event_id} via link")
    return redirect(url_for('photographer_dashboard'))
    
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
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
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
    session['credentials'] = {'token': credentials.token, 'refresh_token': credentials.refresh_token, 'token_uri': credentials.token_uri, 'client_id': credentials.client_id, 'client_secret': credentials.client_secret, 'scopes': credentials.scopes}
    # แก้ให้ redirect ไปที่หน้า dashboard หลักเสมอหลัง login
    return redirect(url_for('photographer_dashboard'))

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

            logger.info(f"Search completed for event {event_id}: Checked {faces_checked} faces, found {len(matching_photos)} matching photos")

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
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('DEBUG', 'True').lower() == 'true'
    app.run(host=host, port=port, debug=debug)