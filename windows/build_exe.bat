@echo off
REM 메모리 뚱냥이 - Windows exe 빌드 스크립트
REM 사전: pip install pyinstaller pyside6 psutil
echo [*] 빌드 시작...
pyinstaller --noconsole --onefile --name MemoryCat --add-data "frames;frames" windows_cat.pyw
echo.
echo [*] 완료! dist\MemoryCat.exe 를 확인하세요.
pause
