@echo off
cd /d "%~dp0"

echo ================================================
echo  FinanzIQ
echo ================================================
echo.

echo [1/4]  Payslips ^& bank statements...
python scripts\process_payslip.py
if errorlevel 1 (
    echo   WARNING: Payslip/bank processing reported errors. Continuing...
)

echo.
echo [2/4]  Kassenbons...
python scripts\process_receipts.py
if errorlevel 1 (
    echo   WARNING: Receipt processing reported errors. Continuing...
)

echo.
echo [3/4]  Building standalone dashboard...
python build.py
if errorlevel 1 (
    echo   WARNING: Standalone build failed. Continuing...
)

echo.
echo [4/4]  Opening dashboard...
python launch.py
