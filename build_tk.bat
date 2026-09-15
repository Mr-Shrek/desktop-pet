@echo off
rem ============================================================
rem  收工喵 - tkinter 版打包脚本（零第三方依赖）
rem  产物: dist_nuitka\doubao-pet-tk.exe（单文件）
rem  环境: 需已安装 .packtools 下的 Nuitka + MSVC
rem ============================================================
chcp 65001 >nul
cd /d %~dp0

taskkill /f /im doubao-pet-tk.exe >nul 2>&1
taskkill /f /im doubao-pet-qt.exe >nul 2>&1
del /q dist_nuitka\doubao-pet-tk.exe 2>nul

set PYTHONPATH=%CD%\.packtools

python -X utf8 -m nuitka ^
  --standalone ^
  --onefile ^
  --msvc=latest ^
  --windows-console-mode=disable ^
  --enable-plugin=tk-inter ^
  --tcl-library-dir=%CD%\.packtools\tcl_lib ^
  --tk-library-dir=%CD%\.packtools\tcl_lib ^
  --assume-yes-for-downloads ^
  --jobs=4 ^
  --output-dir=%CD%\dist_nuitka ^
  --output-filename=doubao-pet-tk.exe ^
  --include-data-dir=%CD%\sprites=sprites ^
  main.py

if exist dist_nuitka\doubao-pet-tk.exe (
  echo.
  echo [OK] 打包完成: dist_nuitka\doubao-pet-tk.exe
) else (
  echo.
  echo [FAIL] 打包失败，请查看上方错误信息
)
pause
