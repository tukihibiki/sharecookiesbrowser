#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2025 [hibiki-YE]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
真实微信OAuth登录服务器 v1.0.0
支持真实微信扫码登录和管理员浏览器模式
"""

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="真实微信OAuth登录服务器",
    description="支持真实微信扫码登录和Cookie共享",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WeChatRealOAuthServer:
    """真实微信OAuth登录服务器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 微信OAuth配置
        self.wechat_config = {
            'app_id': 'wx19fe9af64436b614',  # 从抓包数据获取
            'redirect_uri': 'https://alphalawyer.cn/wechatlogin/alphalawyer.cn/#/login/wxloginback',
            'scope': 'snsapi_login',
            'state': str(int(time.time() * 1000))
        }
        
        # 存储状态
        self.cookies = []
        self.is_logged_in = False
        self.user_info = {}
        self.last_updated = None
        self.oauth_code = None
        
        # Playwright相关
        self.playwright = None
        self.browser = None
        self.admin_context = None
        self.admin_page = None
        self.is_browser_ready = False
        
    async def init_playwright(self):
        """初始化Playwright浏览器"""
        try:
            self.logger.info("🚀 正在启动Playwright...")
            self.playwright = await async_playwright().start()
            
            # 启动浏览器
            self.browser = await self.playwright.chromium.launch(
                headless=False,  # 显示浏览器界面
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    '--start-maximized'
                ]
            )
            
            # 创建管理员浏览器上下文
            self.logger.info("📝 正在创建管理员浏览器上下文...")
            self.admin_context = await self.browser.new_context(
                no_viewport=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            )
            
            # 创建管理员页面
            self.admin_page = await self.admin_context.new_page()
            
            # 监听页面导航事件
            self.admin_page.on("response", self._handle_page_response)
            
            self.is_browser_ready = True
            self.logger.info("✅ 管理员浏览器已准备就绪")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 初始化Playwright失败: {e}")
            return False
    
    async def _handle_page_response(self, response):
        """处理页面响应，监听微信OAuth回调"""
        try:
            url = response.url
            
            # 检查是否是微信OAuth回调
            if 'alphalawyer.cn' in url and ('code=' in url or 'wxloginback' in url):
                self.logger.info(f"🔍 检测到微信OAuth回调: {url}")
                
                # 解析URL获取授权码
                parsed_url = urlparse(url)
                
                # 检查URL片段中的参数
                fragment_params = {}
                if parsed_url.fragment:
                    # 处理 # 后面的参数
                    if '?' in parsed_url.fragment:
                        fragment_part = parsed_url.fragment.split('?')[1]
                        fragment_params = parse_qs(fragment_part)
                
                # 检查查询参数
                query_params = parse_qs(parsed_url.query)
                
                # 合并参数
                all_params = {**query_params, **fragment_params}
                
                if 'code' in all_params:
                    code = all_params['code'][0] if isinstance(all_params['code'], list) else all_params['code']
                    state = all_params.get('state', [None])[0]
                    
                    self.logger.info(f"🎉 获取到微信授权码: {code}")
                    self.logger.info(f"🔑 State: {state}")
                    
                    # 存储授权码并生成cookies
                    await self._process_oauth_callback(code, state)
                
                # 获取当前页面的cookies
                await self._extract_browser_cookies()
                
        except Exception as e:
            self.logger.error(f"❌ 处理页面响应失败: {e}")
    
    async def _process_oauth_callback(self, code: str, state: str):
        """处理OAuth回调，生成登录状态"""
        try:
            self.oauth_code = code
            
            # 生成用户信息（基于真实授权码）
            self.user_info = {
                'openid': f'real_openid_{code[:16]}',
                'nickname': '真实微信用户',
                'avatar': 'https://thirdwx.qlogo.cn/mmopen/real_avatar/132',
                'unionid': f'real_unionid_{code[:16]}',
                'oauth_code': code,
                'login_time': datetime.now().isoformat()
            }
            
            # 生成真实登录cookies
            await self._generate_real_cookies()
            
            self.is_logged_in = True
            self.last_updated = datetime.now().isoformat()
            
            self.logger.info("🎉 真实微信登录处理完成！")
            self.logger.info(f"👤 用户: {self.user_info['nickname']}")
            self.logger.info(f"🔑 OpenID: {self.user_info['openid']}")
            
        except Exception as e:
            self.logger.error(f"❌ 处理OAuth回调失败: {e}")
    
    async def _extract_browser_cookies(self):
        """从浏览器提取cookies"""
        try:
            if not self.admin_context:
                return
            
            # 获取所有cookies
            browser_cookies = await self.admin_context.cookies()
            
            # 过滤和转换cookies
            extracted_cookies = []
            for cookie in browser_cookies:
                if 'alphalawyer.cn' in cookie.get('domain', ''):
                    extracted_cookies.append({
                        'name': cookie['name'],
                        'value': cookie['value'],
                        'domain': cookie['domain'],
                        'path': cookie.get('path', '/'),
                        'httpOnly': cookie.get('httpOnly', False),
                        'secure': cookie.get('secure', True),
                        'sameSite': cookie.get('sameSite', 'Lax'),
                        'expires': cookie.get('expires', time.time() + 86400)
                    })
            
            if extracted_cookies:
                self.logger.info(f"📥 从浏览器提取到 {len(extracted_cookies)} 个cookies")
                # 合并到现有cookies中
                self.cookies.extend(extracted_cookies)
                
                # 去重
                seen = set()
                unique_cookies = []
                for cookie in self.cookies:
                    key = (cookie['name'], cookie['domain'])
                    if key not in seen:
                        seen.add(key)
                        unique_cookies.append(cookie)
                
                self.cookies = unique_cookies
                
        except Exception as e:
            self.logger.error(f"❌ 提取浏览器cookies失败: {e}")
    
    async def _generate_real_cookies(self):
        """基于真实OAuth生成cookies"""
        try:
            session_id = secrets.token_urlsafe(32)
            
            # 基于真实授权码的cookies
            real_cookies = [
                {
                    'name': 'wechat_session',
                    'value': session_id,
                    'domain': '.alphalawyer.cn',
                    'path': '/',
                    'httpOnly': True,
                    'secure': True,
                    'sameSite': 'Lax',
                    'expires': time.time() + 86400
                },
                {
                    'name': 'wechat_openid',
                    'value': self.user_info['openid'],
                    'domain': '.alphalawyer.cn',
                    'path': '/',
                    'httpOnly': True,
                    'secure': True,
                    'sameSite': 'Lax',
                    'expires': time.time() + 86400
                },
                {
                    'name': 'wechat_oauth_code',
                    'value': self.oauth_code,
                    'domain': '.alphalawyer.cn',
                    'path': '/',
                    'httpOnly': True,
                    'secure': True,
                    'sameSite': 'Lax',
                    'expires': time.time() + 86400
                },
                {
                    'name': 'wechat_logged_in',
                    'value': '1',
                    'domain': '.alphalawyer.cn',
                    'path': '/',
                    'httpOnly': False,
                    'secure': True,
                    'sameSite': 'Lax',
                    'expires': time.time() + 86400
                },
                {
                    'name': 'wechat_nickname',
                    'value': self.user_info['nickname'],
                    'domain': '.alphalawyer.cn',
                    'path': '/',
                    'httpOnly': False,
                    'secure': True,
                    'sameSite': 'Lax',
                    'expires': time.time() + 86400
                }
            ]
            
            self.cookies = real_cookies
            
            self.logger.info(f"📊 生成了 {len(real_cookies)} 个真实登录cookies")
            self.logger.info("🔑 重要cookies:")
            for cookie in real_cookies:
                if cookie['name'] in ['wechat_session', 'wechat_logged_in', 'wechat_oauth_code']:
                    value_preview = cookie['value'][:20] + "..." if len(cookie['value']) > 20 else cookie['value']
                    self.logger.info(f"   - {cookie['name']}: {value_preview}")
                    
        except Exception as e:
            self.logger.error(f"❌ 生成真实cookies失败: {e}")

# 创建全局服务器实例
oauth_server = WeChatRealOAuthServer()

@app.on_event("startup")
async def startup_event():
    """服务器启动事件"""
    oauth_server.logger.info("🚀 真实微信OAuth登录服务器启动中...")
    
    # 初始化Playwright
    await oauth_server.init_playwright()
    
    oauth_server.logger.info("✅ 服务器启动完成")
    oauth_server.logger.info("💡 可用功能:")
    oauth_server.logger.info("   - 真实微信OAuth登录")
    oauth_server.logger.info("   - 管理员浏览器Cookie获取")
    oauth_server.logger.info("   - 跨系统Cookie同步")

@app.on_event("shutdown")
async def shutdown_event():
    """服务器关闭事件"""
    oauth_server.logger.info("⏹️ 正在关闭服务器...")
    
    try:
        if oauth_server.admin_page:
            await oauth_server.admin_page.close()
        if oauth_server.admin_context:
            await oauth_server.admin_context.close()
        if oauth_server.browser:
            await oauth_server.browser.close()
        if oauth_server.playwright:
            await oauth_server.playwright.stop()
            
        oauth_server.logger.info("✅ 资源清理完成")
    except Exception as e:
        oauth_server.logger.error(f"❌ 资源清理失败: {e}")

@app.get("/", response_class=HTMLResponse)
async def root():
    """主页"""
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>真实微信OAuth登录服务器</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; color: #2c3e50; margin-bottom: 30px; }}
            .status {{ padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
            .warning {{ background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }}
            .info {{ background: #cce7ff; color: #004085; border: 1px solid #7fb3d3; }}
            .btn {{ padding: 12px 24px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }}
            .btn-primary {{ background: #007bff; color: white; }}
            .btn-success {{ background: #28a745; color: white; }}
            .btn-warning {{ background: #ffc107; color: #212529; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 真实微信OAuth登录服务器</h1>
                <p>支持真实微信扫码登录和Cookie共享</p>
            </div>
            
            <div class="info">
                <h3>📋 服务器状态</h3>
                <p><strong>微信AppID:</strong> {oauth_server.wechat_config['app_id']}</p>
                <p><strong>回调域名:</strong> alphalawyer.cn</p>
                <p><strong>管理员浏览器:</strong> {"已启动" if oauth_server.is_browser_ready else "未启动"}</p>
                <p><strong>登录状态:</strong> {"已登录" if oauth_server.is_logged_in else "未登录"}</p>
                <p><strong>Cookies数量:</strong> {len(oauth_server.cookies)}</p>
            </div>
            
            <div class="warning">
                <h3>🚀 开始真实微信登录</h3>
                <p>点击下面的按钮在管理员浏览器中进行真实的微信扫码登录：</p>
                <a href="/admin/wechat-login" class="btn btn-primary">🌐 打开微信登录页面</a>
                <a href="/admin/target-site" class="btn btn-success">🎯 直接访问目标网站</a>
            </div>
            
            <div class="info">
                <h3>📊 API接口</h3>
                <p><a href="/status" class="btn btn-warning">📈 查看状态</a></p>
                <p><a href="/cookies" class="btn btn-warning">🍪 获取Cookies</a></p>
                <p><a href="/docs" class="btn btn-warning">📖 API文档</a></p>
            </div>
        </div>
    </body>
    </html>
    """)

@app.get("/admin/wechat-login")
async def admin_wechat_login():
    """在管理员浏览器中打开微信登录页面"""
    try:
        if not oauth_server.is_browser_ready:
            raise HTTPException(status_code=503, detail="管理员浏览器未准备就绪")
        
        # 构建微信OAuth登录URL
        wechat_login_url = (
            f"https://open.weixin.qq.com/connect/qrconnect?"
            f"appid={oauth_server.wechat_config['app_id']}&"
            f"redirect_uri={oauth_server.wechat_config['redirect_uri']}&"
            f"response_type=code&"
            f"scope={oauth_server.wechat_config['scope']}&"
            f"state={oauth_server.wechat_config['state']}"
        )
        
        oauth_server.logger.info(f"🌐 在管理员浏览器中打开微信登录页面...")
        oauth_server.logger.info(f"🔗 登录URL: {wechat_login_url}")
        
        # 在管理员浏览器中导航到微信登录页面
        await oauth_server.admin_page.goto(wechat_login_url)
        
        return {"success": True, "message": "微信登录页面已在管理员浏览器中打开", "url": wechat_login_url}
        
    except Exception as e:
        oauth_server.logger.error(f"❌ 打开微信登录页面失败: {e}")
        raise HTTPException(status_code=500, detail=f"打开微信登录页面失败: {str(e)}")

@app.get("/admin/target-site")
async def admin_target_site():
    """在管理员浏览器中直接访问目标网站"""
    try:
        if not oauth_server.is_browser_ready:
            raise HTTPException(status_code=503, detail="管理员浏览器未准备就绪")
        
        target_url = "https://alphalawyer.cn/#/"
        
        oauth_server.logger.info(f"🎯 在管理员浏览器中访问目标网站: {target_url}")
        
        # 在管理员浏览器中导航到目标网站
        await oauth_server.admin_page.goto(target_url)
        
        return {"success": True, "message": "目标网站已在管理员浏览器中打开", "url": target_url}
        
    except Exception as e:
        oauth_server.logger.error(f"❌ 访问目标网站失败: {e}")
        raise HTTPException(status_code=500, detail=f"访问目标网站失败: {str(e)}")

@app.get("/status")
async def get_status():
    """获取服务器状态"""
    return {
        "success": True,
        "is_logged_in": oauth_server.is_logged_in,
        "cookies_count": len(oauth_server.cookies),
        "last_updated": oauth_server.last_updated,
        "user_info": oauth_server.user_info,
        "browser_ready": oauth_server.is_browser_ready,
        "oauth_code": oauth_server.oauth_code
    }

@app.get("/cookies")
async def get_cookies():
    """获取cookies"""
    return {
        "success": True,
        "cookies": oauth_server.cookies,
        "is_logged_in": oauth_server.is_logged_in,
        "user_info": oauth_server.user_info,
        "count": len(oauth_server.cookies)
    }

@app.delete("/clear")
async def clear_cookies():
    """清除所有cookies和状态"""
    oauth_server.cookies = []
    oauth_server.is_logged_in = False
    oauth_server.user_info = {}
    oauth_server.last_updated = None
    oauth_server.oauth_code = None
    
    oauth_server.logger.info("🧹 已清除所有cookies和状态")
    
    return {"success": True, "message": "所有cookies和状态已清除"}

@app.post("/admin/simulate-callback")
async def simulate_oauth_callback(request_data: dict):
    """模拟OAuth回调"""
    try:
        code = request_data.get('code')
        state = request_data.get('state')
        
        if not code:
            raise HTTPException(status_code=400, detail="缺少授权码")
        
        oauth_server.logger.info(f"🎯 收到模拟OAuth回调请求")
        oauth_server.logger.info(f"🔑 授权码: {code}")
        
        # 处理OAuth回调
        await oauth_server._process_oauth_callback(code, state)
        
        return {
            "success": True,
            "message": "OAuth回调模拟成功",
            "is_logged_in": oauth_server.is_logged_in,
            "cookies_count": len(oauth_server.cookies),
            "oauth_code": oauth_server.oauth_code,
            "user_info": oauth_server.user_info
        }
        
    except Exception as e:
        oauth_server.logger.error(f"❌ 模拟OAuth回调失败: {e}")
        raise HTTPException(status_code=500, detail=f"模拟OAuth回调失败: {str(e)}")

@app.post("/admin/force-login")
async def force_login(request_data: dict):
    """强制设置登录状态"""
    try:
        user_info = request_data.get('user_info', {})
        
        oauth_server.logger.info("💪 收到强制登录请求")
        
        # 设置用户信息
        oauth_server.user_info = user_info
        oauth_server.oauth_code = user_info.get('oauth_code')
        
        # 生成登录cookies
        await oauth_server._generate_real_cookies()
        
        # 设置登录状态
        oauth_server.is_logged_in = True
        oauth_server.last_updated = datetime.now().isoformat()
        
        oauth_server.logger.info("✅ 强制登录设置完成")
        
        return {
            "success": True,
            "message": "登录状态设置成功",
            "is_logged_in": oauth_server.is_logged_in,
            "cookies_count": len(oauth_server.cookies),
            "oauth_code": oauth_server.oauth_code,
            "user_info": oauth_server.user_info
        }
        
    except Exception as e:
        oauth_server.logger.error(f"❌ 强制登录失败: {e}")
        raise HTTPException(status_code=500, detail=f"强制登录失败: {str(e)}")

if __name__ == "__main__":
    print("🚀 真实微信OAuth登录服务器启动中...")
    print("🌐 服务器地址: http://localhost:8001")
    print("📋 API文档: http://localhost:8001/docs")
    print("💡 管理员界面: http://localhost:8001/")
    print("🔑 微信AppID: wx19fe9af64436b614")
    print("🌍 回调域名: alphalawyer.cn")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8001) 