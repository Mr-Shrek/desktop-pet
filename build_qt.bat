@echo off
rem ============================================================
rem  收工喵 - PyQt5 版打包脚本（UI 更精美、动画更流畅）
rem  产物: dist_nuitka\doubao-pet-qt.exe（单文件）
rem  环境: 需已安装 Nuitka + MSVC + PyQt5（pip 安装到当前 python）
rem ============================================================
chcp 65001 >nul
cd /d %~dp0

taskkill /f /im doubao-pet-qt.exe >nul 2>&1
taskkill /f /im doubao-pet-tk.exe >nul 2>&1
del /q dist_nuitka\doubao-pet-qt.exe 2>nul

set PYTHONPATH=%CD%\.packtools

python -X utf8 -m nuitka ^
  --standalone ^
  --onefile ^
  --msvc=latest ^
  --windows-console-mode=disable ^
  --enable-plugin=pyqt5 ^
  --assume-yes-for-downloads ^
  --jobs=4 ^
  --output-dir=%CD%\dist_nuitka ^
  --output-filename=doubao-pet-qt.exe ^
  --include-data-dir=%CD%\sprites=sprites ^
  main_qt.py

if exist dist_nuitka\doubao-pet-qt.exe (
  echo.
  echo [OK] 打包完成: dist_nuitka\doubao-pet-qt.exe
) else (
  echo.
  echo [FAIL] 打包失败，请查看上方错误信息
)
pause
