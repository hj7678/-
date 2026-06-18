@echo off
chcp 65001 >nul
echo ========================================
echo  FM接管模式 — 一键启动
echo ========================================
echo.
echo 请先关闭所有已有的服务窗口!
echo.
pause
echo.

start "Stock(8895)" cmd /k "title Stock(8895) && py -m stock_management.main"
timeout /t 2 /nobreak >nul

start "Scheduling(8891-94)" cmd /k "title Scheduling && py -m scheduling.main"
timeout /t 3 /nobreak >nul

start "Diagnosis(8890)" cmd /k "title Diagnosis(8890) && py -m tcp_diagnosis.main"
timeout /t 1 /nobreak >nul

start "FM(8896)" cmd /k "title FM(8896) && py -m feeding_master.main"
timeout /t 3 /nobreak >nul

start "HMI" cmd /k "title HMI && py -m upper_hmi.main"

echo.
echo ========================================
echo  全部启动完毕 (5个窗口)
echo ========================================
