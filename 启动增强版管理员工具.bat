@echo off
chcp 65001 > nul
title 增强版管理员工具 - AlphaLawyer微信扫码登录

echo.
echo ================================================================
echo               增强版管理员工具 - AlphaLawyer微信扫码登录
echo ================================================================
echo.
echo 功能说明：
echo  ✓ 自动打开浏览器并导航到微信登录页面
echo  ✓ 智能检测微信扫码登录状态
echo  ✓ 自动保存并同步cookies到服务器
echo  ✓ 支持所有客户端立即获得登录状态
echo.
echo 使用步骤：
echo  1. 程序将自动打开浏览器
echo  2. 请在浏览器中完成微信扫码登录
echo  3. 登录成功后程序会自动检测并同步cookies
echo  4. 按 Ctrl+C 可以停止监控
echo.
echo ================================================================
echo.

REM 检查Python是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo ❌ 错误：未找到Python，请先安装Python 3.7+
    pause
    exit /b 1
)

REM 检查依赖是否安装
echo 🔍 检查依赖...
python -c "import playwright, aiohttp, fastapi" > nul 2>&1
if errorlevel 1 (
    echo ❌ 缺少依赖，正在安装...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ❌ 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
)

REM 检查浏览器是否安装
echo 🔍 检查浏览器...
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); p.stop()" > nul 2>&1
if errorlevel 1 (
    echo ⚠️  需要安装Playwright浏览器...
    python setup_browser.py
    if errorlevel 1 (
        echo ❌ 浏览器安装失败
        pause
        exit /b 1
    )
)

echo ✅ 环境检查完成
echo.
echo 🚀 启动增强版管理员工具...
echo.

REM 启动管理员工具
echo 选择启动模式:
echo [1] 自动模式 (推荐) - 首先尝试API自动登录，失败时切换到浏览器
echo [2] 手动模式 - 直接打开浏览器，手动完成微信扫码登录
echo [3] 查看当前cookies
echo.
set /p choice="请输入选择 (1-3，默认1): "

if "%choice%"=="" set choice=1
if "%choice%"=="2" goto manual
if "%choice%"=="3" goto cookies

:auto
echo.
echo 🚀 启动自动模式...
python enhanced_admin_tool.py --action auto-login --site alphalawyer
goto end

:manual
echo.
echo 🖥️ 启动手动浏览器模式...
python enhanced_admin_tool.py --action manual-login --site alphalawyer
goto end

:cookies
echo.
echo 📋 显示当前cookies...
python enhanced_admin_tool.py --action cookies --site alphalawyer
echo.
pause
goto end

:end

echo.
echo 程序已退出，按任意键关闭窗口...
pause > nul 