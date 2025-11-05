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
from datetime import datetime
from PIL import Image

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
            print(f"✓ GPU detected: {torch.cuda.get_device_name(0)}")
            return True
        else:
            print("○ No GPU detected, using CPU")
            return False
    except ImportError:
        # ถ้าไม่มี PyTorch ลองเช็คด้วยวิธีอื่น
        try:
            # เช็คว่า dlib ถูก compile ด้วย CUDA support หรือไม่
            import dlib
            if dlib.DLIB_USE_CUDA:
                print("✓ GPU detected: dlib with CUDA support")
                return True
            else:
                print("○ dlib without CUDA support, using CPU")
                return False
        except (ImportError, AttributeError):
            print("○ No GPU detection available, defaulting to CPU")
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
        print(f"Warning: Invalid FACE_MODEL '{Config.FACE_MODEL}', defaulting to 'hog'")
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
    print("\n" + "="*50)
    print("Face Recognition Configuration:")
    print("="*50)
    print(f"Device:       {'GPU (CUDA)' if config['use_gpu'] else 'CPU'}")
    print(f"Model:        {config['model'].upper()} ({'CNN - High Accuracy' if config['model'] == 'cnn' else 'HOG - Fast Processing'})")
    print(f"  (Setting: {Config.FACE_MODEL})")
    print(f"Tolerance:    {config['tolerance']} (lower = stricter)")
    print(f"Batch Size:   {config['batch_size']} images")
    print(f"Num Jitters:  {config['num_jitters']}")
    print("="*50 + "\n")

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
            # ถ้าหาไฟล์ schema.sql ไม่เจอ ให้แจ้งเตือนและหยุดทำงาน
            print("\nERROR: 'schema.sql' not found in the project directory.")
            print("Please make sure the file exists and is named correctly.\n")
            return False # คืนค่าว่าทำงานไม่สำเร็จ

        with app.app_context():
            db = get_db()
            with open(schema_path, 'r', encoding='utf-8') as f:
                db.cursor().executescript(f.read())
            db.commit()
        return True # คืนค่าว่าทำงานสำเร็จ
    except Exception as e:
        print(f"\nAn error occurred during DB initialization: {e}\n")
        return False
    

# --- Helper Functions for Face Recognition ---
def download_image_temp(drive_service, photo_id):
    """Download image from Google Drive to temp file"""
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
        print(f"Error downloading image {photo_id}: {e}")
        return None

def extract_face_encodings(image_path):
    """
    Extract face encodings from an image
    ใช้ config ที่ detect GPU/CPU อัตโนมัติ
    """
    try:
        image = face_recognition.load_image_file(image_path)

        # ใช้ model ที่เหมาะสมตาม GPU/CPU
        face_locations = face_recognition.face_locations(
            image,
            model=FACE_RECOGNITION_CONFIG['model']
        )

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
        return results
    except Exception as e:
        print(f"Error extracting faces from {image_path}: {e}")
        return []

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
    event_name = request.form['event_name']
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
    return redirect(url_for('photographer_dashboard'))

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

    try:
        # Update task to running
        update_task_status(task_id, 'running', progress=0, total=0)

        # Build Google Drive service
        creds = Credentials(**credentials_dict)
        drive_service = build('drive', 'v3', credentials=creds)

        print(f"[Task {task_id}] Starting Face Indexing for Event: {event_id}")

        # Get all images from the folder
        query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
        results = drive_service.files().list(
            q=query,
            fields="files(id, name)",
            pageSize=100
        ).execute()
        photos = results.get('files', [])

        total_photos = len(photos)
        print(f"[Task {task_id}] Found {total_photos} photos to process")

        # Update task with total
        update_task_status(task_id, 'running', progress=0, total=total_photos)
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('In Progress', event_id))
        db_conn.commit()

        # Process photos in batches
        batch_size = FACE_RECOGNITION_CONFIG['batch_size']
        for i in range(0, len(photos), batch_size):
            batch = photos[i:i+batch_size]
            print(f"[Task {task_id}] Processing batch {i//batch_size + 1} ({len(batch)} photos)...")

            for photo in batch:
                photo_id = photo['id']
                photo_name = photo['name']
                print(f"[Task {task_id}]   Processing: {photo_name}")

                # Update current item
                update_task_status(
                    task_id,
                    'running',
                    progress=indexed_photos,
                    current_item=photo_name
                )

                # Download image to temp file
                temp_path = download_image_temp(drive_service, photo_id)
                if not temp_path:
                    continue

                temp_files.append(temp_path)

                # Extract face encodings
                faces = extract_face_encodings(temp_path)

                if faces:
                    print(f"[Task {task_id}]     Found {len(faces)} faces")
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
                    print(f"[Task {task_id}]     No faces found")

                indexed_photos += 1

                # Update progress in events table
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

        update_task_status(task_id, 'completed', progress=indexed_photos, total=total_photos)
        print(f"[Task {task_id}] Completed. Photos: {indexed_photos}, Faces: {total_faces}")

    except HttpError as error:
        error_msg = f'Google Drive API error: {error}'
        print(f"[Task {task_id}] {error_msg}")
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db_conn.commit()
        update_task_status(task_id, 'failed', error=error_msg)

    except Exception as e:
        error_msg = f'Unexpected error: {str(e)}'
        print(f"[Task {task_id}] {error_msg}")
        db_conn.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db_conn.commit()
        update_task_status(task_id, 'failed', error=error_msg)

    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass

        # Close database connection
        db_conn.close()

@app.route('/start_indexing/<event_id>')
def start_indexing(event_id):
    """Start face indexing as a background task"""
    db = get_db()
    event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()

    if not event_data or 'credentials' not in session:
        return redirect(url_for('photographer_dashboard'))

    folder_id = event_data['drive_folder_id']
    if not folder_id:
        return redirect(url_for('photographer_dashboard'))

    # Create background task
    task_id = create_task(event_id, 'indexing')

    # Get credentials from session
    credentials_dict = session['credentials']

    # Submit task to background executor
    executor.submit(run_face_indexing_task, event_id, task_id, credentials_dict, folder_id)

    print(f"✓ Face indexing task created: {task_id} for event: {event_data['name']}")

    # Redirect to dashboard (task runs in background)
    return redirect(url_for('photographer_dashboard'))

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
    if 'selfie_images' not in request.files:
        return "No images uploaded.", 400
    
    files = request.files.getlist('selfie_images')
    if len(files) == 0 or files[0].filename == '':
        return "No selected files.", 400
    
    if len(files) > 3:
        return "Maximum 3 images allowed.", 400

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
                faces = extract_face_encodings(temp_file.name)
                if faces:
                    # Use first face found in each image
                    uploaded_encodings.append(faces[0]['encoding'])
                    print(f"Found face in uploaded image: {file.filename}")
        
        if not uploaded_encodings:
            return "No faces detected in uploaded photos. Please try again with clear face photos.", 400
        
        # Create average encoding from uploaded faces
        search_encoding = create_average_encoding(uploaded_encodings)
        print(f"Created average encoding from {len(uploaded_encodings)} face(s)")
        
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
                
                print(f"Match found: {photo_name} (distance: {distance:.3f})")
            
            faces_checked += 1
        
        print(f"Checked {faces_checked} faces, found {len(matching_photos)} matching photos")
        
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
        
    except Exception as e:
        print(f"Error in search_faces: {e}")
        return f"An error occurred while processing: {str(e)}", 500
        
    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass

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
    Get latest task for an event

    Returns:
        JSON: Task status information
    """
    task = get_event_latest_task(event_id)

    if task is None:
        return jsonify({'error': 'No task found for this event'}), 404

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
    })

if __name__ == '__main__':
    # Run Flask development server
    app.run(
        debug=Config.DEBUG,
        host=Config.HOST,
        port=Config.PORT
    )