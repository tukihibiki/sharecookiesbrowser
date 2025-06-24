@echo off
chcp 65001 >nul
echo 正在测试GUI配置修复...
echo.

echo 1. 检查配置文件内容:
type server_config.ini
echo.

echo 2. 启动GUI管理器(查看控制台输出中的配置加载信息):
echo    观察控制台是否显示 "🔧 GUI管理器加载配置: max_concurrent_clients = 2"
echo.
echo 3. 然后在GUI界面中检查"最大同时在线客户端数"是否显示为2
echo.

echo 按任意键启动GUI管理器...
pause >nul

python server_gui_manager_fixed.py 