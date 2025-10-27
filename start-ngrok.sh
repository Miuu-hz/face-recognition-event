#!/bin/bash

# Face Recognition Event - Startup with ngrok (Alternative to localtunnel)
# สคริปต์สำหรับรัน Flask server + ngrok

echo "======================================"
echo "Face Recognition Event - ngrok Setup"
echo "======================================"
echo ""

# สี ANSI codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ฟังก์ชัน cleanup
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    if [ ! -z "$FLASK_PID" ]; then
        echo "Stopping Flask server (PID: $FLASK_PID)..."
        kill $FLASK_PID 2>/dev/null
    fi
    if [ ! -z "$NGROK_PID" ]; then
        echo "Stopping ngrok (PID: $NGROK_PID)..."
        kill $NGROK_PID 2>/dev/null
    fi
    echo -e "${GREEN}Goodbye!${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ตรวจสอบ Virtual Environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}Warning: Virtual environment is not activated!${NC}"
    if [ -d "venv" ]; then
        source venv/bin/activate
        echo -e "${GREEN}Virtual environment activated.${NC}"
    else
        echo -e "${RED}Error: Virtual environment not found!${NC}"
        exit 1
    fi
fi

# ตรวจสอบ ngrok
if ! command -v ngrok &> /dev/null; then
    echo -e "${RED}Error: ngrok is not installed!${NC}"
    echo ""
    echo "Please install ngrok:"
    echo "  Mac:     brew install ngrok"
    echo "  Linux:   snap install ngrok"
    echo "  Windows: Download from https://ngrok.com/download"
    echo ""
    echo "Then sign up and run: ngrok config add-authtoken YOUR_TOKEN"
    exit 1
fi

PORT=10000

echo ""
echo "======================================"
echo "Starting services..."
echo "======================================"
echo ""

# รัน Flask
echo -e "${GREEN}[1/2] Starting Flask server on port $PORT...${NC}"
python app.py > flask.log 2>&1 &
FLASK_PID=$!

sleep 3

if ! ps -p $FLASK_PID > /dev/null; then
    echo -e "${RED}Error: Flask failed to start!${NC}"
    tail -20 flask.log
    exit 1
fi

echo -e "${GREEN}Flask server is running!${NC}"

# รัน ngrok
echo ""
echo -e "${GREEN}[2/2] Starting ngrok...${NC}"
ngrok http $PORT > /dev/null 2>&1 &
NGROK_PID=$!

sleep 2

# ดึง URL จาก ngrok API
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"https://[^"]*' | grep -o 'https://[^"]*' | head -1)

echo ""
echo "======================================"
echo -e "${GREEN}System is ready!${NC}"
echo "======================================"
echo ""
echo "Access your application at:"
echo ""
echo -e "${GREEN}Local:${NC}  http://localhost:$PORT"

if [ ! -z "$NGROK_URL" ]; then
    echo -e "${GREEN}Public:${NC} $NGROK_URL"
    echo ""
    echo -e "${YELLOW}Tip: ngrok URL is stable until you restart.${NC}"
else
    echo -e "${YELLOW}ngrok URL not found. Check http://localhost:4040 for details.${NC}"
fi

echo ""
echo "======================================"
echo ""
echo "Logs:"
echo "  Flask:  tail -f flask.log"
echo "  ngrok:  http://localhost:4040 (Web Interface)"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

wait $FLASK_PID $NGROK_PID
