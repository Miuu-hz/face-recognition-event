# คู่มือการติดตั้งและรันระบบ Face Recognition แบบ Local + Localtunnel

## สารบัญ
1. [ข้อกำหนดเบื้องต้น](#ข้อกำหนดเบื้องต้น)
2. [การติดตั้ง](#การติดตั้ง)
3. [การตั้งค่า Google OAuth](#การตั้งค่า-google-oauth)
4. [การรันระบบ](#การรันระบบ)
5. [การแก้ปัญหา](#การแก้ปัญหา)

---

## ข้อกำหนดเบื้องต้น

### 1. Python 3.9 หรือสูงกว่า
```bash
python --version
# ควรได้ Python 3.9.x หรือสูงกว่า
```

### 2. Node.js และ npm (สำหรับ localtunnel)
```bash
node --version
npm --version
```

### 3. ติดตั้ง build tools (สำหรับ face_recognition)

#### บน Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake
sudo apt-get install -y libopenblas-dev liblapack-dev
sudo apt-get install -y libjpeg-dev libpng-dev
```

#### บน macOS:
```bash
brew install cmake
```

#### บน Windows:
- ติดตั้ง Visual Studio Build Tools
- หรือใช้ WSL2 (แนะนำ)

---

## การติดตั้ง

### ขั้นตอนที่ 1: Clone โปรเจค (ถ้ายังไม่ได้ทำ)
```bash
git clone <your-repo-url>
cd face-recognition-event
```

### ขั้นตอนที่ 2: สร้าง Virtual Environment
```bash
# สร้าง virtual environment
python -m venv venv

# เปิดใช้งาน virtual environment
# บน Linux/macOS:
source venv/bin/activate

# บน Windows:
venv\Scripts\activate
```

### ขั้นตอนที่ 3: ติดตั้ง Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements-local.txt
```

**หมายเหตุ:** การติดตั้ง `face_recognition` อาจใช้เวลา 5-10 นาที เนื่องจากต้อง compile dlib

### ขั้นตอนที่ 4: ติดตั้ง Localtunnel
```bash
npm install -g localtunnel
```

### ขั้นตอนที่ 5: เตรียม Database
```bash
# สร้างไฟล์ schema.sql ถ้ายังไม่มี (ดูตัวอย่างด้านล่าง)
# จากนั้นรัน:
flask --app app init-db
```

**ตัวอย่างไฟล์ schema.sql:**
```sql
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS faces;

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    link TEXT,
    qr_path TEXT,
    drive_folder_id TEXT,
    indexing_status TEXT DEFAULT 'Not Started',
    indexed_photos INTEGER DEFAULT 0,
    total_faces INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,
    photo_name TEXT,
    face_encoding BLOB NOT NULL,
    face_location TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
);

CREATE INDEX idx_event_faces ON faces(event_id);
CREATE INDEX idx_photo_id ON faces(photo_id);
```

---

## การตั้งค่า Google OAuth

### ขั้นตอนที่ 1: สร้าง Google Cloud Project
1. ไปที่ https://console.cloud.google.com/
2. สร้าง Project ใหม่หรือเลือก Project ที่มีอยู่
3. เปิดใช้งาน **Google Drive API**

### ขั้นตอนที่ 2: สร้าง OAuth 2.0 Credentials
1. ไปที่ "APIs & Services" > "Credentials"
2. คลิก "Create Credentials" > "OAuth client ID"
3. เลือก Application type: **Web application**
4. ตั้งค่า Authorized redirect URIs:
   ```
   http://localhost:10000/callback_temp
   ```
5. Download ไฟล์ JSON และบันทึกเป็น `client_secrets.json` ในโฟลเดอร์โปรเจค

### ขั้นตอนที่ 3: ตรวจสอบไฟล์ client_secrets.json
ไฟล์ควรมีโครงสร้างประมาณนี้:
```json
{
  "web": {
    "client_id": "your-client-id.apps.googleusercontent.com",
    "client_secret": "your-client-secret",
    "redirect_uris": ["http://localhost:10000/callback_temp"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token"
  }
}
```

---

## การรันระบบ

### วิธีที่ 1: ใช้ Script อัตโนมัติ (แนะนำ)

```bash
# ทำให้ script รันได้ (ครั้งแรกเท่านั้น)
chmod +x start.sh

# รันระบบ
./start.sh
```

Script จะ:
1. เช็คว่า virtual environment เปิดอยู่หรือไม่
2. รัน Flask server ที่ port 10000
3. รัน localtunnel และสร้าง public URL อัตโนมัติ
4. แสดง URL ที่ใช้เข้าถึงระบบ

### วิธีที่ 2: รัน Manual

#### Terminal 1 - รัน Flask Server:
```bash
source venv/bin/activate  # เปิด virtual environment
python app.py
```

#### Terminal 2 - รัน Localtunnel:
```bash
lt --port 10000 --subdomain your-custom-name
# หรือไม่ระบุ subdomain ให้ random
lt --port 10000
```

**หมายเหตุ:**
- ถ้าไม่ระบุ `--subdomain` จะได้ URL แบบ random เช่น `https://random-name-123.loca.lt`
- ถ้าระบุ subdomain จะได้ URL แบบ `https://your-custom-name.loca.lt` (แต่อาจถูกใช้งานแล้ว)

---

## การใช้งาน

### 1. เปิดระบบ
หลังจากรัน `./start.sh` จะได้ URL 2 แบบ:
- **Local:** http://localhost:10000
- **Public (Localtunnel):** https://your-url.loca.lt

### 2. เข้าสู่ระบบ Google
1. เปิด URL ที่ได้ในเบราว์เซอร์
2. คลิก "Login" หรือไปที่ `/login_temp`
3. เลือก Google Account และอนุญาตให้เข้าถึง Google Drive

### 3. สร้าง Event
1. กรอกชื่อ Event
2. เลือก Google Drive Folder ที่เก็บรูปภาพ
3. กด "Start Indexing" เพื่อเริ่มสแกนใบหน้า

### 4. แชร์ QR Code
- ระบบจะสร้าง QR Code อัตโนมัติ
- นำ QR Code ไปติดที่งาน เพื่อให้คนถ่ายเซลฟี่ค้นหารูป

---

## การหยุดระบบ

```bash
# กด Ctrl+C ใน terminal ที่รัน start.sh
# หรือถ้ารัน manual ให้กด Ctrl+C ทั้งสอง terminal
```

---

## การแก้ปัญหา

### ปัญหา: face_recognition ติดตั้งไม่สำเร็จ
**วิธีแก้:**
```bash
# ติดตั้ง dlib แยกก่อน
pip install cmake
pip install dlib
pip install face_recognition
```

### ปัญหา: Localtunnel ขึ้น "connection refused"
**วิธีแก้:**
- ตรวจสอบว่า Flask server รันอยู่ที่ port 10000
- ลองรัน `curl http://localhost:10000` ดูว่าตอบกลับไหม

### ปัญหา: Localtunnel URL เปลี่ยนทุกครั้ง
**วิธีแก้:**
- ใช้ `--subdomain` เพื่อกำหนดชื่อ (แต่อาจถูกใช้แล้ว)
- หรือใช้บริการอื่นเช่น ngrok, serveo

### ปัญหา: Google OAuth redirect URI mismatch
**วิธีแก้:**
1. ไปที่ Google Cloud Console
2. เพิ่ม Localtunnel URL ใน Authorized redirect URIs:
   ```
   https://your-url.loca.lt/callback_temp
   ```
3. **สำคัญ:** ต้องเพิ่ม URL ใหม่ทุกครั้งที่ Localtunnel เปลี่ยน URL

### ปัญหา: RAM ใช้งานเยอะเกินไป
**วิธีแก้:**
1. ลด `batch_size` ใน `FACE_RECOGNITION_CONFIG` ใน app.py
2. ใช้ `model: 'hog'` แทน `'cnn'` (ตั้งค่าไว้แล้ว)
3. ปิดโปรแกรมอื่นๆ ที่ไม่จำเป็น

### ปัญหา: Database locked
**วิธีแก้:**
```bash
# ลบ database แล้วสร้างใหม่
rm database.db
flask --app app init-db
```

---

## ข้อจำกัดของ Localtunnel

1. **URL เปลี่ยน:** ถ้าไม่ใช้ subdomain, URL จะเปลี่ยนทุกครั้งที่รัน
2. **Warning Page:** บางครั้งจะมีหน้า warning ของ localtunnel (กด Continue)
3. **ความเร็ว:** อาจช้ากว่า deploy จริง
4. **ไม่ stable:** ไม่แนะนำสำหรับ production

---

## ทางเลือกอื่นนอกจาก Localtunnel

### 1. ngrok (แนะนำสำหรับ MVP)
```bash
# ติดตั้ง
brew install ngrok  # macOS
# หรือดาวน์โหลดจาก https://ngrok.com/download

# รัน
ngrok http 10000
```

**ข้อดี:**
- URL ไม่เปลี่ยน (ถ้าใช้ account)
- เสถียรกว่า localtunnel
- มี dashboard ดู traffic

**ข้อเสีย:**
- Free tier จำกัด 1 concurrent tunnel

### 2. serveo
```bash
ssh -R 80:localhost:10000 serveo.net
```

**ข้อดี:**
- ไม่ต้องติดตั้งอะไร (ใช้ SSH)

**ข้อเสีย:**
- บางครั้ง service ล่ม

---

## เทคนิคการใช้งานสำหรับ MVP

### 1. ทดสอบก่อนใช้งานจริง
```bash
# สร้าง test event ด้วยรูป 2-3 รูป
# เทสต์การค้นหาใบหน้า
# ดูว่า RAM ใช้งานเท่าไหร่
```

### 2. เตรียม Google Drive ให้พร้อม
- จัดรูปเป็นโฟลเดอร์ชัดเจน
- ตั้งชื่อไฟล์ให้เป็นระเบียบ
- อัพโหลดไฟล์เป็น .jpg หรือ .png เท่านั้น

### 3. แนะนำผู้ใช้
- บอกให้ถ่ายเซลฟี่หน้าชัดๆ
- แนะนำให้อัพโหลด 2-3 รูป (มุมต่างกัน)
- บอกว่าระบบอาจใช้เวลาประมวลผล

---

## การอัพเดทระบบ

```bash
# Pull code ใหม่
git pull origin main

# อัพเดท dependencies
pip install -r requirements-local.txt --upgrade

# Restart ระบบ
./start.sh
```

---

## ติดต่อ/ช่วยเหลือ

หากมีปัญหาหรือคำถาม:
- ตรวจสอบ logs ใน terminal
- ดู error messages ในเบราว์เซอร์
- เช็ค console.log ในเบราว์เซอร์ (F12)

---

**สร้างโดย:** Face Recognition Event System
**Version:** 1.0 (Local Development with Localtunnel)
**Updated:** 2025-10-22
