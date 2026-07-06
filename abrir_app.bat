@echo off
setlocal
cd /d "%~dp0"

set PYTHON_EXE=
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Iniciando la app de préstamos...
start "" http://localhost:8501
"%PYTHON_EXE%" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true

endlocal
