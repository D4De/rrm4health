$VenvDir = "venv"
$MinPythonVersion = [Version]"3.10"

$python = Get-Command python -ErrorAction SilentlyContinue

if (-not $python) {
    Write-Error "Python non trovato. Installa Python 3.8+ da https://python.org"
    exit 1
}

$version = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([Version]$version -lt $MinPythonVersion) {
    Write-Error "Python 3.10 o superiore richiesto (trovato $version)"
    exit 1
}

python -m venv $VenvDir
& "$VenvDir\Scripts\Activate.ps1"

python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "Setup completato (Windows)"
