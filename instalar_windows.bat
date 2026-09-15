@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Instalador - Telegram Downloader

REM ==========================================================================
REM  Instalador do Telegram Downloader para Windows
REM
REM  Cria o ambiente, instala as bibliotecas, gera o icone e coloca um
REM  atalho na area de trabalho e no menu iniciar.
REM
REM  Uso: duplo clique neste arquivo (com telegram_downloader.py ao lado)
REM ==========================================================================

set "NOME=Telegram Downloader"
set "BASE=%LOCALAPPDATA%\TelegramDownloader"
set "VENV=%BASE%\venv"
set "ORIGEM=%~dp0telegram_downloader.py"

echo.
echo ===========================================
echo   Instalando %NOME%
echo ===========================================
echo.

REM --- 1. conferir o script --------------------------------------------------
if not exist "%ORIGEM%" (
    echo ERRO: telegram_downloader.py nao encontrado nesta pasta.
    echo Coloque os dois arquivos juntos e rode de novo.
    echo.
    pause
    exit /b 1
)

REM --- 2. localizar o Python -------------------------------------------------
echo [1/5] Procurando Python...

set "PY="
for %%C in (py python) do (
    if not defined PY (
        %%C -c "import sys,tkinter; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PY=%%C"
    )
)

if not defined PY (
    echo.
    echo Python nao encontrado, ou instalado sem o modulo tkinter.
    echo.
    echo Baixe em: https://www.python.org/downloads/windows
    echo.
    echo IMPORTANTE ao instalar:
    echo   - marque "Add python.exe to PATH"
    echo   - em Optional Features, mantenha "tcl/tk and IDLE" marcado
    echo.
    echo Depois rode este instalador de novo.
    echo.
    start "" "https://www.python.org/downloads/windows/"
    pause
    exit /b 1
)
echo       encontrado: %PY%

REM --- 3. ambiente virtual ---------------------------------------------------
echo [2/5] Preparando ambiente virtual...
if not exist "%BASE%" mkdir "%BASE%"
if not exist "%VENV%\Scripts\python.exe" (
    %PY% -m venv "%VENV%"
    if !errorlevel! neq 0 (
        echo ERRO ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo [3/5] Instalando bibliotecas...
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install --quiet telethon pillow pycryptodome
if !errorlevel! neq 0 (
    echo    aviso: tentando sem o acelerador opcional...
    "%VENV%\Scripts\python.exe" -m pip install --quiet telethon pillow
)

REM --- 4. copiar o script e gerar o icone -----------------------------------
copy /Y "%ORIGEM%" "%BASE%\telegram_downloader.py" >nul

echo [4/5] Gerando icone...
if exist "%~dp0gerar_icone.py" (
    copy /Y "%~dp0gerar_icone.py" "%BASE%\gerar_icone.py" >nul
    "%VENV%\Scripts\python.exe" "%BASE%\gerar_icone.py" ico "%BASE%\icone.ico"
) else (
    echo    gerar_icone.py nao encontrado; usando icone padrao do Python.
)

REM --- 5. atalhos ------------------------------------------------------------
echo [5/5] Criando atalhos...

set "ICONE=%BASE%\icone.ico"
set "MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

powershell -NoProfile -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), '%MENU%')) {" ^
  "  $s = $w.CreateShortcut((Join-Path $dir '%NOME%.lnk'));" ^
  "  $s.TargetPath = '%VENV%\Scripts\pythonw.exe';" ^
  "  $s.Arguments = '\"%BASE%\telegram_downloader.py\"';" ^
  "  $s.WorkingDirectory = '%BASE%';" ^
  "  $s.Description = 'Baixa arquivos de grupos do Telegram';" ^
  "  if (Test-Path '%ICONE%') { $s.IconLocation = '%ICONE%' }" ^
  "  $s.Save() }"

echo.
echo ===========================================
echo   Pronto!
echo.
echo   Atalho criado na area de trabalho
echo   e no menu Iniciar.
echo.
echo   Abra com duplo clique. Na primeira vez o
echo   app pede as credenciais e tem um botao
echo   que leva direto a pagina onde obte-las.
echo ===========================================
echo.

choice /C SN /M "Abrir o aplicativo agora"
if !errorlevel! equ 1 start "" "%VENV%\Scripts\pythonw.exe" "%BASE%\telegram_downloader.py"

endlocal
