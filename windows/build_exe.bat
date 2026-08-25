@echo off
REM 한글 메시지가 cp949 콘솔에서 깨지지 않게 UTF-8 로 맞춘다.
chcp 65001 >nul
REM 메모리 뚱냥이 - Windows exe 빌드 스크립트
REM 사전: pip install -r requirements.txt  그리고  pip install pyinstaller
REM
REM 이 스크립트는 어느 폴더에서 실행해도 동작합니다.
REM (pushd "%~dp0" 로 스크립트가 있는 windows 폴더로 먼저 이동하기 때문에,
REM  저장소 루트에서 windows\build_exe.bat 로 실행해도 frames 를 찾습니다.)
setlocal
pushd "%~dp0" || (echo [X] 스크립트 폴더로 이동하지 못했습니다. & pause & exit /b 1)

echo [*] 빌드 시작... (작업 폴더: %CD%)

where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo.
    echo [X] pyinstaller 를 찾을 수 없습니다.
    echo     먼저 아래를 실행하세요:
    echo         pip install -r requirements.txt
    echo         pip install pyinstaller
    popd
    pause
    exit /b 1
)

if not exist "frames" (
    echo.
    echo [X] frames 폴더가 없습니다. 저장소를 통째로 받았는지 확인하세요.
    popd
    pause
    exit /b 1
)

REM i18n.py 는 저장소 루트에 있다. --paths 로 import 경로에 넣어 준다.
pyinstaller --noconsole --onefile --name MemoryCat ^
    --add-data "frames;frames" ^
    --paths ".." ^
    --hidden-import i18n ^
    windows_cat.pyw
if errorlevel 1 (
    echo.
    echo [X] 빌드 실패. 위의 오류 메시지를 확인하세요.
    popd
    pause
    exit /b 1
)

echo.
echo [*] 완료! %CD%\dist\MemoryCat.exe 를 확인하세요.
echo.
echo [!] 주의: 만들어진 exe 는 코드 서명이 되어 있지 않습니다.
echo     처음 실행할 때 Windows SmartScreen 이 "Windows의 PC 보호" 경고를 띄우고,
echo     백신이 오탐(false positive)으로 차단할 수 있습니다. 자세한 내용은
echo     README.txt 의 [ exe 와 보안 경고 ] 항목을 읽어보세요.
popd
pause
endlocal
