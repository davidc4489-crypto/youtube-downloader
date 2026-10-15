@echo off
REM Construit YoutubeDownloader.exe en local sous Windows (Python 3.10+ requis).
setlocal
cd /d "%~dp0"

python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-build.txt || goto :err

REM ffmpeg embarque : on recupere le binaire fourni par imageio-ffmpeg
for /f "delims=" %%i in ('python -c "import imageio_ffmpeg,sys;sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())"') do copy /y "%%i" ffmpeg.exe >nul

pyinstaller --onefile --noconsole --clean --name YoutubeDownloader --add-binary "ffmpeg.exe;." youtube_downloader.py || goto :err

echo.
echo  OK : dist\YoutubeDownloader.exe
pause
exit /b 0

:err
echo.
echo  ERREUR pendant la construction.
pause
exit /b 1
