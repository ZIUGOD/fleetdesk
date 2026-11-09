@echo off
rem End-user launcher: double-click to start FleetDesk. First run installs it into .venv.
cd /d "%~dp0.."

if not exist ".venv\Scripts\pythonw.exe" (
    echo Instalando o FleetDesk pela primeira vez, aguarde...
    python -m venv .venv || goto :no_python
    ".venv\Scripts\python.exe" -m pip install --quiet . || goto :install_failed
)

start "" ".venv\Scripts\pythonw.exe" -m fleetdesk
exit /b 0

:no_python
echo Python nao encontrado. Instale o Python 3.11 ou mais novo em https://www.python.org/downloads/
pause
exit /b 1

:install_failed
echo Falha ao instalar as dependencias. Verifique a conexao com a internet e tente novamente.
pause
exit /b 1
