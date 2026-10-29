#!/usr/bin/env bash
set -e

VENV_DIR="venv"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 non trovato."
    echo "Installa Python con:"
    echo "  brew install python"
    exit 1
fi

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Setup completato (macOS)"
