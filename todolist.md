Face Recognition Event System
ระบบค้นหารูปภาพจากงานอีเวนต์ด้วยเทคโนโลยี Face Recognition

Quick Start
1. ติดตั้ง Dependencies
# สร้าง virtual environment
python -m venv venv

# เปิดใช้งาน
source venv/bin/activate  # Linux/macOS
# หรือ
venv\Scripts\activate  # Windows

# ติดตั้ง packages
pip install -r requirements-local.txt

# ติดตั้ง localtunnel
npm install -g localtunnel
2. ตั้งค่า Environment Variables
# สร้างไฟล์ .env จาก template
cp .env.example .env

# สร้าง SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# Copy output และใส่ใน .env

# แก้ไข .env ตามต้องการ
nano .env
3. Setup Database
flask --app app init-db
4. ตั้งค่า Google OAuth
ไปที่ Google Cloud Console
สร้าง OAuth 2.0 credentials
Download เป็น client_secrets.json วางในโฟลเดอร์โปรเจค
4. รันระบบ
# ทำให้ script รันได้ (ครั้งแรกเท่านั้น)
chmod +x start.sh

# รันระบบ
./start.sh
คุณสมบัติหลัก
🎯 Core Features
✅ สร้าง Event และ QR Code อัตโนมัติ
✅ เชื่อมต่อ Google Drive สำหรับเก็บรูปภาพ
✅ Face Recognition & Indexing อัตโนมัติ
✅ ค้นหารูปด้วยการอัพโหลดเซลฟี่
✅ รองรับการอัพโหลดหลายรูปเพื่อความแม่นยำ
⚡ Performance & Reliability
⚡ Auto-detect GPU/CPU - ใช้ GPU อัตโนมัติถ้ามี (เร็วกว่า 3-10 เท่า)
🔄 Background Task Processing - Indexing ทำงาน background ไม่บล็อก UI
📊 Real-time Progress Tracking - ติดตามความคืบหน้าผ่าน API
🔁 Auto-retry Failed Operations - Retry อัตโนมัติสำหรับ network errors
🛡️ Robust Error Handling - ทำงานต่อได้แม้บางรูปมีปัญหา
🔧 Development & Operations
📝 Structured Logging - บันทึก log แบบมีโครงสร้างใน logs/
✅ Input Validation - ตรวจสอบข้อมูลก่อนประมวลผล
⚙️ Environment-based Config - ตั้งค่าผ่าน .env file
🔍 Detailed Error Messages - แสดง error ละเอียดเพื่อ debug ง่าย
📊 Real-time Monitoring (Phase 2A)
📈 Progress Bar - แสดง progress แบบ real-time พร้อม animation
🔄 Auto-polling - อัพเดตข้อมูลทุก 2 วินาทีอัตโนมัติ
⏱️ ETA Calculation - คำนวณเวลาที่เหลือจากความเร็วเฉลี่ย
📸 Current Photo Display - แสดงชื่อรูปที่กำลังประมวลผล
👤 Faces Counter - นับจำนวนใบหน้าที่เจอแบบ real-time
🔁 Auto-refresh - Reload หน้าอัตโนมัติเมื่อเสร็จหรือล้มเหลว
🛡️ Advanced Security (Phase 2B)
📏 File Size Limits - จำกัดขนาดไฟล์สูงสุด 10MB
✍️ Event Name Validation - ตรวจสอบชื่อ 3-100 ตัวอักษร
🔐 Google Drive Permissions - ตรวจสอบสิทธิ์ก่อน link folder
🧹 Input Sanitization - ลบอักขระที่ไม่พึงประสงค์
⚠️ User-friendly Errors - แสดง error แบบเข้าใจง่าย
โครงสร้างโปรเจค
face-recognition-event/
├── app.py                    # Flask application หลัก
├── schema.sql                # Database schema
├── start.sh                  # Startup script
├── requirements-local.txt    # Python dependencies
├── SETUP_LOCAL.md           # คู่มือติดตั้งแบบละเอียด
├── static/                   # QR codes และไฟล์ static
├── templates/                # HTML templates
│   ├── photographer_dashboard.html
│   ├── event_page.html
│   └── results_page.html
└── database.db              # SQLite database (auto-created)
เทคโนโลยีที่ใช้
Backend: Flask (Python)
Face Recognition: face_recognition library (dlib)
Database: SQLite
Cloud Storage: Google Drive API
Tunneling: Localtunnel (สำหรับ MVP)
คู่มือการใช้งาน
สำหรับช่างภาพ (Photographer)
เข้าสู่ระบบด้วย Google Account
สร้าง Event ใหม่
เลือก Google Drive Folder ที่เก็บรูป
กด "Start Indexing" รอระบบสแกนใบหน้า
นำ QR Code ไปติดที่งาน
สำหรับผู้เข้าร่วมงาน (Attendee)
สแกน QR Code ที่งาน
อัพโหลดเซลฟี่ 1-3 รูป (ยิ่งหลายรูปยิ่งแม่นยำ)
กด "Search" รอระบบค้นหา
ดาวน์โหลดรูปที่ตรงกับใบหน้า
Configuration
⚡ GPU/CPU Auto-Detection
ระบบจะตรวจสอบและใช้ GPU อัตโนมัติ! เมื่อรัน server จะเห็นข้อความแบบนี้:

==================================================
Face Recognition Configuration:
==================================================
Device:       GPU (CUDA)
Model:        CNN (CNN - High Accuracy)
Tolerance:    0.5 (lower = stricter)
Batch Size:   20 images
Num Jitters:  1
==================================================
การตั้งค่า Manual
แก้ไขใน app.py บรรทัด 67-81:

config = {
    'tolerance': 0.5,    # 0.4-0.6 (ยิ่งน้อยยิ่งเข้มงวด)
    'batch_size': 20,    # จำนวนรูปต่อ batch

    # Auto-detect (default)
    'model': 'cnn' if has_gpu else 'hog',

    # หรือบังคับเลือก:
    # 'model': 'hog',  # บังคับใช้ CPU (เร็ว, RAM น้อย)
    # 'model': 'cnn',  # บังคับใช้ CNN (แม่นยำ, ต้องการ GPU)
}
เปรียบเทียบ CPU vs GPU
CPU (HOG)	GPU (CNN)
ความเร็ว	เร็ว	เร็วมาก (3-10x)
ความแม่นยำ	ดี	ดีเยี่ยม
RAM	น้อย (~2GB)	ปานกลาง (~4GB)
ต้องการ GPU	❌	✅
API Endpoints
Background Task Status
ดู status ของ task
GET /api/task/<task_id>
Response:

{
  "id": "task-uuid",
  "status": "running",
  "progress": 15,
  "total": 100,
  "progress_percent": 15,
  "current_item": "photo_name.jpg",
  "error": null
}
ดู task ล่าสุดของ event
GET /api/event/<event_id>/task
Response เหมือนกับข้างบน

Task Status Values:

pending: รอเริ่มทำงาน
running: กำลังทำงาน
completed: เสร็จสมบูรณ์
failed: ล้มเหลว (ดู error field)
Error Handling & Logging
📋 Structured Logging
ระบบบันทึก log แบบมีโครงสร้าง:

logs/
├── app.log      # All logs (DEBUG level)
└── error.log    # Errors only (ERROR level)
Log Format:

[2025-11-05 10:30:15] INFO [app:660] - Starting Face Indexing for Event: abc-123
Log Levels:

DEBUG: Development mode - รายละเอียดทุกอย่าง
INFO: Production mode - ข้อมูลสำคัญ
WARNING: คำเตือน - อาจมีปัญหา
ERROR: ข้อผิดพลาด - ต้องแก้ไข
🔄 Error Recovery
Retry Logic:

Download failures: Retry 3 times with exponential backoff (1s, 2s, 4s)
Continue processing if individual photos fail
Clean up temp files even on errors
Custom Exceptions:

ImageProcessingError: รูปภาพเสียหรือประมวลผลไม่ได้
GoogleDriveError: Google Drive API ล้มเหลว
ValidationError: ข้อมูล input ไม่ถูกต้อง
DatabaseError: Database operation ล้มเหลว
Input Validation:

Event ID: ต้องเป็น UUID format
Folder ID: ต้องมีความยาว 10-100 ตัวอักษร
Image files: รองรับเฉพาะ jpg, jpeg, png, gif
📊 Monitoring Logs
# ดู log แบบ real-time
tail -f logs/app.log

# ดู errors อย่างเดียว
tail -f logs/error.log

# ค้นหา errors
grep ERROR logs/app.log

# ดู task specific logs
grep "task.abc-123" logs/app.log
การแก้ปัญหา
RAM ใช้งานเยอะเกินไป
ลด batch_size ใน config
ใช้ model: 'hog' แทน 'cnn'
ปิดโปรแกรมอื่นๆ
Face Recognition ไม่แม่นยำ
ลด tolerance (เช่น 0.4)
ให้ผู้ใช้อัพโหลดรูปหน้าชัดๆ หลายรูป
ใช้ model: 'cnn' (ต้องการ GPU)
Localtunnel URL เปลี่ยนทุกครั้ง
แก้ไข SUBDOMAIN ใน start.sh
หรือใช้ ngrok แทน
ตรวจสอบ Errors
ดู logs/error.log สำหรับ errors ล่าสุด
ตรวจสอบ stack trace สำหรับรายละเอียด
ดู task status ผ่าน API /api/task/<task_id>
ตรวจสอบ Google Drive permissions
คู่มือเพิ่มเติม
📖 คู่มือติดตั้งแบบละเอียด: SETUP_LOCAL.md

ข้อจำกัดปัจจุบัน
⚠️ ใช้ Localtunnel (ไม่เสถียรเท่า production)
⚠️ SQLite (ไม่เหมาะสำหรับ concurrent users เยอะ)

Roadmap
 Completed (Phase 1 - CRITICAL)
 Background task processing 
 Progress tracking API
 Environment configuration 
 GPU/CPU auto-detection 
 Error handling & logging system 
 Basic input validation 
Completed (Phase 2 - HIGH PRIORITY)
 Frontend real-time progress UI 
Progress bar with percentage
Current photo display
Estimated time remaining (ETA)
Real-time faces count
Auto-refresh on completion/failure
 Advanced input validation 
Event name validation (3-100 chars)
File size limits (10MB max)
Google Drive folder permissions check
Input sanitization
 UI Polish 
Toast notification system (success/error/info)
Inline form validation errors
Button loading states
Client-side validation
Smooth animations
✅ Completed (Landing Page & Theme Update)
 Modern Landing Page
Public landing page with futuristic design
Hero section with gradient effects
Feature showcase (99.9% accuracy, instant search, privacy)
Browse Events button for public users
Photographer Login button
 Public Event Selection
/events route for browsing completed events
Shows event metadata (photos, faces, date)
Dark theme with glassmorphism effects
Click-to-view event details
 Futuristic Theme (Blue/Purple)
Complete redesign of all pages to futuristic aesthetic
Dark background (#020617) with blue/purple gradients
Glassmorphism effects with backdrop-filter
Background blur animations
Consistent navbar with PHOPY logo
Updated pages:
  - Landing page (index.html)
  - Event selection (events.html)
  - Event upload page (event_page.html)
  - Results page (results_page.html)
  - Photographer dashboard (photographer_dashboard.html)
  - Folder selection (select_folder.html)
 Authentication Improvements
Logout functionality (/logout route)
Sign-out button in photographer dashboard navbar
Responsive design (icon-only on mobile)
Dedicated photographer login page
Feature highlights before OAuth
Professional onboarding experience
 Custom Error Pages
404 Page Not Found with consistent branding
500 Internal Server Error with helpful actions
Error handlers in Flask app
User-friendly error messages
Responsive error page designs
📋 Phase 3 - MEDIUM PRIORITY
✅ 🔄 Resume Interrupted Indexing (COMPLETED)
   - ✅ Save progress checkpoints during indexing
   - ✅ Resume from last checkpoint on failure/interruption
   - ✅ Skip already processed photos
   - ✅ Progress persistence in database
   - ✅ UI indicator showing resumable progress
   - ✅ Automatic checkpoint cleanup on completion
   Implementation:
   * New table: indexing_checkpoints (event_id, photo_id, photo_name, faces_found, processed_at)
   * Helper functions: get_checkpoints(), save_checkpoint(), clear_checkpoints(), count_checkpoints()
   * Modified run_indexing_background() to check/save/skip checkpoints
   * API endpoint: /api/event/<event_id>/checkpoint/status
   * Dashboard shows "Resume Face Indexing" with checkpoint count when interrupted
   * Migration script: migrate_checkpoints.py

✅ 🐘 PostgreSQL Support (COMPLETED)
   - ✅ Optional PostgreSQL support (environment-based selection)
   - ✅ Connection pooling with ThreadedConnectionPool (min=1, max=20)
   - ✅ DatabaseWrapper class for unified interface
   - ✅ Automatic parameter substitution (? → %s)
   - ✅ Migration script from SQLite to PostgreSQL
   Implementation:
   * Added DATABASE_TYPE environment variable (sqlite/postgresql)
   * Created DatabaseWrapper class to abstract SQLite vs PostgreSQL differences
   * Added init_postgres_pool() for connection pooling
   * Modified get_db() to support both database types
   * Created get_db_connection() for background threads
   * PostgreSQL schema: schema_postgresql.sql
   * Migration script: migrate_sqlite_to_postgres.py
   * Requirements: requirements-postgresql.txt (psycopg2-binary)
   Setup:
   * Set DATABASE_TYPE=postgresql in .env
   * Configure POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
   * Install: pip install -r requirements-postgresql.txt
   * Initialize DB: psql -U postgres -d face_recognition -f schema_postgresql.sql
   * Migrate data: python migrate_sqlite_to_postgres.py

✅ ⚡ Performance Optimization (COMPLETED)
   - ✅ Vectorized face comparison (10-50x faster than loop)
   - ✅ In-memory encoding cache (avoid repeated DB queries)
   - ✅ Thread-safe cache with automatic invalidation
   - ✅ Composite database index (event_id + indexed_at)
   Implementation:
   * Modified search_faces() to use numpy vectorized distance calculation
   * Added get_cached_encodings() function with threading.Lock
   * Added invalidate_cache() called on indexing start/complete
   * Cache structure: {event_id: {'encodings': np.array, 'photo_ids': list, 'photo_names': list}}
   * Added idx_faces_event_indexed composite index in schema.sql
   * Migration script: migrate_performance_indexes.py
   Performance gains:
   * Search speed: 10-50x faster with vectorized comparison
   * Repeated searches: Near-instant with in-memory cache
   * Database queries: Faster with composite index

✅ 📸 Batch Upload Improvements (COMPLETED)
   - ✅ Drag & drop zone with visual feedback
   - ✅ Image preview grid before upload
   - ✅ Client-side validation (file type, size, count)
   - ✅ Individual file removal from preview
   - ✅ Real-time validation messages
   Implementation:
   * Drag & drop zone with hover effects
   * Preview grid showing thumbnails with file names
   * Validation: max 3 files, 10MB each, JPG/PNG only
   * Remove button (×) on each preview
   * Smart submit button (disabled when no files)
   * DataTransfer API for file management
   * Success/error validation messages
   UX Improvements:
   * Visual feedback on drag over
   * Preview images before submission
   * Clear error messages for invalid files
   * Easy file removal with one click
   * Disabled submit button prevents empty submissions

💡 Future (Phase 4 - NICE TO HAVE)
 🗄️ Vector Database Integration
   - Integrate Milvus or Faiss for faster similarity search
   - Migrate face encodings to vector database
   - Improve search performance for large datasets
 ⚙️ Multiple Events Support
   - Support concurrent indexing for multiple events
   - Queue system for background tasks
   - Resource allocation and throttling
 🔍 Advanced Face Clustering
   - Group similar faces automatically
   - Detect duplicate faces across photos
   - Face grouping UI for photographers
 📊 Photo Quality Detection
   - Detect blurry or low-quality photos
   - Auto-skip poor quality images during indexing
   - Quality score for each photo
 📈 Analytics Dashboard (Future Enhancement)
   - Statistics and insights for photographers
   - Search analytics (popular events, search patterns)
   - Performance metrics (indexing speed, search time)
   - Usage graphs and charts
 🔔 Notification System (Future Enhancement)
   - Email notifications for indexing completion
   - LINE/Telegram bot integration
   - Push notifications for photographers
   - SMS alerts for critical events
 🎨 Photo Gallery View (Future Enhancement)
   - Grid view with lightbox
   - Download all photos as ZIP
   - Share photos via social media
   - Photo slideshow mode
 🔐 API Authentication (Future Enhancement)
   - JWT token-based API authentication
   - API rate limiting
   - API key management for third-party integrations
   - OAuth2 for external apps
 🌐 Multi-language Support (Future Enhancement)
   - Internationalization (i18n) framework
   - Thai and English language support
   - Language switcher in UI
   - Localized error messages
 📱 Mobile App (Future Enhancement)
   - Progressive Web App (PWA)
   - Native mobile app (React Native)
   - Mobile-optimized UI
   - Offline support for event pages
License


Final System Flow
┌─────────────────────────────────────────────────────────────────┐
│                     SETUP PHASE (ครั้งแรก)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Operator]                        [Phopy OA]                   │
│      │                                  │                       │
│      ├── แอดเพื่อน @Phopy ──────────────>│                       │
│      ├── พิมพ์ "ลงทะเบียน" ─────────────>│                       │
│      │<─────── "✅ สำเร็จ! พิมพ์ 'เพิ่มกลุ่ม'" ─┤                │
│      ├── พิมพ์ "เพิ่มกลุ่ม" ─────────────>│                       │
│      │<─────── Invite Link ─────────────┤                       │
│      │                                  │                       │
│      ├── เอา Link ไปเชิญ Bot เข้า Group ─┼──> [LINE Group]       │
│      │                                  │         │             │
│      ├── พิมพ์ "Phopy เชื่อมต่อ" ใน Group ──────>│             │
│      │<─────────────── "✅ เชื่อมต่อแล้ว!" ──────┤             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     EVENT PHASE (ทุกครั้งที่จัดงาน)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [LINE Group]                                                   │
│      │                                                          │
│  Operator: "Phopy เริ่มงาน ประชุมABC"                            │
│      │                                                          │
│      ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 📸 เริ่มงาน "ประชุมABC"                                  │    │
│  │ 🔑 รหัส: ABC123                                         │    │
│  │                                                         │    │
│  │ แอด @Phopy แล้วกรอกรหัสเพื่อรับรูป                       │    │
│  │ ⚠️ ข้อมูลใบหน้าจะถูกลบใน 7 วัน                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     USER REGISTRATION (ผู้เข้าร่วม)              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [User]                            [Phopy OA]                   │
│      │                                  │                       │
│      ├── แอดเพื่อน @Phopy ──────────────>│                       │
│      │<── "ส่ง selfie มาลงทะเบียน" ──────┤                       │
│      ├── ส่ง selfie ────────────────────>│                       │
│      │<── "✅ บันทึกใบหน้าแล้ว           │                       │
│      │     กรอกรหัสงานเพื่อรับรูป" ───────┤                       │
│      ├── พิมพ์ "ABC123" ────────────────>│                       │
│      │<── "✅ เข้าร่วมงาน ประชุมABC แล้ว  │                       │
│      │     รอรับแจ้งเตือนเมื่อมีรูปของคุณ" ┤                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     REALTIME INDEX + NOTIFY                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [LINE Group]        [Celery Worker]        [Phopy OA]          │
│      │                     │                     │              │
│  ช่างภาพส่งรูป ───────────>│                     │              │
│      │              Queue รูป                    │              │
│      │                     │                     │              │
│      │              ┌──────▼──────┐              │              │
│      │              │ 1.ดึงรูปจากLINE │              │              │
│      │              │ 2.Extract faces│              │              │
│      │              │ 3.บันทึก encoding│             │              │
│      │              │ 4.Match กับ     │              │              │
│      │              │   participants │              │              │
│      │              └──────┬──────┘              │              │
│      │                     │                     │              │
│      │              [ถ้า match]                  │              │
│      │                     ├────────────────────>│              │
│      │                     │         Push: "📸 พบคุณในงาน       │
│      │                     │          ประชุมABC รอสรุปภายหลัง"   │
│      │                     │                     │──> [User]    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     AUTO CLOSE (1 ชม. หลังรูปสุดท้าย)            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Celery Beat]              [LINE Group]        [Users]         │
│      │                           │                 │            │
│  เช็คทุก 5 นาที                  │                 │            │
│  "last_photo > 1 ชม.?"           │                 │            │
│      │                           │                 │            │
│      ├── Yes ────────────────────>│                 │            │
│      │         "✅ งาน ประชุมABC สรุปแล้ว           │            │
│      │          📊 247 รูป / 89 คน                 │            │
│      │          แอด @Phopy กรอก ABC123"            │            │
│      │                           │                 │            │
│      ├───────────────────────────┼────────────────>│            │
│      │                           │    Push แต่ละคน:│            │
│      │                           │    "พบรูปของคุณ 12 รูป       │
│      │                           │     [ดูรูปทั้งหมด]"          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     VIEW PHOTOS (เว็บ)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [User]              [LIFF/Web]              [Backend]          │
│      │                   │                       │              │
│      ├── กดปุ่ม ─────────>│                       │              │
│      │            เปิด liff.line.me/xxx          │              │
│      │                   ├── GET /photos ────────>│              │
│      │                   │<── photo list ─────────┤              │
│      │                   │                       │              │
│      │<── แสดงรูป ────────┤    (ดึงจาก LINE API   │              │
│      │    พร้อม Banner    │     by message_id)   │              │
│      │                   │                       │              │
│      ├── กดดาวน์โหลด ────>│                       │              │
│      │<── รูป + Banner ───┤                       │              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Development Phases
Phase 1: Foundation (1-2 สัปดาห์)
เป้าหมาย: Bot ทำงานได้ basic ใน Group + OA
TaskรายละเอียดEst.☐ สมัคร LINE OA + Messaging APIดูหัวข้อ Checklist ด้านล่าง1 วัน☐ Setup project structureFlask + LINE SDK + SQLite0.5 วัน☐ Database schemaสร้างตาราง ตาม design0.5 วัน☐ Webhook endpointรับ event จาก LINE1 วัน☐ OA Handler: ลงทะเบียน Operatorพิมพ์ "ลงทะเบียน" → บันทึก1 วัน☐ OA Handler: เพิ่มกลุ่มสร้าง invite token1 วัน☐ Group Handler: Join EventBot เข้า Group → welcome0.5 วัน☐ Group Handler: เชื่อมต่อLink Group กับ Operator1 วัน☐ Group Handler: เริ่มงานสร้าง Event + รหัส1 วัน☐ ทดสอบ Flow พื้นฐานManual test ใน Group จริง1 วัน
Deliverable: Bot เข้า Group ได้ สร้างงานได้ มีรหัสงาน

Phase 2: Face Processing (1-2 สัปดาห์)
เป้าหมาย: Index รูป + Match หน้าได้
TaskรายละเอียดEst.☐ Setup Celery + RedisDocker compose หรือ local1 วัน☐ Image Handlerรับรูปจาก Group → queue1 วัน☐ Worker: Download imageดึงรูปจาก LINE API0.5 วัน☐ Worker: Extract facesface_recognition library1 วัน☐ Worker: Save encodingsบันทึกลง DB0.5 วัน☐ OA Handler: ลงทะเบียนหน้าUser ส่ง selfie → บันทึก1 วัน☐ OA Handler: กรอกรหัสงานJoin event as participant1 วัน☐ Worker: Match facesเทียบ encoding + push2 วัน☐ Concurrency limitจำกัด worker ไม่ให้ overload0.5 วัน☐ ทดสอบ Face matchingทดสอบกับรูปจริง1 วัน
Deliverable: ส่งรูป → index → match → push แจ้งเตือนได้

Phase 3: Auto Close + Summary (1 สัปดาห์)
เป้าหมาย: ระบบปิดงานอัตโนมัติ + สรุปผล
TaskรายละเอียดEst.☐ Celery Beat setupScheduled task ทุก 5 นาที0.5 วัน☐ Auto close logicเช็ค last_photo > 1 ชม.1 วัน☐ Summary message (Group)แจ้งสรุปใน Group0.5 วัน☐ Summary message (User)Push หาแต่ละคน + จำนวนรูป1 วัน☐ Flex Message templateปุ่มกด "ดูรูปทั้งหมด"1 วัน☐ ทดสอบ Auto closeจำลอง scenario1 วัน
Deliverable: งานปิดอัตโนมัติ + ทุกคนได้รับสรุป

Phase 4: Web Viewer (1-2 สัปดาห์)
เป้าหมาย: เว็บดูรูป + ดาวน์โหลด
TaskรายละเอียดEst.☐ สร้าง LIFF Appลงทะเบียนใน LINE Console0.5 วัน☐ API: Get user photos/api/events/{code}/photos1 วัน☐ API: Get image contentProxy จาก LINE API1 วัน☐ Web: Photo galleryแสดงรูปทั้งหมดของ user2 วัน☐ Web: Download รูปดาวน์โหลดทีละรูป1 วัน☐ Event Banner overlayใส่ Banner ตอนดาวน์โหลด2 วัน☐ ทดสอบ End-to-endFlow เต็มจาก Group ถึง Download1 วัน
Deliverable: กดปุ่ม → เห็นรูป → ดาวน์โหลดพร้อม Banner

Phase 5: Production Ready (1 สัปดาห์)
เป้าหมาย: พร้อม deploy ใช้งานจริง
TaskรายละเอียดEst.☐ Error handlingทุก endpoint มี try-catch1 วัน☐ Loggingบันทึก event สำคัญ0.5 วัน☐ Rate limitingป้องกัน spam0.5 วัน☐ Auto delete (7 วัน)Cleanup job1 วัน☐ Docker composeBackend + Redis + Worker1 วัน☐ Deploy to cloudRailway / Render / VPS1 วัน☐ SSL + DomainHTTPS สำหรับ webhook0.5 วัน
Deliverable: ระบบพร้อมใช้งานจริง

Checklist: สิ่งที่ต้องเตรียม/สมัคร
ทำทันที (ก่อน code)
☐รายการวิธีทำ☐LINE Developers Accounthttps://developers.line.biz → Login ด้วย LINE☐Create Providerตั้งชื่อ เช่น "Phopy"☐Create Messaging API Channelเลือก Provider → Create Channel☐ตั้งค่า Channel- Channel name: Phopy- Channel description: ผู้ช่วยหารูป Event- Category: ธุรกิจ☐เปิด Bot settings- Allow bot to join group chats: ✅- Auto-reply messages: ❌ (ปิด)- Greeting messages: ❌ (ปิด)☐เก็บ credentials- Channel ID- Channel Secret- Channel Access Token (Issue ใหม่)☐Webhook URLตั้งค่าทีหลังตอน dev (ใช้ ngrok)
ทำตอนเริ่ม Phase 1
☐รายการวิธีทำ☐Python environmentPython 3.9+, venv☐LINE Bot SDKpip install line-bot-sdk☐ngrok accounthttps://ngrok.com → สมัครฟรี☐Redis (local)Docker: docker run -d -p 6379:6379 redis
ทำตอนเริ่ม Phase 4
☐รายการวิธีทำ☐Create LIFF AppLINE Console → LIFF → Add☐LIFF Settings- Size: Full- Endpoint URL: (เว็บของเรา)- Scope: profile
ทำตอน Phase 5
☐รายการวิธีทำ☐Cloud hostingRailway / Render / DigitalOcean☐Domain name(ถ้าต้องการ) เช่น phopy.app☐SSL Certificateมากับ hosting หรือ Cloudflare