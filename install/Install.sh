#!/usr/bin/env bash

set -e  # interrompe lo script al primo errore

# Parametri
MIN_PYTHON_VERSION="3.10"
VENV_DIR="venv"

echo "Verifica presenza di Python 3..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Errore: python3 non è installato."
    echo "Installa una versione recente di Python 3 e riprova."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')

if [[ "$(printf '%s\n' "$MIN_PYTHON_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$MIN_PYTHON_VERSION" ]]; then
    echo "Errore: Python $MIN_PYTHON_VERSION o superiore è richiesto (trovato $PYTHON_VERSION)."
    exit 1
fi

echo "Python $PYTHON_VERSION rilevato."

echo "Creazione virtual environment in ./$VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo "Attivazione virtual environment..."
source "$VENV_DIR/bin/activate"

echo "Aggiornamento pip..."
python -m pip install --upgrade pip

echo "Installazione dipendenze..."
python -m pip install psutil
python -m pip install pyzmq
python -m pip install jsonschema

echo "Installazione completata con successo."
echo "Per attivare l'ambiente in futuro:"
echo "source $VENV_DIR/bin/activate"
