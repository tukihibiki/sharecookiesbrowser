@echo off
chcp 65001 > nul
title 真实微信OAuth客户端

echo ===============================================================
echo                   真实微信OAuth客户端
echo                   Real WeChat OAuth Client
echo ===============================================================
echo.
echo 版本: v1.0.0
echo 配套: 真实微信OAuth登录服务器
echo.
echo 📋 功能说明:
echo ├─ 从服务器获取真实登录cookies
echo ├─ 自动应用cookies到浏览器
echo ├─ 访问目标网站测试登录状态
echo └─ 支持用户交互测试
echo.
echo 🔧 使用前提:
echo 1. 确保真实OAuth服务器正在运行 (端口8001)
echo 2. 确保已在服务器端完成微信登录
echo 3. 服务器管理界面: http://localhost:8001
echo.
echo 🎯 测试流程:
echo 1. 客户端会自动连接服务器
echo 2. 获取真实的微信登录cookies
echo 3. 应用cookies到客户端浏览器
echo 4. 访问目标网站 (alphalawyer.cn)
echo 5. 验证登录状态和功能
echo.

echo 🚀 正在启动真实微信OAuth客户端...
echo 📡 连接服务器: http://localhost:8001
echo 🎯 目标网站: https://alphalawyer.cn
echo 💡 按 Ctrl+C 停止客户端
echo.

python real-oauth-client.py

echo.
echo 客户端已停止
pause 