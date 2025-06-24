@echo off
chcp 65001 >nul
title 增强版远程浏览器客户端

echo ====================================
echo      增强版远程浏览器客户端
echo ====================================
echo.

echo 正在检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误：未找到Python环境，请先安装Python 3.7+
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo 正在启动增强版GUI客户端...
echo.

python remote_browser_client_gui_enhanced.py

if errorlevel 1 (
    echo.
    echo 程序运行出现错误，请检查：
    echo 1. 是否安装了必要的依赖库 (pip install -r requirements.txt)
    echo 2. 是否有足够的权限
    echo 3. 查看上方的错误信息
    echo.
)

echo.
echo 客户端已退出
pause 