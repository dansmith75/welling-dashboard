@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Welling Dashboard - Update
echo ============================================
echo.

rem The Python updater now owns the complete publish flow:
rem - pulls latest website code
rem - reconciles Supabase through Excel / existing open workbook
rem - creates an unlocked local workbook snapshot
rem - exports and validates dashboard JSON
rem - offers to commit and push changed data
rem
rem Do not run the old workbook-mutating helper scripts here first. They open
rem the OneDrive workbook independently and will fail when the workbook is
rem already open in Excel on this PC.

where py >nul 2>nul
if %errorlevel%==0 (
    py update_welling.py
) else (
    python update_welling.py
)

if errorlevel 1 goto :fail

goto :done

:fail
echo.
echo UPDATE FAILED.

:done
echo.
pause
