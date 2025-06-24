@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 🚀 正在启动智能浏览器客户端...
echo ====================================
echo.
echo 📋 智能客户端特性:
echo    ✅ 自动保护用户现有登录状态
echo    ✅ 智能检测是否需要应用管理员cookies  
echo    ✅ 提供手动控制选项
echo    ✅ 不会强制覆盖用户登录状态
echo.
echo 💡 使用说明:
echo    - 如果您已登录，客户端会保护您的登录状态
echo    - 如果您未登录，客户端会尝试使用管理员cookies
echo    - 您随时可以手动切换登录状态
echo.

python intelligent_browser_client.py

echo.
echo 按任意键退出...
pause >nul 