@echo off
chcp 65001 >nul
echo 正在运行配置诊断脚本...
echo.

python test_config_diagnostic.py

echo.
echo 按任意键退出...
pause >nul 