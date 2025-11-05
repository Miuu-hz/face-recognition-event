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
from PIL import Image


from flask import Flask, redirect, request, session, url_for, render_template, jsonify, g
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_change_this'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

DATABASE = 'database.db'

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
    Returns: dict ของ config
    """
    has_gpu = detect_gpu_availability()

    # ตัวเลือกการตั้งค่า
    config = {
        'tolerance': 0.5,  # ค่า 0.4-0.6 เหมาะสม (ยิ่งน้อยยิ่งเข้มงวด)
        'batch_size': 20,  # จำนวนรูปต่อ batch

        # Auto-detect model based on GPU availability
        'model': 'cnn' if has_gpu else 'hog',

        # Manual override (ถ้าต้องการบังคับใช้ model ใดๆ uncomment บรรทัดด้านล่าง)
        # 'model': 'hog',  # บังคับใช้ CPU (เร็ว, RAM น้อย)
        # 'model': 'cnn',  # บังคับใช้ CNN (แม่นยำกว่า, ต้องการ GPU หรือ CPU แรงๆ)

        # GPU specific settings
        'use_gpu': has_gpu,
        'num_jitters': 1 if has_gpu else 1,  # จำนวนครั้งที่ sample รูปเพื่อเพิ่มความแม่นยำ
    }

    # แสดงข้อมูล config
    print("\n" + "="*50)
    print("Face Recognition Configuration:")
    print("="*50)
    print(f"Device:       {'GPU (CUDA)' if config['use_gpu'] else 'CPU'}")
    print(f"Model:        {config['model'].upper()} ({'CNN - High Accuracy' if config['model'] == 'cnn' else 'HOG - Fast Processing'})")
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

@app.route('/start_indexing/<event_id>')
def start_indexing(event_id):
    db = get_db()
    event_data = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()

    if not event_data or 'credentials' not in session:
        return redirect(url_for('photographer_dashboard'))

    # Update status to In Progress
    db.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('In Progress', event_id))
    db.commit()
    
    folder_id = event_data['drive_folder_id']
    creds = Credentials(**session['credentials'])
    drive_service = build('drive', 'v3', credentials=creds)
    
    print(f"--- Starting Face Indexing for Event: {event_data['name']} ---")
    
    indexed_photos = 0
    total_faces = 0
    temp_files = []  # Track temp files for cleanup
    
    try:
        # Get all images from the folder
        query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/jpg') and trashed=false"
        results = drive_service.files().list(
            q=query, 
            fields="files(id, name)",
            pageSize=100  # Adjust as needed
        ).execute()
        photos = results.get('files', [])
        
        print(f"Found {len(photos)} photos to process")
        
        # Process photos in batches
        batch_size = FACE_RECOGNITION_CONFIG['batch_size']
        for i in range(0, len(photos), batch_size):
            batch = photos[i:i+batch_size]
            print(f"Processing batch {i//batch_size + 1} ({len(batch)} photos)...")
            
            for photo in batch:
                photo_id = photo['id']
                photo_name = photo['name']
                print(f"  Processing: {photo_name}")
                
                # Download image to temp file
                temp_path = download_image_temp(drive_service, photo_id)
                if not temp_path:
                    continue
                    
                temp_files.append(temp_path)
                
                # Extract face encodings
                faces = extract_face_encodings(temp_path)
                
                if faces:
                    print(f"    Found {len(faces)} faces")
                    for face_data in faces:
                        # Convert encoding to blob for storage
                        encoding_blob = face_data['encoding'].tobytes()
                        location_json = json.dumps(face_data['location'])
                        
                        # Save to database
                        db.execute(
                            'INSERT INTO faces (event_id, photo_id, photo_name, face_encoding, face_location) VALUES (?, ?, ?, ?, ?)',
                            (event_id, photo_id, photo_name, encoding_blob, location_json)
                        )
                        total_faces += 1
                else:
                    print(f"    No faces found")
                
                indexed_photos += 1
                
                # Update progress (optional - for real-time updates)
                db.execute(
                    "UPDATE events SET indexed_photos = ?, total_faces = ? WHERE id = ?",
                    (indexed_photos, total_faces, event_id)
                )
                db.commit()
                
        # Update final status
        db.execute(
            "UPDATE events SET indexing_status = ?, indexed_photos = ?, total_faces = ? WHERE id = ?",
            ('Completed', indexed_photos, total_faces, event_id)
        )
        db.commit()
        print(f"--- Indexing completed. Photos: {indexed_photos}, Faces: {total_faces} ---")
        
    except HttpError as error:
        print(f'An error occurred: {error}')
        db.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db.commit()
        
    except Exception as e:
        print(f'Unexpected error: {e}')
        db.execute("UPDATE events SET indexing_status = ? WHERE id = ?", ('Failed', event_id))
        db.commit()
        
    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)