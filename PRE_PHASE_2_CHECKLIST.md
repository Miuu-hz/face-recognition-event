# Pre-Phase 2 Checklist

## ✅ สิ่งที่ควรทำก่อนเริ่ม Phase 2

### 1. ตรวจสอบ Environment Setup

```bash
# ตรวจสอบว่ามี .env file หรือยัง
ls -la .env

# ถ้ายังไม่มี ให้สร้างจาก template
cp .env.example .env

# สร้าง SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# Copy output และใส่ใน .env ที่บรรทัด SECRET_KEY=...
```

### 2. ตรวจสอบ Database

```bash
# ลบ database เก่า (ถ้ามี) เพื่อเริ่มใหม่
rm -f database.db

# สร้าง database ใหม่
flask --app app init-db
```

### 3. ตรวจสอบ Google OAuth Setup

```bash
# ตรวจสอบว่ามี client_secrets.json หรือยัง
ls -la client_secrets.json
```

**ถ้ายังไม่มี:**
1. ไปที่ [Google Cloud Console](https://console.cloud.google.com/)
2. สร้าง OAuth 2.0 Client ID
3. Download เป็น `client_secrets.json`
4. วางในโฟลเดอร์โปรเจค

### 4. ตรวจสอบ Logs Directory

```bash
# ตรวจสอบว่ามี logs directory หรือยัง
ls -la logs/

# ถ้ายังไม่มี จะถูกสร้างอัตโนมัติเมื่อรัน app
# แต่สามารถสร้างล่วงหน้าได้
mkdir -p logs
```

### 5. ทดสอบ Phase 1 Features

```bash
# รัน application
python app.py
```

**ทดสอบ:**
- [ ] App รันได้ไม่มี error
- [ ] เห็นข้อความ Face Recognition Configuration
- [ ] ตรวจสอบว่า GPU/CPU detection ทำงานถูกต้อง
- [ ] เข้า http://localhost:5000 ได้
- [ ] API endpoints ตอบกลับได้ (ทดสอบด้วย curl หรือ browser)

### 6. ตรวจสอบ Dependencies

```bash
# ตรวจสอบว่า dependencies ติดตั้งครบหรือยัง
pip list | grep -E "Flask|face-recognition|google|qrcode|dotenv"

# ถ้าขาดอะไร ให้ติดตั้งใหม่
pip install -r requirements.txt
```

### 7. ตรวจสอบ Static Directory

```bash
# สร้าง static directory สำหรับ QR codes
mkdir -p static
```

---

## ⚠️ ปัญหาที่อาจพบและวิธีแก้

### ปัญหา 1: ModuleNotFoundError: No module named 'dlib'

**สาเหตุ:** ไม่มี C++ compiler หรือ dlib ติดตั้งไม่สำเร็จ

**แก้ไข:**
```bash
# Ubuntu/Debian
sudo apt-get install build-essential cmake
pip install face-recognition

# macOS
xcode-select --install
brew install cmake
pip install face-recognition

# Windows
# ติดตั้ง Visual Studio with C++ Build Tools
# หรือใช้ pre-compiled version:
pip install dlib-binary
pip install face-recognition
```

### ปัญหา 2: SECRET_KEY not set

**แก้ไข:**
```bash
# แก้ไข .env
nano .env

# เพิ่มบรรทัด:
SECRET_KEY=your_generated_secret_key_here
```

### ปัญหา 3: Database schema mismatch

**แก้ไข:**
```bash
# ลบ database เก่าและสร้างใหม่
rm database.db
flask --app app init-db
```

### ปัญหา 4: Google OAuth not working

**ตรวจสอบ:**
1. มี `client_secrets.json` หรือไม่
2. Redirect URI ใน Google Cloud Console ตรงกับ URL ที่ใช้หรือไม่
   - สำหรับ local: `http://localhost:5000/callback_temp`
3. Enable Google Drive API ใน Google Cloud Console แล้วหรือยัง

---

## 📋 Quick Test Commands

```bash
# Test 1: ตรวจสอบ syntax
python -m py_compile app.py

# Test 2: ตรวจสอบ imports
python -c "import app; print('OK')"

# Test 3: ตรวจสอบ database connection
python -c "from app import app, get_db; app.app_context().push(); print(get_db())"

# Test 4: ตรวจสอบ environment variables
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(f'SECRET_KEY exists: {bool(os.getenv(\"SECRET_KEY\"))}')"
```

---

## 🎯 Phase 1 Feature Checklist

ตรวจสอบว่า Phase 1 features ทำงานครบ:

- [x] **Phase 1.1:** Background task processing
  - Task class สร้างได้
  - Threading ทำงานได้
  - Task store ทำงานได้

- [x] **Phase 1.2:** Progress tracking API
  - `/api/task/<task_id>` ตอบกลับได้
  - `/api/event/<event_id>/task` ตอบกลับได้

- [x] **Phase 1.3:** Environment configuration
  - `.env.example` มีครบ
  - `python-dotenv` ติดตั้งแล้ว
  - Config โหลดจาก environment ได้

- [x] **Phase 1.4:** GPU/CPU auto-detection
  - `detect_gpu()` ทำงานได้
  - แสดง config ตอน startup
  - เลือก model อัตโนมัติได้

- [x] **Phase 1.5:** Error handling & logging
  - `logs/app.log` ถูกสร้าง
  - `logs/error.log` ถูกสร้าง
  - Custom exceptions ทำงานได้
  - Retry logic ทำงานได้

- [x] **Phase 1.6:** Basic input validation
  - `validate_event_name()` ทำงานได้
  - `validate_folder_id()` ทำงานได้
  - `validate_event_id()` ทำงานได้
  - `validate_image_file()` ทำงานได้

---

## 🚀 Ready for Phase 2?

ถ้าทุกอย่างข้างบน pass แล้ว คุณพร้อมสำหรับ **Phase 2** แล้ว!

### Phase 2 จะทำอะไร?

**Phase 2A - Frontend Real-time Progress UI:**
- Progress bar with percentage
- Current photo display
- ETA calculation
- Real-time faces counter
- Auto-refresh on completion

**Phase 2B - Advanced Input Validation & UI Polish:**
- Toast notification system
- Inline form validation
- Button loading states
- Client-side validation
- Smooth animations

---

## 📝 Notes

1. **ไม่ต้องกังวลถ้ายังไม่มี GPU** - ระบบจะใช้ CPU mode โดยอัตโนมัติ
2. **Google OAuth จำเป็น** - ถ้ายังไม่มี `client_secrets.json` ต้องสร้างก่อน
3. **Database จะถูก init ใหม่** - ข้อมูลเก่าจะหายถ้า re-init
4. **Logs จะเพิ่มขึ้นเรื่อยๆ** - อาจต้อง clean up `logs/` บางครั้ง

---

**สรุป:** ตรวจสอบ checklist ข้างบนให้ครบ แล้วพร้อมไป Phase 2! 🚀
