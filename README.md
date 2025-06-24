我来为您详细分析这个远程企查查cookies服务器项目。首先让我读取几个核心文件来了解项目的整体架构和功能。
Read file: 新版-带GUI/requirements.txt
Read file: 新版-带GUI/wechat-real-oauth-server.py
Read file: 新版-带GUI/remote_browser_client_gui_enhanced.py
Read file: 新版-带GUI/server_config.ini
让我先检查当前工作目录的结构：
Ran tool
现在让我读取核心文件来分析项目功能：
Read file: requirements.txt
Read file: wechat-real-oauth-server.py
Read file: remote_browser_client_gui_enhanced.py
Read file: server_config.ini
让我继续读取几个重要的文件以了解完整的功能：
Read file: remote_browser_server.py
Read file: enhanced_admin_tool.py
Read file: 各类修复说明/SOLUTION-SUMMARY.md
现在让我查看启动脚本和说明文档来完整了解项目：
Read file: start-real-oauth-server.bat
Read file: 各类修复说明/增强版客户端使用说明.md
Read file: 各类修复说明/修复总结.md

基于我对您项目的详细分析，我来为您提供一个完整的项目说明，适合在GitHub上发布：

# 🚀 远程浏览器Cookies共享服务器

一个功能强大的远程浏览器Cookies共享解决方案，支持多客户端并发、域名级别的Cookies管理和真实OAuth登录。

## 📋 项目概述

这是一个基于微信OAuth登录的远程浏览器Cookies共享系统，专门为解决企查查等需要登录状态的网站的自动化访问问题而设计。系统提供了完整的服务器端和客户端解决方案，支持真实的微信扫码登录、智能Cookies管理和多用户并发访问。

## ✨ 核心功能

### 🔐 真实OAuth登录支持
- **真实微信扫码登录**：支持真实的微信OAuth授权流程
- **自动Cookies捕获**：自动捕获登录成功后的Cookies
- **跨域Cookies管理**：支持跨域名的Cookies共享
- **管理员浏览器模式**：提供管理员专用浏览器进行登录操作

### 🌐 多客户端并发系统
- **智能排队机制**：基于域名可用性的智能排队系统
- **并发控制**：支持1-10个客户端同时在线（可配置）
- **域名级别管理**：按域名分配Cookies，避免冲突
- **实时状态监控**：WebSocket实时通信，监控客户端状态

### 🖥️ 完整GUI界面
- **服务器管理GUI**：提供可视化的服务器管理界面
- **增强版客户端GUI**：用户友好的客户端操作界面
- **管理员工具**：专业的Cookies管理和导入工具
- **实时日志显示**：详细的操作日志和状态监控

### 🔧 高级功能
- **自动浏览器启动**：客户端自动启动浏览器并注入Cookies
- **心跳机制**：自动维持连接，处理异常断线
- **权限自动释放**：浏览器关闭时自动释放访问权限
- **配置持久化**：客户端配置自动保存

## 🏗️ 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   管理员工具     │    │   服务器核心     │    │   客户端GUI     │
│ enhanced_admin  │◄──►│ remote_browser  │◄──►│ client_gui_     │
│ _tool.py       │    │ _server.py      │    │ enhanced.py     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        ▲                       ▲                       ▲
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  OAuth登录服务   │    │   Cookies存储    │    │   本地浏览器     │
│ wechat-real-    │    │   管理系统       │    │   Playwright     │
│ oauth-server.py │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🛠️ 环境要求

### Python环境
- **Python 3.8+** (推荐 Python 3.9+)
- 支持Windows 10/11

### 系统依赖
```bash
# Chrome浏览器（Playwright会自动下载）
# Windows PowerShell（用于启动脚本）
```

## 📦 安装配置

### 1. 克隆项目
```bash
git clone https://github.com/your-username/remote-browser-cookies-server.git
cd remote-browser-cookies-server
```

### 2. 安装Python依赖
```bash
# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 安装Playwright浏览器
```bash
# 安装Playwright浏览器
playwright install chromium
```

### 4. 配置文件设置

**服务器配置** (`server_config.ini`):
```ini
[server]
max_concurrent_clients = 2
heartbeat_interval = 30
max_inactive_minutes = 10
```

## 🚀 快速开始

### 方式一：一键启动（推荐）

#### 启动服务器
```bash
# 双击运行
start-real-oauth-server.bat
```

#### 启动客户端
```bash
# 新开命令窗口，双击运行
启动增强版GUI客户端.bat
```

### 方式二：手动启动

#### 1. 启动OAuth登录服务器
```bash
python wechat-real-oauth-server.py
```
服务器将在 `http://localhost:8001` 启动

#### 2. 启动远程浏览器服务器
```bash
python remote_browser_server.py
```
服务器将在默认端口启动

#### 3. 启动客户端
```bash
python remote_browser_client_gui_enhanced.py
```

## 📖 使用说明

### 🔐 管理员操作流程

1. **启动OAuth服务器**
   ```bash
   启动真实OAuth服务器: start-real-oauth-server.bat
   ```

2. **进行微信登录**
   - 访问 `http://localhost:8001`
   - 点击"打开微信登录页面"
   - 使用微信扫码登录
   - 系统自动捕获登录Cookies

3. **启动主服务器**
   ```bash
   启动GUI管理器: 启动GUI管理器.bat
   ```

4. **管理Cookies**
   - 使用增强版管理员工具导入/导出Cookies
   - 监控客户端连接状态
   - 调整系统参数

### 👤 客户端使用流程

1. **启动客户端**
   ```bash
   启动增强版GUI客户端: 启动增强版GUI客户端.bat
   ```

2. **配置连接**
   - 设置服务器地址（默认: localhost:8001）
   - 点击"连接服务器"

3. **选择域名**
   - 点击"刷新域名"获取可用域名
   - 选择需要的域名（支持多选）

4. **请求访问权限**
   - 点击"请求访问权限"
   - 等待分配或排队

5. **打开浏览器**
   - 获得权限后点击"打开浏览器"
   - 系统自动注入Cookies并导航到目标网站

## 🔧 高级配置

### 服务器配置选项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `max_concurrent_clients` | 最大并发客户端数 | 2 |
| `heartbeat_interval` | 心跳间隔（秒） | 30 |
| `max_inactive_minutes` | 最大非活跃时间（分钟） | 10 |

### 客户端配置选项

客户端配置保存在 `client_config.ini`:
```ini
[SERVER]
host = localhost
port = 8001
```

### OAuth配置

OAuth服务器配置位于 `wechat-real-oauth-server.py`:
```python
wechat_config = {
    'app_id': 'wx19fe9af64436b614',
    'redirect_uri': 'https://alphalawyer.cn/wechatlogin/...',
    'scope': 'snsapi_login'
}
```

## 📊 API接口

### 服务器管理API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/admin/key` | GET | 获取管理员密钥 |
| `/admin/cookies` | POST | 更新Cookies |
| `/admin/clients/{id}/kick` | POST | 踢出客户端 |
| `/admin/server/config/max-clients` | POST | 设置最大客户端数 |

### 客户端API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/create_session` | POST | 创建会话 |
| `/access/request` | POST | 请求访问权限 |
| `/cookies` | GET | 获取Cookies |
| `/domains` | GET | 获取域名信息 |

## 🔍 故障排除

### 常见问题

**Q: 连接服务器失败**
```
A: 检查服务器是否启动，端口是否被占用
   netstat -an | findstr :8001
```

**Q: 微信登录失败**
```
A: 确保网络连接正常，检查微信OAuth配置
   查看服务器日志获取详细错误信息
```

**Q: Cookies不生效**
```
A: 检查Cookies是否过期，域名是否匹配
   使用管理员工具重新导入Cookies
```

**Q: 浏览器启动失败**
```
A: 确保Playwright浏览器已安装
   playwright install chromium
```

### 日志文件

- 服务器日志: `logs/remote_browser_server.log`
- 客户端日志: 显示在GUI界面中
- OAuth服务器日志: 控制台输出

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 📄 许可证

本项目采用 AGPL-3.0 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🎯 项目特色

- ✅ **真实登录**: 基于真实微信OAuth，非模拟登录
- ✅ **智能管理**: 域名级别的Cookies分配和管理
- ✅ **并发支持**: 多客户端智能排队和并发控制
- ✅ **用户友好**: 完整的GUI界面，操作简单直观
- ✅ **稳定可靠**: 完善的错误处理和自动恢复机制
- ✅ **高度可配置**: 丰富的配置选项，适应不同需求


---

**注意**: 本项目仅供学习和研究使用，请遵守相关网站的使用条款和法律法规。

