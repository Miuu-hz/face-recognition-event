#!/usr/bin/env bash
# exit on error
set -o errexit

# Install system dependencies for face_recognition
apt-get update
apt-get install -y python3-dev build-essential
apt-get install -y cmake
apt-get install -y libopenblas-dev liblapack-dev
apt-get install -y libjpeg-dev libpng-dev

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt