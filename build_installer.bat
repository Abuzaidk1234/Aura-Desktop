@echo off
echo Building AURA (Directory Mode)...
pyinstaller --noconfirm --onedir --windowed --icon=aura_icon.ico --name=AURA --add-data="aura_icon.ico;." --add-data="avatar.glb;." --add-data="index.html;." --add-data="assets;assets" main.py
echo Build complete! The files are in the "dist\AURA" folder.

echo Checking for Inno Setup Compiler (ISCC)...
where iscc >nul 2>&1
if %errorlevel% equ 0 (
    echo Compiling Setup.exe...
    iscc installer.iss
    echo Setup.exe compiled successfully!
) else (
    echo ISCC not found in PATH. Skipping Setup.exe compilation. You can run Inno Setup manually.
)
pause
