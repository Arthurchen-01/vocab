@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   VerbalEx 课程交付 - 粘贴链接即可
echo ============================================================
echo.
echo 已知课程（可直接输入链接，系统会自动识别是哪一集）：
echo   哈佛《公正》 ep01  https://www.youtube.com/watch?v=kBdfcR-8hEY
echo   哈佛《公正》 ep02  https://www.youtube.com/watch?v=0O2Rq4HJBxw
echo   哈佛《公正》 ep03  https://www.youtube.com/watch?v=Qw4l1w0rkjs
echo   哈佛《公正》 ep04  https://www.youtube.com/watch?v=MGyygiXMzRk
echo.

set "LINK="
set /p LINK=请粘贴课程视频链接（直接回车则交付 ep03）:
if "%LINK%"=="" (
  set "ARGS=--episode ep03"
) else (
  set "ARGS=--url %LINK%"
)

set "EP="
set /p EP=如果这是全新的一集，请输入卡组 id（如 ep05）；否则直接回车:
if not "%EP%"=="" set "ARGS=%ARGS% --episode %EP%"

echo.
echo 即将执行: python deliver_client.py %ARGS% --commit
echo.
python "%~dp0deliver_client.py" %ARGS% --commit
echo.
echo 交付结束。验收报告：..\..\docs\*_DELIVERY_REPORT.md
pause
endlocal
