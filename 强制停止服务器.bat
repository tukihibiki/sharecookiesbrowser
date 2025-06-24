@echo off
chcp 65001 > nul
title 强制停止服务器

echo.
echo ==========================================
echo        🆘 强制停止服务器工具
echo ==========================================
echo.
echo ⚠️ 此工具用于强制停止卡死的服务器进程
echo ⚠️ 只有在服务器无法正常关闭时才使用
echo.

echo 正在检查Python依赖...
python -c "import psutil" 2>nul
if errorlevel 1 (
    echo ❌ 缺少psutil模块，正在安装...
    pip install psutil
    if errorlevel 1 (
        echo ❌ 安装psutil失败，请手动安装：pip install psutil
        pause
        exit /b 1
    )
)

echo ✅ 依赖检查完成
echo.

echo 🚀 启动强制停止脚本...
python force_kill_server.py

echo.
echo 处理完成！
pause 