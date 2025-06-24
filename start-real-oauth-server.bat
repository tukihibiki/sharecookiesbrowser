@echo off
chcp 65001 > nul
title 真实微信OAuth登录服务器

echo ===============================================================
echo                   真实微信OAuth登录服务器
echo                   Real WeChat OAuth Server
echo ===============================================================
echo.
echo 版本: v1.0.0
echo 基于: 真实微信扫码登录抓包分析
echo.
echo 📋 当前配置:
echo ├─ 服务器地址: http://localhost:8001
echo ├─ 微信AppID: wx19fe9af64436b614
echo ├─ 回调域名: alphalawyer.cn
echo └─ 管理员浏览器: 自动启动
echo.
echo 🔧 功能说明:
echo 1. 自动启动管理员浏览器
echo 2. 支持真实微信扫码登录
echo 3. 自动捕获OAuth授权码
echo 4. 生成真实登录cookies
echo 5. 提供API接口供客户端获取cookies
echo.
echo 🎯 使用步骤:
echo 1. 服务器启动后会自动打开管理员浏览器
echo 2. 访问 http://localhost:8001 查看管理界面
echo 3. 点击"打开微信登录页面"进行真实登录
echo 4. 扫码登录成功后，服务器会自动捕获cookies
echo 5. 客户端可通过 http://localhost:8001/cookies 获取cookies
echo.

echo 🚀 正在启动真实微信OAuth登录服务器...
echo 📡 服务器将在 http://localhost:8001 启动
echo 💡 按 Ctrl+C 停止服务器
echo.

python wechat-real-oauth-server.py

echo.
echo 服务器已停止
pause 