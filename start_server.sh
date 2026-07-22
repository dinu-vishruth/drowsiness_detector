#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d venv ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

PORT="${PORT:-80}"

if [ "$(id -u)" -eq 0 ]; then
  echo "Starting app on port $PORT..."
  exec env PORT="$PORT" python app.py
else
  echo "Starting app on port $PORT with sudo..."
  exec sudo env PATH="$PATH" PORT="$PORT" "$PWD/venv/bin/python" "$PWD/app.py"
fi
