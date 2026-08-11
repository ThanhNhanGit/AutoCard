@echo off
REM Drag a subtitle file onto this .bat, or just double-click it and pick one
REM when asked. Then paste the video URL (YouTube, etc.) when prompted.
setlocal

set "SUB=%~1"
if "%SUB%"=="" (
    echo Drag your .srt file onto this window now, then press Enter:
    set /p SUB=Subtitle file path:
)

set /p URL=Video URL:

"%~dp0mpv.exe" "%URL%" --sub-file="%SUB%"
