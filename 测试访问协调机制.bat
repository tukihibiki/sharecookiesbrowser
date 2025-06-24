@echo off
chcp 65001 >nul
title 测试访问协调机制

echo.
echo ╔════════════════════════════════════════════════════════════════════════════════╗
echo ║                            🚦 访问协调机制测试工具 🚦                             ║
echo ╚════════════════════════════════════════════════════════════════════════════════╝
echo.
echo 📋 功能说明:
echo   ✅ 测试多客户端排队机制
echo   ✅ 测试访问权限自动切换
echo   ✅ 测试心跳超时保护
echo   ✅ 验证单点访问控制
echo.
echo ⚠️  测试前请确认:
echo   1. 远程浏览器服务器已启动 (remote_browser_server.py)
echo   2. 服务器运行在 http://localhost:8001
echo   3. 没有其他客户端正在使用访问权限
echo.

pause

echo.
echo 🚀 开始执行访问协调机制测试...
echo.

python test_access_coordinator.py

echo.
echo 🏁 测试完成！
echo.
pause 