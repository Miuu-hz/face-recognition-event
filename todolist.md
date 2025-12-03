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
📋 Planned (Phase 3 - MEDIUM PRIORITY)
 🐘 PostgreSQL Support
   - Replace SQLite with PostgreSQL for better concurrency
   - Connection pooling
   - Migration script from SQLite to PostgreSQL
   - Environment-based database selection
 ⚡ Performance Optimization
   - Cache face encodings to avoid recomputation
   - Redis/Memcached integration for encoding cache
   - Implement lazy loading for event images
   - Optimize database queries with indexes
 🔄 Resume Interrupted Indexing
   - Save progress checkpoints during indexing
   - Resume from last checkpoint on failure/interruption
   - Skip already processed photos
   - Progress persistence in database
 📸 Batch Upload Improvements
   - Drag & drop multiple files
   - Image preview before upload
   - Client-side image validation
   - Progress indicator for each file
   - Concurrent upload support

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
