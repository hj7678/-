@echo off
echo ========================================
echo  FM接管模式 — 一键启动 (5服务)
echo ========================================
echo.

start "Stock" cmd /k "py -m stock_management.main"
timeout /t 2 /nobreak >nul

start "Scheduling" cmd /k "py -m scheduling.main"
timeout /t 2 /nobreak >nul

start "Diagnosis" cmd /k "py -m tcp_diagnosis.main"
timeout /t 1 /nobreak >nul

start "FeedingMaster" cmd /k "py -m feeding_master.main"
timeout /t 3 /nobreak >nul

start "HMI" cmd /k "py -m upper_hmi.main"

echo.
echo 全部服务已启动!
echo ========================================
