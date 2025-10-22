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

### 2. Setup Database

```bash
flask --app app init-db
```

### 3. ตั้งค่า Google OAuth

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

แก้ไขค่าใน `app.py`:

```python
FACE_RECOGNITION_CONFIG = {
    'tolerance': 0.5,    # 0.4-0.6 (ยิ่งน้อยยิ่งเข้มงวด)
    'model': 'hog',      # 'hog' = เร็ว, 'cnn' = แม่นยำ
    'batch_size': 20,    # จำนวนรูปต่อ batch
}
```

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
- ⚠️ RAM usage สูงเมื่อ index รูปจำนวนมาก

## Roadmap

- [ ] เพิ่ม caching สำหรับ face encodings
- [ ] ใช้ vector database (Milvus/Faiss)
- [ ] Batch processing แบบ async
- [ ] Support multiple events พร้อมกัน

## License

MIT License

## ติดต่อ

หากมีปัญหาหรือข้อสงสัย กรุณาเปิด Issue ใน repository

---

**Version:** 1.0.0 (Local Development with Localtunnel)
**Last Updated:** 2025-10-22
