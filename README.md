# Face Recognition Event System

ระบบค้นหารูปภาพจากงานอีเวนต์ด้วยเทคโนโลยี Face Recognition

## Quick Start

### 1. ติดตั้ง Dependencies

```bash
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
```

### 2. ตั้งค่า Environment Variables

```bash
# สร้างไฟล์ .env จาก template
cp .env.example .env

# สร้าง SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# Copy output และใส่ใน .env

# แก้ไข .env ตามต้องการ
nano .env
```

### 3. Setup Database

```bash
flask --app app init-db
```

### 4. ตั้งค่า Google OAuth

1. ไปที่ [Google Cloud Console](https://console.cloud.google.com/)
2. สร้าง OAuth 2.0 credentials
3. Download เป็น `client_secrets.json` วางในโฟลเดอร์โปรเจค

### 4. รันระบบ

```bash
# ทำให้ script รันได้ (ครั้งแรกเท่านั้น)
chmod +x start.sh

# รันระบบ
./start.sh
```

## คุณสมบัติหลัก

- ✅ สร้าง Event และ QR Code อัตโนมัติ
- ✅ เชื่อมต่อ Google Drive สำหรับเก็บรูปภาพ
- ✅ Face Recognition & Indexing อัตโนมัติ
- ✅ ค้นหารูปด้วยการอัพโหลดเซลฟี่
- ✅ รองรับการอัพโหลดหลายรูปเพื่อความแม่นยำ
- ⚡ **Auto-detect GPU/CPU** - ใช้ GPU อัตโนมัติถ้ามี (เร็วกว่า 3-10 เท่า)
- 🔄 **Background Task Processing** - Indexing ทำงาน background ไม่บล็อก UI
- 📊 **Real-time Progress Tracking** - ติดตามความคืบหน้าผ่าน API

## โครงสร้างโปรเจค

```
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
```

## เทคโนโลยีที่ใช้

- **Backend:** Flask (Python)
- **Face Recognition:** face_recognition library (dlib)
- **Database:** SQLite
- **Cloud Storage:** Google Drive API
- **Tunneling:** Localtunnel (สำหรับ MVP)

## คู่มือการใช้งาน

### สำหรับช่างภาพ (Photographer)

1. เข้าสู่ระบบด้วย Google Account
2. สร้าง Event ใหม่
3. เลือก Google Drive Folder ที่เก็บรูป
4. กด "Start Indexing" รอระบบสแกนใบหน้า
5. นำ QR Code ไปติดที่งาน

### สำหรับผู้เข้าร่วมงาน (Attendee)

1. สแกน QR Code ที่งาน
2. อัพโหลดเซลฟี่ 1-3 รูป (ยิ่งหลายรูปยิ่งแม่นยำ)
3. กด "Search" รอระบบค้นหา
4. ดาวน์โหลดรูปที่ตรงกับใบหน้า

## Configuration

### ⚡ GPU/CPU Auto-Detection

ระบบจะตรวจสอบและใช้ GPU อัตโนมัติ! เมื่อรัน server จะเห็นข้อความแบบนี้:

```
==================================================
Face Recognition Configuration:
==================================================
Device:       GPU (CUDA)
Model:        CNN (CNN - High Accuracy)
Tolerance:    0.5 (lower = stricter)
Batch Size:   20 images
Num Jitters:  1
==================================================
```

### การตั้งค่า Manual

แก้ไขใน `app.py` บรรทัด 67-81:

```python
config = {
    'tolerance': 0.5,    # 0.4-0.6 (ยิ่งน้อยยิ่งเข้มงวด)
    'batch_size': 20,    # จำนวนรูปต่อ batch

    # Auto-detect (default)
    'model': 'cnn' if has_gpu else 'hog',

    # หรือบังคับเลือก:
    # 'model': 'hog',  # บังคับใช้ CPU (เร็ว, RAM น้อย)
    # 'model': 'cnn',  # บังคับใช้ CNN (แม่นยำ, ต้องการ GPU)
}
```

### เปรียบเทียบ CPU vs GPU

| | CPU (HOG) | GPU (CNN) |
|---|---|---|
| **ความเร็ว** | เร็ว | เร็วมาก (3-10x) |
| **ความแม่นยำ** | ดี | ดีเยี่ยม |
| **RAM** | น้อย (~2GB) | ปานกลาง (~4GB) |
| **ต้องการ GPU** | ❌ | ✅ |

## API Endpoints

### Background Task Status

#### ดู status ของ task
```bash
GET /api/task/<task_id>
```

Response:
```json
{
  "id": "task-uuid",
  "status": "running",
  "progress": 15,
  "total": 100,
  "progress_percent": 15,
  "current_item": "photo_name.jpg",
  "error": null
}
```

#### ดู task ล่าสุดของ event
```bash
GET /api/event/<event_id>/task
```

Response เหมือนกับข้างบน

**Task Status Values:**
- `pending`: รอเริ่มทำงาน
- `running`: กำลังทำงาน
- `completed`: เสร็จสมบูรณ์
- `failed`: ล้มเหลว (ดู error field)

## การแก้ปัญหา

### RAM ใช้งานเยอะเกินไป
- ลด `batch_size` ใน config
- ใช้ `model: 'hog'` แทน `'cnn'`
- ปิดโปรแกรมอื่นๆ

### Face Recognition ไม่แม่นยำ
- ลด `tolerance` (เช่น 0.4)
- ให้ผู้ใช้อัพโหลดรูปหน้าชัดๆ หลายรูป
- ใช้ `model: 'cnn'` (ต้องการ GPU)

### Localtunnel URL เปลี่ยนทุกครั้ง
- แก้ไข `SUBDOMAIN` ใน `start.sh`
- หรือใช้ ngrok แทน

## คู่มือเพิ่มเติม

📖 **คู่มือติดตั้งแบบละเอียด:** [SETUP_LOCAL.md](SETUP_LOCAL.md)

## ข้อจำกัดปัจจุบัน

- ⚠️ ใช้ Localtunnel (ไม่เสถียรเท่า production)
- ⚠️ SQLite (ไม่เหมาะสำหรับ concurrent users เยอะ)

## Roadmap

- [x] Background task processing ✅
- [x] Progress tracking API ✅
- [x] Environment configuration ✅
- [x] GPU/CPU auto-detection ✅
- [ ] Frontend real-time progress UI
- [ ] Error handling & logging system
- [ ] Input validation & security
- [ ] PostgreSQL support
- [ ] เพิ่ม caching สำหรับ face encodings
- [ ] ใช้ vector database (Milvus/Faiss)
- [ ] Support multiple events พร้อมกัน

## License

MIT License

## ติดต่อ

หากมีปัญหาหรือข้อสงสัย กรุณาเปิด Issue ใน repository

---

**Version:** 1.0.0 (Local Development with Localtunnel)
**Last Updated:** 2025-10-22
