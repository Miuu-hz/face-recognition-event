# System Requirements & Dependencies

## 📋 สารบัญ
- [Python Dependencies](#python-dependencies)
- [System Requirements](#system-requirements)
- [GPU Support & Limitations](#gpu-support--limitations)
- [Installation Guide](#installation-guide)
- [Troubleshooting](#troubleshooting)

---

## 🐍 Python Dependencies

### Required Libraries

```bash
# ดูรายการทั้งหมดใน requirements.txt
pip install -r requirements.txt
```

| Library | Version | Purpose | Size |
|---------|---------|---------|------|
| **Flask** | 2.3.2 | Web framework | ~5MB |
| **face-recognition** | 1.3.0 | Face recognition (ใช้ dlib ภายใน) | ~50MB |
| **dlib** | 19.24.x | ML library (auto-installed with face-recognition) | ~40MB |
| **numpy** | 1.24.3 | Array operations | ~20MB |
| **Pillow** | 10.0.0 | Image processing | ~10MB |
| **qrcode** | 7.4.2 | QR code generation | ~2MB |
| **google-auth** | 2.22.0 | Google OAuth | ~5MB |
| **google-api-python-client** | 2.95.0 | Google Drive API | ~10MB |
| **python-dotenv** | 1.0.0 | Environment variables | <1MB |
| **gunicorn** | 21.2.0 | Production server | ~2MB |

**Total Size:** ~150MB

---

## 💻 System Requirements

### ⚠️ สำคัญ: dlib ต้องการ C++ Compiler!

**dlib ต้อง compile จาก C++ source code** ดังนั้นต้องมี:

### สำหรับ Linux (Ubuntu/Debian):
```bash
# ติดตั้ง build tools ก่อน install Python packages
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    python3-dev
```

### สำหรับ macOS:
```bash
# ติดตั้ง Xcode Command Line Tools
xcode-select --install

# ติดตั้ง Homebrew packages
brew install cmake
```

### สำหรับ Windows:
```powershell
# ต้องติดตั้ง:
# 1. Visual Studio 2019+ with C++ Build Tools
# 2. CMake (https://cmake.org/download/)

# หรือใช้ pre-compiled wheel (แนะนำ):
pip install dlib-binary
```

---

## 🎮 GPU Support & Limitations

### ⚠️ ข้อจำกัดสำคัญ: รองรับเฉพาะ NVIDIA GPU!

| ยี่ห้อ GPU | รองรับหรือไม่ | เหตุผล |
|-----------|--------------|--------|
| **NVIDIA** | ✅ รองรับ | dlib รองรับ CUDA |
| **AMD** | ❌ ไม่รองรับ | dlib ไม่รองรับ ROCm |
| **Intel** | ❌ ไม่รองรับ | dlib ไม่รองรับ Intel GPU |
| **Apple Silicon (M1/M2/M3)** | ❌ ไม่รองรับ | dlib ไม่รองรับ Metal |

### การใช้งาน GPU (NVIDIA)

#### 1. ต้องติดตั้ง CUDA Toolkit

```bash
# ตรวจสอบว่ามี NVIDIA GPU
nvidia-smi

# ติดตั้ง CUDA Toolkit 11.x หรือ 12.x
# Download: https://developer.nvidia.com/cuda-downloads
```

#### 2. ต้อง compile dlib with CUDA

```bash
# Clone dlib source
git clone https://github.com/davisking/dlib.git
cd dlib

# Build with CUDA support
mkdir build
cd build
cmake .. -DDLIB_USE_CUDA=1 -DUSE_AVX_INSTRUCTIONS=1
cmake --build . --config Release
cd ..

# Install Python bindings
python setup.py install
```

#### 3. ตรวจสอบว่า CUDA ทำงาน

```python
import dlib
print(f"CUDA Available: {dlib.DLIB_USE_CUDA}")  # ต้องได้ True
```

### ถ้าไม่มี GPU (ใช้ CPU)

ระบบจะทำงานด้วย CPU โดยอัตโนมัติ:
- ใช้ HOG model (เร็วกว่า แต่แม่นยำน้อยกว่า)
- ไม่ต้องติดตั้ง CUDA
- ติดตั้ง dlib ปกติได้เลย: `pip install face-recognition`

---

## 📦 Installation Guide

### ขั้นตอนที่ 1: ติดตั้ง System Dependencies

<details>
<summary><b>Ubuntu/Debian</b></summary>

```bash
# อัพเดท package list
sudo apt-get update

# ติดตั้ง build tools และ libraries
sudo apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    python3-dev \
    python3-pip \
    python3-venv

# (Optional) ถ้ามี NVIDIA GPU
# ติดตั้ง CUDA Toolkit จาก https://developer.nvidia.com/cuda-downloads
```
</details>

<details>
<summary><b>macOS</b></summary>

```bash
# ติดตั้ง Xcode Command Line Tools
xcode-select --install

# ติดตั้ง Homebrew (ถ้ายังไม่มี)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ติดตั้ง dependencies
brew install cmake python@3.11
```
</details>

<details>
<summary><b>Windows</b></summary>

```powershell
# 1. ติดตั้ง Python 3.11+ จาก https://www.python.org/downloads/

# 2. ติดตั้ง Visual Studio 2019+ with C++ Build Tools
# Download: https://visualstudio.microsoft.com/downloads/

# 3. ติดตั้ง CMake
# Download: https://cmake.org/download/

# 4. (แนะนำ) ใช้ pre-compiled dlib
pip install dlib-binary

# (Optional) ถ้ามี NVIDIA GPU
# ติดตั้ง CUDA Toolkit จาก https://developer.nvidia.com/cuda-downloads
```
</details>

### ขั้นตอนที่ 2: สร้าง Virtual Environment

```bash
# สร้าง virtual environment
python3 -m venv venv

# Activate venv
source venv/bin/activate  # Linux/macOS
# หรือ
venv\Scripts\activate     # Windows
```

### ขั้นตอนที่ 3: ติดตั้ง Python Dependencies

```bash
# ติดตั้งจาก requirements.txt
pip install --upgrade pip
pip install -r requirements.txt
```

### ขั้นตอนที่ 4: ตั้งค่า Environment Variables

```bash
# คัดลอก template
cp .env.example .env

# สร้าง SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# แก้ไขไฟล์ .env
nano .env
```

### ขั้นตอนที่ 5: ตั้งค่า Google OAuth

```bash
# 1. ไปที่ Google Cloud Console
# 2. สร้าง OAuth 2.0 Client ID
# 3. Download client_secrets.json
# 4. วางไฟล์ในโฟลเดอร์โปรเจค
```

### ขั้นตอนที่ 6: Initialize Database

```bash
flask --app app init-db
```

### ขั้นตอนที่ 7: รันแอพ

```bash
python app.py
```

---

## 🔧 Troubleshooting

### ❌ ปัญหา: dlib ติดตั้งไม่สำเร็จ

**สาเหตุ:** ไม่มี C++ compiler หรือ CMake

**แก้ไข:**
```bash
# Linux
sudo apt-get install build-essential cmake

# macOS
xcode-select --install
brew install cmake

# Windows
# ติดตั้ง Visual Studio with C++ Build Tools
# หรือใช้ pre-compiled version:
pip install dlib-binary
```

### ❌ ปัญหา: GPU ไม่ทำงาน (ใช้ CPU แทน)

**ตรวจสอบ:**
```python
import dlib
print(f"CUDA Available: {dlib.DLIB_USE_CUDA}")
```

**ถ้าได้ False:**
1. ตรวจสอบว่าติดตั้ง CUDA Toolkit แล้ว: `nvidia-smi`
2. Compile dlib ใหม่พร้อม CUDA flag
3. ดู [การใช้งาน GPU](#การใช้งาน-gpu-nvidia) ด้านบน

### ❌ ปัญหา: ImportError หรือ ModuleNotFoundError

**แก้ไข:**
```bash
# ตรวจสอบว่า activate venv แล้ว
source venv/bin/activate

# ติดตั้งใหม่
pip install -r requirements.txt --force-reinstall
```

### ❌ ปัญหา: Memory Error ระหว่าง Face Recognition

**แก้ไข:**
```bash
# แก้ไข .env
BATCH_SIZE=10        # ลดจาก 20 เป็น 10
FACE_MODEL=hog       # เปลี่ยนจาก cnn เป็น hog (ใช้ RAM น้อยกว่า)
```

---

## 📊 Minimum vs Recommended Specs

### CPU-Only (HOG Model)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 2 cores @ 2.0 GHz | 4+ cores @ 3.0 GHz |
| **RAM** | 4 GB | 8 GB+ |
| **Storage** | 2 GB | 5 GB+ |
| **Python** | 3.8+ | 3.11+ |

### GPU-Accelerated (CNN Model - NVIDIA Only)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 cores @ 2.5 GHz | 6+ cores @ 3.5 GHz |
| **RAM** | 8 GB | 16 GB+ |
| **GPU** | NVIDIA GTX 1050 (2GB VRAM) | NVIDIA RTX 3060+ (6GB+ VRAM) |
| **CUDA** | 11.x | 12.x |
| **Storage** | 5 GB | 10 GB+ |
| **Python** | 3.8+ | 3.11+ |

---

## 🚀 Performance Comparison

### Processing Speed (100 photos with faces)

| Configuration | Time | Accuracy |
|--------------|------|----------|
| **CPU (HOG)** | ~5-10 minutes | Good (90-95%) |
| **GPU (CNN)** | ~1-2 minutes | Excellent (95-99%) |

### ข้อจำกัดที่ควรรู้

1. **NVIDIA GPU Only** - ไม่รองรับ AMD, Intel, Apple Silicon
2. **CUDA Required** - ต้องติดตั้ง CUDA Toolkit สำหรับ GPU
3. **C++ Compiler Required** - dlib ต้อง compile จาก source
4. **Memory Intensive** - CNN model ใช้ RAM/VRAM มาก
5. **Linux/macOS Recommended** - Windows ต้องติดตั้ง Visual Studio

---

## 📚 Additional Resources

- [dlib Documentation](http://dlib.net/)
- [face_recognition Documentation](https://face-recognition.readthedocs.io/)
- [CUDA Installation Guide](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/)
- [Google Drive API Guide](https://developers.google.com/drive/api/guides/about-sdk)

---

## ⚠️ สรุปข้อจำกัดหลัก

```
┌─────────────────────────────────────────────┐
│  ข้อจำกัดที่ต้องทราบก่อนใช้งาน              │
├─────────────────────────────────────────────┤
│ 1. ต้องมี C++ Compiler (dlib)              │
│ 2. GPU รองรับแค่ NVIDIA (CUDA)              │
│ 3. ไม่รองรับ AMD / Intel / Apple GPU       │
│ 4. ต้องติดตั้ง CUDA สำหรับ GPU mode        │
│ 5. Windows ต้องใช้ Visual Studio           │
└─────────────────────────────────────────────┘
```

**คำแนะนำ:** ถ้าไม่มี NVIDIA GPU ให้ใช้ CPU mode (HOG) ก็เพียงพอสำหรับงานทั่วไป
