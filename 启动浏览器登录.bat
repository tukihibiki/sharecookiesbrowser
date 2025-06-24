@echo off
chcp 65001 > nul
title 增强版管理员工具 - 浏览器手动登录

echo.
echo ================================================================
echo         增强版管理员工具 - AlphaLawyer浏览器手动登录
echo ================================================================
echo.
echo 🔔 此模式将:
echo  ✓ 自动打开浏览器并导航到AlphaLawyer登录页面
echo  ✓ 清理旧cookies避免误报
echo  ✓ 实时监控您的登录状态
echo  ✓ 智能检测微信扫码登录成功
echo  ✓ 自动保存并同步cookies到服务器
echo  ✓ 提供详细的登录过程日志
echo.
echo 📋 操作步骤:
echo  1. 程序打开浏览器后，点击"微信登录"
echo  2. 使用微信扫描二维码
echo  3. 在手机上确认登录
echo  4. 等待页面跳转，程序会自动检测
echo.
echo ================================================================
echo.

REM 检查Python
python --version > nul 2>&1
if errorlevel 1 (
    echo ❌ 错误：未找到Python
    pause
    exit /b 1
)

REM 检查依赖
echo 🔍 检查环境...
python -c "import playwright, aiohttp" > nul 2>&1
if errorlevel 1 (
    echo ❌ 缺少依赖，正在安装...
    pip install -r requirements.txt
)

REM 检查浏览器
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); p.stop()" > nul 2>&1
if errorlevel 1 (
    echo ⚠️  安装浏览器...
    python setup_browser.py
)

echo ✅ 环境检查完成
echo.
echo 🚀 启动浏览器手动登录模式...
echo ⚠️  请注意浏览器窗口，程序会自动打开登录页面
echo.

REM 启动手动浏览器模式
python enhanced_admin_tool.py --action manual-login --site alphalawyer

echo.
echo 🏁 程序已退出，按任意键关闭窗口...
pause > nul 