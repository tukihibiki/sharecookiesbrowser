@echo off
chcp 65001 >nul
title 远程浏览器服务器管理中心

echo 正在启动服务器管理界面...
echo.

python server_gui_manager_fixed.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 启动失败，请检查 Python 环境和依赖包。
    echo 详细错误信息请查看 "logs/remote_browser_server.log" 文件。
    echo.
    pause
) 