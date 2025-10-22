# ============================================
# DISABLED - ไฟล์นี้ถูก disable ไว้ชั่วคราว
# ============================================
# ใช้สำหรับ deploy บน Render หรือ Cloud Platform
# ปัจจุบันใช้ localtunnel สำหรับ MVP แทน
# ดูคู่มือการใช้งานใน SETUP_LOCAL.md
# ============================================

# FROM python:3.9

# RUN apt-get update && apt-get install -y \
#     build-essential \
#     cmake \
#     libopenblas-dev \
#     liblapack-dev \
#     libjpeg-dev \
#     libpng-dev

# WORKDIR /app

# COPY requirements.txt .
# RUN pip install --upgrade pip
# RUN pip install -r requirements.txt

# COPY . .

# CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:10000", "app:app"]