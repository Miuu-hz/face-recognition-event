#!/bin/bash

# Face Recognition Event - Local Development Startup Script
# สคริปต์สำหรับรัน Flask server + Localtunnel อัตโนมัติ

echo "======================================"
echo "Face Recognition Event - Local Setup"
echo "======================================"
echo ""

# สี ANSI codes สำหรับ output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ฟังก์ชันสำหรับ cleanup เมื่อกด Ctrl+C
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"

    # ฆ่า process ทั้งหมดในกลุ่ม
    if [ ! -z "$FLASK_PID" ]; then
        echo "Stopping Flask server (PID: $FLASK_PID)..."
        kill $FLASK_PID 2>/dev/null
    fi

    if [ ! -z "$LT_PID" ]; then
        echo "Stopping Localtunnel (PID: $LT_PID)..."
        kill $LT_PID 2>/dev/null
    fi

    echo -e "${GREEN}Goodbye!${NC}"
    exit 0
}

# ตั้งค่า trap สำหรับจับสัญญาณ SIGINT (Ctrl+C) และ SIGTERM
trap cleanup SIGINT SIGTERM

# ตรวจสอบ Virtual Environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}Warning: Virtual environment is not activated!${NC}"
    echo "Attempting to activate..."

    if [ -d "venv" ]; then
        source venv/bin/activate
        echo -e "${GREEN}Virtual environment activated.${NC}"
    else
        echo -e "${RED}Error: Virtual environment not found!${NC}"
        echo "Please create it first:"
        echo "  python -m venv venv"
        echo "  source venv/bin/activate"
        echo "  pip install -r requirements-local.txt"
        exit 1
    fi
fi

echo ""
echo "Checking dependencies..."

# ตรวจสอบว่า Python packages ติดตั้งแล้วหรือยัง
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${RED}Error: Flask is not installed!${NC}"
    echo "Please run: pip install -r requirements-local.txt"
    exit 1
fi

# ตรวจสอบว่า localtunnel ติดตั้งแล้วหรือยัง
if ! command -v lt &> /dev/null; then
    echo -e "${YELLOW}Warning: Localtunnel (lt) is not installed!${NC}"
    echo "Installing localtunnel..."
    npm install -g localtunnel

    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to install localtunnel!${NC}"
        echo "Please install manually: npm install -g localtunnel"
        exit 1
    fi
fi

# ตรวจสอบไฟล์ที่จำเป็น
echo ""
echo "Checking required files..."

if [ ! -f "client_secrets.json" ]; then
    echo -e "${YELLOW}Warning: client_secrets.json not found!${NC}"
    echo "Please download OAuth credentials from Google Cloud Console"
    echo "See SETUP_LOCAL.md for instructions"
fi

if [ ! -f "schema.sql" ]; then
    echo -e "${YELLOW}Warning: schema.sql not found!${NC}"
    echo "Database initialization may fail"
fi

if [ ! -f "database.db" ]; then
    echo -e "${YELLOW}Warning: database.db not found!${NC}"
    echo "Attempting to initialize database..."
    flask --app app init-db

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Database initialized successfully.${NC}"
    else
        echo -e "${RED}Failed to initialize database. Please check schema.sql${NC}"
    fi
fi

# กำหนด PORT
PORT=10000

# ตัวเลือกสำหรับ Localtunnel subdomain (comment ออกถ้าต้องการ random)
# SUBDOMAIN="my-face-recognition"
SUBDOMAIN=""

echo ""
echo "======================================"
echo "Starting services..."
echo "======================================"
echo ""

# รัน Flask server ใน background
echo -e "${GREEN}[1/2] Starting Flask server on port $PORT...${NC}"
python app.py > flask.log 2>&1 &
FLASK_PID=$!

# รอให้ Flask server พร้อม
echo "Waiting for Flask to start..."
sleep 3

# ตรวจสอบว่า Flask รันสำเร็จหรือไม่
if ! ps -p $FLASK_PID > /dev/null; then
    echo -e "${RED}Error: Flask failed to start!${NC}"
    echo "Check flask.log for details:"
    tail -20 flask.log
    exit 1
fi

# ทดสอบว่า Flask ตอบกลับหรือไม่
if curl -s http://localhost:$PORT > /dev/null; then
    echo -e "${GREEN}Flask server is running!${NC}"
else
    echo -e "${RED}Error: Flask server is not responding!${NC}"
    kill $FLASK_PID
    exit 1
fi

echo ""
echo -e "${GREEN}[2/2] Starting Localtunnel...${NC}"

# รัน Localtunnel
if [ -z "$SUBDOMAIN" ]; then
    lt --port $PORT > lt.log 2>&1 &
else
    lt --port $PORT --subdomain $SUBDOMAIN > lt.log 2>&1 &
fi

LT_PID=$!

# รอให้ localtunnel สร้าง URL
echo "Waiting for Localtunnel URL..."
sleep 3

# อ่าน URL จาก log
LT_URL=$(grep -oP 'https://[^\s]+' lt.log | head -1)

echo ""
echo "======================================"
echo -e "${GREEN}System is ready!${NC}"
echo "======================================"
echo ""
echo "Access your application at:"
echo ""
echo -e "${GREEN}Local:${NC}  http://localhost:$PORT"

if [ ! -z "$LT_URL" ]; then
    echo -e "${GREEN}Public:${NC} $LT_URL"
    echo ""
    echo -e "${YELLOW}Note: Localtunnel may show a warning page on first visit.${NC}"
    echo -e "${YELLOW}      Click 'Continue' to access your app.${NC}"
else
    echo -e "${YELLOW}Localtunnel URL not found. Check lt.log for details.${NC}"
fi

echo ""
echo "======================================"
echo ""
echo "Logs:"
echo "  Flask:       tail -f flask.log"
echo "  Localtunnel: tail -f lt.log"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# รอจนกว่าจะถูกยกเลิก
wait $FLASK_PID $LT_PID
