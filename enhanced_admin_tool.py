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

import argparse
import asyncio
import aiohttp
import json
import logging
import time
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin, urlparse, parse_qs
from PIL import Image
from io import BytesIO
import threading
import os
# 添加浏览器自动化支持
from playwright.async_api import async_playwright, Browser, Page

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QRCodeDisplay(threading.Thread):
    """二维码显示线程 - 参考微信方案"""
    def __init__(self, image_data: bytes):
        threading.Thread.__init__(self)
        self.image_data = image_data
        self.daemon = True
        
    def run(self):
        try:
            img = Image.open(BytesIO(self.image_data))
            img.show()
        except Exception as e:
            logger.error(f"显示二维码失败: {e}")

class EnhancedAdminTool:
    """增强版管理员工具 - 完整实现微信扫码登录方案"""
    
    def __init__(self, server_url: str = "http://localhost:8001", target_site: str = "alphalawyer"):
        self.server_url = server_url
        self.target_site = target_site
        self.session: Optional[aiohttp.ClientSession] = None
        self.admin_key: Optional[str] = None
        self.current_cookies: List[dict] = []
        self.running = True
        
        # 添加浏览器相关属性
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        
        # 配置文件路径
        self.config_dir = Path(__file__).parent / "browser_data"
        self.config_dir.mkdir(exist_ok=True)
        self.cookies_file = self.config_dir / f"admin_cookies_{target_site}.json"
        
        # 扫码登录状态
        self.login_states = {
            "pending": "二维码未失效，请扫码",
            "scanned": "已扫码，请在手机上确认",
            "confirmed": "已确认，登录成功",
            "expired": "二维码已过期，请重新获取",
            "error": "登录过程出现错误"
        }
        
        # 网站特定配置
        self.site_configs = {
            "alphalawyer": {
                "base_url": "https://alphalawyer.cn",
                "login_url": "https://alphalawyer.cn/#/login/wechat",
                "api_base": "https://alphalawyer.cn/api",
                "qr_generate_api": "/wechat/qrcode",
                "qr_status_api": "/wechat/qrcode/status",
                "expected_cookies": ["token", "session", "auth"]  # 预期的关键cookies
            },
            "weixin": {
                "base_url": "https://mp.weixin.qq.com",
                "login_url": "https://mp.weixin.qq.com",
                "start_login_api": "/cgi-bin/bizlogin?action=startlogin",
                "qr_api": "/cgi-bin/scanloginqrcode?action=getqrcode",
                "qr_status_api": "/cgi-bin/scanloginqrcode?action=ask",
                "expected_cookies": ["ticket", "token", "lang"]
            }
        }
        
        # 加载已保存的cookies
        self.load_cookies()
        
        logger.info(f"增强版管理员工具已初始化: {target_site}")
        
    async def init_session(self):
        """初始化HTTP会话"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
    def load_cookies(self):
        """从文件加载cookies"""
        try:
            if self.cookies_file.exists():
                with open(self.cookies_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    self.current_cookies = self._clean_cookies(cookies)
                logger.info(f"已从文件加载 {len(self.current_cookies)} 个cookies")
        except Exception as e:
            logger.error(f"加载cookies失败: {e}")
            self.current_cookies = []
            
    def save_cookies(self):
        """保存cookies到文件"""
        try:
            cleaned_cookies = self._clean_cookies(self.current_cookies)
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cleaned_cookies, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(cleaned_cookies)} 个cookies到文件")
        except Exception as e:
            logger.error(f"保存cookies失败: {e}")
            
    def _clean_cookies(self, cookies: List[dict]) -> List[dict]:
        """清理和去重cookies"""
        cleaned = {}
        for cookie in cookies:
            if isinstance(cookie.get('value'), list):
                cookie['value'] = ''.join(cookie['value'])
            key = (cookie.get('name', ''), cookie.get('domain', ''))
            cleaned[key] = cookie
        return list(cleaned.values())

    async def get_admin_key(self) -> str:
        """获取管理员密钥"""
        key_file = self.config_dir / "admin.key"
        
        if key_file.exists():
            self.admin_key = key_file.read_text().strip()
            return self.admin_key
            
        try:
            await self.init_session()
            async with self.session.get(urljoin(self.server_url, "/admin/key")) as response:
                if response.status == 200:
                    data = await response.json()
                    self.admin_key = data["admin_key"]
                    key_file.write_text(self.admin_key)
                    logger.info("已获取并保存管理员密钥")
                    return self.admin_key
                else:
                    raise Exception(f"获取管理员密钥失败: {response.status}")
        except Exception as e:
            logger.error(f"获取管理员密钥失败: {e}")
            raise

    async def init_login_session(self, site_config: dict) -> dict:
        """初始化登录会话 - 参考微信方案第一步"""
        logger.info("步骤1: 初始化登录会话...")
        
        try:
            await self.init_session()
            # 访问主页获取初始cookies和参数
            async with self.session.get(site_config["base_url"]) as response:
                if response.status == 200:
                    logger.info("成功访问主页，获取初始参数")
                    
                    # 模拟微信的ua_id获取
                    initial_cookies = []
                    try:
                        for morsel in response.cookies.values():
                            initial_cookies.append({
                                'name': morsel.key,
                                'value': morsel.value,
                                'domain': morsel.get('domain', ''),
                                'path': morsel.get('path', '/'),
                                'secure': morsel.get('secure', False),
                                'httpOnly': morsel.get('httponly', False)
                            })
                    except Exception as cookie_error:
                        logger.warning(f"处理响应cookies时出错: {cookie_error}")
                        # 如果cookie处理失败，继续但不设置cookies
                        initial_cookies = []
                    
                    return {
                        "status": "success",
                        "cookies": initial_cookies,
                        "session_id": int(time.time() * 1000)  # 模拟微信的sessionid
                    }
                else:
                    raise Exception(f"访问主页失败: {response.status}")
                    
        except Exception as e:
            logger.error(f"初始化登录会话失败: {e}")
            return {"status": "error", "message": str(e)}

    async def start_login_process(self, site_config: dict, session_data: dict) -> dict:
        """启动登录过程 - 参考微信方案第二步"""
        logger.info("步骤2: 启动登录过程...")
        
        try:
            # 构建登录启动请求 - 模拟微信的startlogin
            session_id = session_data.get("session_id", int(time.time() * 1000))
            
            if self.target_site == "weixin":
                # 微信公众号的具体实现
                data = f'userlang=zh_CN&redirect_url=&login_type=3&sessionid={session_id}&token=&lang=zh_CN&f=json&ajax=1'
                headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                
                async with self.session.post(
                    site_config["base_url"] + site_config["start_login_api"],
                    data=data,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        logger.info("成功启动微信登录流程")
                        return {"status": "success", "session_id": session_id}
            else:
                # 通用实现 - 适用于其他网站
                payload = {
                    "session_id": session_id,
                    "login_type": "qr_code",
                    "timestamp": int(time.time() * 1000)
                }
                
                async with self.session.post(
                    site_config["base_url"] + "/api/auth/start",
                    json=payload
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        logger.info("成功启动登录流程")
                        return {"status": "success", "data": data}
                    
        except Exception as e:
            logger.error(f"启动登录过程失败: {e}")
            
        return {"status": "error", "message": "启动登录过程失败"}

    async def generate_qr_code(self, site_config: dict, session_data: dict) -> Tuple[bytes, dict]:
        """生成二维码 - 参考微信方案，支持alphalawyer"""
        logger.info("步骤3: 生成登录二维码...")
        
        try:
            # 构建二维码请求URL - 根据网站类型
            random_param = int(time.time() * 1000)
            
            if self.target_site == "weixin":
                # 微信公众号的二维码获取
                qr_url = f"{site_config['base_url']}{site_config['qr_api']}&random={random_param}"
            elif self.target_site.startswith("alphalawyer"):
                # AlphaLawyer网站的二维码获取
                api_base = site_config.get("api_base", site_config["base_url"])
                qr_endpoint = site_config.get("qr_generate_api", "/wechat/qrcode")
                qr_url = f"{api_base}{qr_endpoint}"
                
                # 尝试多种可能的API调用方式
                qr_urls_to_try = [
                    f"{api_base}{qr_endpoint}?t={random_param}",
                    f"{api_base}{qr_endpoint}",
                    f"{site_config['base_url']}/api{qr_endpoint}",
                    f"{site_config['base_url']}/api/v1{qr_endpoint}",
                    # 基于微信登录页面的可能API端点
                    f"{site_config['base_url']}/api/wechat/getLoginQrCode",
                    f"{site_config['base_url']}/api/auth/wechat/qrcode",
                    f"{site_config['base_url']}/wechat/qrcode",
                ]
            else:
                # 通用二维码生成
                qr_url = f"{site_config['base_url']}/api/auth/qr/generate?session_id={session_data.get('session_id')}&random={random_param}"
                qr_urls_to_try = [qr_url]
            
            # 如果是alphalawyer，尝试多个可能的端点
            if self.target_site.startswith("alphalawyer"):
                for attempt_url in qr_urls_to_try:
                    try:
                        logger.info(f"尝试二维码API: {attempt_url}")
                        async with self.session.get(attempt_url) as response:
                            if response.status == 200:
                                qr_data = await response.read()
                                
                                # 检查是否是图片数据
                                if qr_data.startswith(b'\x89PNG') or qr_data.startswith(b'\xFF\xD8\xFF'):
                                    logger.info(f"成功获取二维码图片: {attempt_url}")
                                    return qr_data, {"status": "success", "qr_url": attempt_url}
                                else:
                                    # 可能是JSON响应
                                    try:
                                        json_data = json.loads(qr_data.decode('utf-8'))
                                        if any(key in json_data for key in ['qr_code', 'qrcode', 'qr_url', 'qrCode']):
                                            logger.info(f"成功获取二维码数据: {attempt_url}")
                                            # 处理不同格式的二维码数据
                                            qr_content = (json_data.get('qr_code') or 
                                                        json_data.get('qrcode') or 
                                                        json_data.get('qr_url') or 
                                                        json_data.get('qrCode'))
                                            
                                            if qr_content.startswith('data:image'):
                                                # Base64编码的图片
                                                qr_bytes = base64.b64decode(qr_content.split(',')[1])
                                                return qr_bytes, {"status": "success", "data": json_data}
                                            elif qr_content.startswith('http'):
                                                # 二维码URL，需要再次请求
                                                async with self.session.get(qr_content) as qr_response:
                                                    if qr_response.status == 200:
                                                        qr_bytes = await qr_response.read()
                                                        return qr_bytes, {"status": "success", "data": json_data}
                                    except Exception as json_error:
                                        logger.debug(f"解析JSON响应失败: {json_error}")
                            else:
                                logger.debug(f"API调用失败: {attempt_url} -> HTTP {response.status}")
                    except Exception as attempt_error:
                        logger.debug(f"尝试 {attempt_url} 失败: {attempt_error}")
                        continue
                
                # 如果所有API都失败，返回错误
                raise Exception("所有可能的二维码API端点都无法访问")
            else:
                # 非alphalawyer网站的处理
                async with self.session.get(qr_url) as response:
                    if response.status == 200:
                        qr_data = await response.read()
                        
                        # 检查是否是图片数据
                        if qr_data.startswith(b'\x89PNG') or qr_data.startswith(b'\xFF\xD8\xFF'):
                            logger.info("成功获取二维码图片")
                            return qr_data, {"status": "success", "qr_url": qr_url}
                        else:
                            # 可能是JSON响应
                            try:
                                json_data = json.loads(qr_data.decode('utf-8'))
                                if 'qr_code' in json_data:
                                    # Base64编码的二维码
                                    qr_bytes = base64.b64decode(json_data['qr_code'])
                                    return qr_bytes, {"status": "success", "data": json_data}
                            except:
                                pass
                                
                    raise Exception(f"无效的二维码响应: {response.status}")
                
        except Exception as e:
            logger.error(f"生成二维码失败: {e}")
            return b'', {"status": "error", "message": str(e)}

    async def check_scan_status(self, site_config: dict, session_data: dict) -> dict:
        """检查扫码状态 - 参考微信方案的状态轮询，支持alphalawyer"""
        try:
            if self.target_site == "weixin":
                # 微信公众号状态检查
                status_url = f"{site_config['base_url']}{site_config['qr_status_api']}&token=&lang=zh_CN&f=json&ajax=1"
            elif self.target_site.startswith("alphalawyer"):
                # AlphaLawyer状态检查 - 尝试多个可能的端点
                api_base = site_config.get("api_base", site_config["base_url"])
                status_endpoint = site_config.get("qr_status_api", "/wechat/qrcode/status")
                
                status_urls_to_try = [
                    f"{api_base}{status_endpoint}",
                    f"{site_config['base_url']}/api{status_endpoint}",
                    f"{site_config['base_url']}/api/wechat/checkLoginStatus",
                    f"{site_config['base_url']}/api/auth/wechat/status",
                    f"{site_config['base_url']}/api/auth/check",
                    f"{site_config['base_url']}/wechat/login/status"
                ]
                
                # 尝试多个可能的状态检查端点
                for status_url in status_urls_to_try:
                    try:
                        async with self.session.get(status_url) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                # 解析alphalawyer的状态响应
                                if 'code' in data or 'status' in data or 'state' in data:
                                    # 常见的状态字段
                                    status_code = data.get('code', data.get('status', data.get('state', -1)))
                                    message = data.get('message', data.get('msg', ''))
                                    
                                    # AlphaLawyer可能的状态映射
                                    if status_code in [0, 200, 'success']:
                                        if 'scan' in message.lower() and 'confirm' not in message.lower():
                                            return {"status": "scanned", "message": self.login_states["scanned"]}
                                        elif 'success' in message.lower() or 'confirm' in message.lower():
                                            return {"status": "confirmed", "message": self.login_states["confirmed"]}
                                        else:
                                            return {"status": "pending", "message": self.login_states["pending"]}
                                    elif status_code in [408, 'timeout', 'expired']:
                                        return {"status": "expired", "message": self.login_states["expired"]}
                                    elif status_code in [1, 'waiting', 'pending']:
                                        return {"status": "pending", "message": self.login_states["pending"]}
                                    else:
                                        return {"status": "error", "message": f"未知状态: {status_code} - {message}"}
                            elif response.status == 404:
                                continue  # 尝试下一个端点
                            else:
                                logger.debug(f"状态检查失败: {status_url} -> HTTP {response.status}")
                    except Exception as e:
                        logger.debug(f"尝试状态检查 {status_url} 失败: {e}")
                        continue
                
                # 如果所有端点都失败，返回通用错误
                return {"status": "error", "message": "无法检查登录状态，可能需要手动检查"}
            else:
                # 通用状态检查
                status_url = f"{site_config['base_url']}/api/auth/qr/status?session_id={session_data.get('session_id')}"
            
            # 非alphalawyer的通用处理
            if not self.target_site.startswith("alphalawyer"):
                async with self.session.get(status_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if self.target_site == "weixin":
                            # 微信状态映射
                            status_code = data.get('status', -1)
                            if status_code == 0:
                                return {"status": "pending", "message": self.login_states["pending"]}
                            elif status_code == 6:
                                return {"status": "scanned", "message": self.login_states["scanned"]}
                            elif status_code == 1:
                                return {"status": "confirmed", "message": self.login_states["confirmed"]}
                            else:
                                return {"status": "error", "message": f"未知状态码: {status_code}"}
                        else:
                            # 通用状态处理
                            status = data.get('status', 'unknown')
                            return {
                                "status": status,
                                "message": self.login_states.get(status, f"状态: {status}"),
                                "data": data
                            }
                    else:
                        return {"status": "error", "message": f"检查状态失败: {response.status}"}
                    
        except Exception as e:
            return {"status": "error", "message": f"检查扫码状态失败: {e}"}

    async def complete_login(self, site_config: dict, session_data: dict) -> dict:
        """完成登录过程 - 获取最终登录cookies"""
        logger.info("步骤4: 完成登录，获取认证cookies...")
        
        try:
            # 获取当前session的所有cookies
            final_cookies = []
            
            # 从session中提取cookies
            try:
                for cookie in self.session.cookie_jar:
                    final_cookies.append({
                        'name': cookie.key,
                        'value': cookie.value,
                        'domain': cookie['domain'] if 'domain' in cookie else '',
                        'path': cookie['path'] if 'path' in cookie else '/',
                        'secure': cookie.get('secure', False),
                        'httpOnly': cookie.get('httponly', False),
                        'sameSite': 'Lax'
                    })
            except Exception as cookie_error:
                logger.warning(f"处理session cookies时出错: {cookie_error}")
                final_cookies = []
            
            if final_cookies:
                self.current_cookies = self._clean_cookies(final_cookies)
                self.save_cookies()
                
                # 同步到服务器
                await self.sync_cookies_to_server()
                
                logger.info(f"登录完成，获取到 {len(self.current_cookies)} 个cookies")
                return {
                    "status": "success",
                    "cookies_count": len(self.current_cookies),
                    "message": "登录成功，cookies已同步到服务器"
                }
            else:
                return {"status": "error", "message": "未获取到有效的登录cookies"}
                
        except Exception as e:
            logger.error(f"完成登录失败: {e}")
            return {"status": "error", "message": str(e)}

    async def sync_cookies_to_server(self):
        """同步cookies到服务器"""
        try:
            if not self.admin_key:
                await self.get_admin_key()
                
            headers = {
                'Content-Type': 'application/json',
                'X-Admin-Key': self.admin_key
            }
            
            async with self.session.post(
                urljoin(self.server_url, "/admin/cookies"),
                json=self.current_cookies,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"成功同步 {len(self.current_cookies)} 个cookies到服务器")
                    return True
                else:
                    logger.error(f"同步cookies失败: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"同步cookies到服务器失败: {e}")
            return False

    async def auto_scan_login(self, target_url: str = None):
        """自动扫码登录 - 完整流程，支持回退模式"""
        site_config = self.site_configs.get(self.target_site)
        if not site_config:
            raise ValueError(f"不支持的网站: {self.target_site}")
            
        if target_url:
            site_config["login_url"] = target_url
            
        logger.info(f"🚀 开始自动扫码登录流程: {site_config['login_url']}")
        print(f"\n{'='*60}")
        print(f"🚀 增强版管理员工具 - 自动扫码登录模式")
        print("="*60)
        print(f"目标网站: {self.target_site}")
        print(f"登录地址: {site_config['login_url']}")
        print("功能说明:")
        print("  ✓ 尝试通过API自动生成二维码")
        print("  ✓ 如果失败则自动切换到手动浏览器模式")
        print("  ✓ 完整日志记录和实时状态监控")
        print("="*60)
        
        # 清理旧cookies
        logger.info("🧹 清理旧cookies以避免误报...")
        print("\n🧹 清理旧cookies以避免误报...")
        await self.clear_old_cookies()
        
        try:
            # 步骤1: 尝试初始化登录会话
            logger.info("📡 尝试自动模式 - 初始化登录会话...")
            print("\n📡 步骤1: 尝试自动模式...")
            session_result = await self.init_login_session(site_config)
            if session_result["status"] != "success":
                logger.warning(f"❌ 自动模式初始化失败: {session_result.get('message')}")
                print(f"❌ 自动模式初始化失败: {session_result.get('message')}")
                print("🔄 自动切换到手动浏览器模式...")
                return await self._fallback_to_manual_mode(site_config)
            
            logger.info("✅ 自动模式初始化成功")
            print("✅ 自动模式初始化成功")
            
            # 步骤2: 启动登录过程
            logger.info("🔑 启动登录过程...")
            print("🔑 步骤2: 启动登录过程...")
            start_result = await self.start_login_process(site_config, session_result)
            if start_result["status"] != "success":
                logger.warning(f"❌ 启动登录过程失败: {start_result.get('message')}")
                print(f"❌ 启动登录过程失败")
                print("🔄 切换到手动浏览器模式...")
                return await self._fallback_to_manual_mode(site_config)
            
            logger.info("✅ 登录过程启动成功")
            print("✅ 登录过程启动成功")
            
            # 步骤3: 生成并显示二维码
            logger.info("📱 生成二维码...")
            print("📱 步骤3: 生成二维码...")
            qr_data, qr_result = await self.generate_qr_code(site_config, session_result)
            if qr_result["status"] != "success":
                logger.warning(f"❌ 生成二维码失败: {qr_result.get('message')}")
                print("❌ 生成二维码失败")
                print("🔄 切换到手动浏览器模式...")
                return await self._fallback_to_manual_mode(site_config)
            
            if qr_data:
                # 显示二维码
                logger.info("✅ 二维码生成成功，启动显示窗口")
                print("✅ 二维码生成成功")
                qr_thread = QRCodeDisplay(qr_data)
                qr_thread.start()
                print("📱 二维码窗口已打开，请使用微信扫码登录...")
            else:
                logger.warning("❌ 二维码数据为空")
                print("❌ 无法显示二维码")
                print("🔄 切换到手动浏览器模式...")
                return await self._fallback_to_manual_mode(site_config)
            
            # 步骤4: 轮询扫码状态
            logger.info("🔍 开始监控扫码状态...")
            print("\n🔍 步骤4: 监控扫码状态...")
            print("="*60)
            print("📱 请使用微信扫描上方二维码")
            print("⏱️ 最多等待2分钟，每3秒检查一次状态")
            print("="*60)
            
            max_attempts = 120  # 最多等待2分钟
            attempt = 0
            
            while attempt < max_attempts and self.running:
                status_result = await self.check_scan_status(site_config, session_result)
                current_status = status_result.get("status", "unknown")
                message = status_result.get("message", "检查状态中...")
                
                # 详细状态记录
                logger.debug(f"扫码状态检查 {attempt + 1}: {current_status} - {message}")
                print(f"\r📊 状态检查 {attempt + 1}/{max_attempts}: {message}", end='', flush=True)
                
                if current_status == "confirmed":
                    logger.info("🎉 登录确认成功！")
                    print("\n🎉 登录确认成功！")
                    break
                elif current_status == "expired":
                    logger.warning("⏰ 二维码已过期")
                    print("\n⏰ 二维码已过期")
                    print("🔄 切换到手动浏览器模式...")
                    return await self._fallback_to_manual_mode(site_config)
                elif current_status == "error":
                    logger.error(f"❌ 登录过程出错: {message}")
                    print(f"\n❌ 登录过程出错: {message}")
                    print("🔄 切换到手动浏览器模式...")
                    return await self._fallback_to_manual_mode(site_config)
                
                await asyncio.sleep(3)  # 每3秒检查一次
                attempt += 1
                
                # 每30秒显示一次详细状态
                if attempt % 10 == 0:
                    logger.info(f"📊 扫码状态监控: 已等待{attempt * 3}秒, 状态: {current_status}")
                    print(f"\n📊 已等待 {attempt * 3} 秒，当前状态: {current_status}")
                    print("💡 提示: 请确保微信已扫码并确认登录")
                    print("", end='')  # 为下一行做准备
            
            if attempt >= max_attempts:
                logger.warning("⏰ 等待超时")
                print("\n⏰ 等待超时，未检测到登录")
                print("🔄 切换到手动浏览器模式...")
                return await self._fallback_to_manual_mode(site_config)
            
            # 步骤5: 完成登录
            logger.info("💾 完成登录流程...")
            print("💾 步骤5: 完成登录流程...")
            complete_result = await self.complete_login(site_config, session_result)
            if complete_result["status"] == "success":
                logger.info(f"🎉 自动登录完全成功！获取{complete_result['cookies_count']}个cookies")
                print(f"\n🎉 自动登录成功！")
                print(f"✅ 已获取 {complete_result['cookies_count']} 个认证cookies")
                print("✅ 所有客户端现在可以使用登录状态")
                return True
            else:
                logger.error(f"❌ 完成登录失败: {complete_result.get('message')}")
                print(f"\n❌ 完成登录失败: {complete_result.get('message')}")
                print("🔄 切换到手动浏览器模式...")
                return await self._fallback_to_manual_mode(site_config)
                
        except Exception as e:
            logger.error(f"自动扫码登录失败: {e}", exc_info=True)
            print(f"\n❌ 自动模式出现异常: {e}")
            print("🔄 自动切换到手动浏览器模式...")
            return await self._fallback_to_manual_mode(site_config)

    async def init_browser(self):
        """初始化浏览器"""
        try:
            logger.info("正在启动浏览器...")
            self.playwright = await async_playwright().start()
            
            # 尝试启动浏览器
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--no-first-run',
                        '--no-service-autorun',
                        '--no-default-browser-check',
                        '--password-store=basic',
                        '--start-maximized'
                    ]
                )
            except Exception as e:
                logger.warning(f"使用默认浏览器失败，尝试系统浏览器: {e}")
                # 尝试系统浏览器路径
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                ]
                
                for path in chrome_paths:
                    if Path(path).exists():
                        logger.info(f"使用系统浏览器: {path}")
                        self.browser = await self.playwright.chromium.launch(
                            headless=False,
                            executable_path=path,
                            args=[
                                '--no-sandbox',
                                '--disable-setuid-sandbox',
                                '--disable-dev-shm-usage',
                                '--disable-gpu',
                                '--start-maximized'
                            ]
                        )
                        break
                
                if not self.browser:
                    raise Exception("未找到可用的浏览器")

            # 创建页面
            context = await self.browser.new_context(no_viewport=True)  # 无固定视口
            self.page = await context.new_page()
            logger.info("浏览器初始化成功")
            
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            await self.cleanup_browser()
            raise

    async def cleanup_browser(self):
        """清理浏览器资源"""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"清理浏览器资源时出错: {e}")
        finally:
            self.page = None
            self.browser = None
            self.playwright = None

    async def get_browser_cookies(self) -> List[dict]:
        """从浏览器获取cookies"""
        if not self.page:
            return []
            
        try:
            # 获取当前页面的所有cookies
            browser_cookies = await self.page.context.cookies()
            
            # 转换格式
            formatted_cookies = []
            for cookie in browser_cookies:
                formatted_cookie = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie['domain'],
                    'path': cookie['path'],
                    'secure': cookie.get('secure', False),
                    'httpOnly': cookie.get('httpOnly', False),
                    'sameSite': cookie.get('sameSite', 'Lax')
                }
                
                # 添加expires字段
                if 'expires' in cookie and cookie['expires'] != -1:
                    formatted_cookie['expires'] = cookie['expires']
                    
                formatted_cookies.append(formatted_cookie)
            
            return formatted_cookies
        except Exception as e:
            logger.error(f"获取浏览器cookies失败: {e}")
            return []

    def _detect_login_success(self, cookies: List[dict]) -> bool:
        """检测是否登录成功"""
        site_config = self.site_configs.get(self.target_site, {})
        expected_cookies = site_config.get("expected_cookies", [])
        
        # 检查是否包含关键cookies
        cookie_names = {cookie['name'].lower() for cookie in cookies}
        
        # alphalawyer特定检查
        if self.target_site == "alphalawyer":
            # 检查是否有认证相关的cookies
            auth_indicators = ['token', 'session', 'auth', 'jwt', 'access', 'user']
            has_auth = any(indicator in name for name in cookie_names for indicator in auth_indicators)
            
            # 检查domain是否为alphalawyer
            has_alpha_domain = any('alphalawyer' in cookie.get('domain', '') for cookie in cookies)
            
            # 检查cookies数量增加（登录通常会增加cookies）
            has_sufficient_cookies = len(cookies) >= 3
            
            logger.info(f"登录检测: 认证cookies={has_auth}, Alpha域名={has_alpha_domain}, "
                       f"足够cookies={has_sufficient_cookies} (共{len(cookies)}个)")
            
            return has_auth or (has_alpha_domain and has_sufficient_cookies)
        
        # 通用检查
        return len(cookies) >= 2 and any(expected in name for name in cookie_names for expected in expected_cookies)

    async def clear_old_cookies(self):
        """清除旧的cookies文件和浏览器cookies，避免误报"""
        logger.info("🧹 清理旧cookies数据...")
        print("🧹 清理旧cookies数据，避免误报...")
        
        try:
            # 清除本地cookies文件
            if self.cookies_file.exists():
                old_size = self.cookies_file.stat().st_size
                self.cookies_file.unlink()
                logger.info(f"已删除旧的cookies文件 ({old_size} bytes)")
                print("✓ 已删除旧的cookies文件")
            
            # 清除内存中的cookies
            self.current_cookies = []
            
            # 如果浏览器已初始化，清除浏览器cookies
            if self.page:
                await self.page.context.clear_cookies()
                logger.info("已清除浏览器cookies")
                print("✓ 已清除浏览器cookies")
                
        except Exception as e:
            logger.warning(f"清理cookies时出现问题: {e}")
            print(f"⚠️ 清理cookies时出现问题: {e}")

    async def _fallback_to_manual_mode(self, site_config: dict):
        """回退到手动模式 - 增强版本，使用浏览器监控"""
        print(f"\n{'='*60}")
        print("🚀 增强版管理员工具 - 手动登录模式 (浏览器集成)")
        print("="*60)
        print("功能说明:")
        print("  ✓ 自动打开浏览器并导航到AlphaLawyer微信登录页面")
        print("  ✓ 实时监控登录状态和cookies变化")
        print("  ✓ 智能检测登录成功并自动保存cookies")
        print("  ✓ 详细日志记录整个登录过程")
        print("\n操作步骤:")
        print("  1. 程序将自动打开浏览器并清理旧cookies")
        print("  2. 自动导航到AlphaLawyer微信登录页面")
        print("  3. 请在浏览器中点击微信登录并扫码")
        print("  4. 登录成功后程序会自动检测并同步cookies")
        print("  5. 按 Ctrl+C 可以停止监控")
        print("="*60)
        
        try:
            # 步骤1: 初始化浏览器
            logger.info("📱 开始初始化浏览器环境...")
            print("\n📱 步骤1: 初始化浏览器环境...")
            await self.init_browser()
            logger.info("✓ 浏览器初始化成功")
            print("✓ 浏览器初始化成功")
            
            # 步骤2: 清理旧cookies
            logger.info("🧹 开始清理旧cookies...")
            print("\n🧹 步骤2: 清理旧cookies...")
            await self.clear_old_cookies()
            
            # 步骤3: 导航到登录页面
            logger.info(f"🌐 开始导航到登录页面: {site_config['login_url']}")
            print(f"\n🌐 步骤3: 导航到登录页面...")
            print(f"目标URL: {site_config['login_url']}")
            
            try:
                response = await self.page.goto(site_config['login_url'], wait_until="networkidle", timeout=30000)
                current_url = self.page.url
                logger.info(f"✓ 页面导航成功: {current_url}")
                print(f"✓ 页面导航成功")
                print(f"  当前URL: {current_url}")
                print(f"  页面标题: {await self.page.title()}")
                
                # 检查是否成功到达登录页面
                if "alphalawyer" in current_url.lower():
                    logger.info("✓ 成功到达AlphaLawyer页面")
                    print("✓ 成功到达AlphaLawyer页面")
                else:
                    logger.warning(f"⚠️ 页面URL异常: {current_url}")
                    print(f"⚠️ 页面URL异常: {current_url}")
                
            except Exception as e:
                logger.error(f"✗ 页面导航失败: {e}")
                print(f"✗ 页面导航失败: {e}")
                return False
            
            # 步骤4: 等待用户操作
            print(f"\n👤 步骤4: 等待用户登录...")
            print("="*60)
            print("🔔 请注意浏览器窗口已打开!")
            print("📋 请在浏览器中完成以下操作:")
            print("  1. 找到并点击 '微信登录' 按钮")
            print("  2. 使用微信扫描二维码")
            print("  3. 在手机上确认登录")
            print("  4. 等待页面跳转到工作台或主页")
            print("="*60)
            print("🔍 程序正在实时监控登录状态...\n")
            
            # 步骤5: 开始监控cookies变化
            logger.info("🔍 开始监控cookies变化...")
            initial_cookies = await self.get_browser_cookies()
            logger.info(f"初始cookies数量: {len(initial_cookies)}")
            print(f"📊 初始状态: {len(initial_cookies)} 个cookies")
            
            last_cookies = initial_cookies
            last_cookie_count = len(initial_cookies)
            check_count = 0
            login_detected = False
            last_url = self.page.url
            
            try:
                while self.running:
                    # 获取当前URL
                    current_url = self.page.url
                    
                    # 检查URL变化
                    if current_url != last_url:
                        logger.info(f"🔄 页面跳转: {last_url} -> {current_url}")
                        print(f"🔄 页面跳转检测到:")
                        print(f"  从: {last_url}")
                        print(f"  到: {current_url}")
                        last_url = current_url
                        
                        # 检查是否跳转到工作台
                        if any(keyword in current_url.lower() for keyword in ['work-plat', 'dashboard', 'main', 'home']):
                            logger.info("✓ 检测到跳转到工作台/主页，可能登录成功")
                            print("✓ 检测到跳转到工作台/主页，可能登录成功!")
                    
                    # 获取当前cookies
                    current_cookies = await self.get_browser_cookies()
                    
                    # 详细记录cookies变化
                    if len(current_cookies) != last_cookie_count:
                        logger.info(f"📊 Cookies数量变化: {last_cookie_count} -> {len(current_cookies)}")
                        print(f"📊 Cookies数量变化: {last_cookie_count} -> {len(current_cookies)}")
                        
                        # 显示新增的cookies
                        if len(current_cookies) > last_cookie_count:
                            last_names = {c['name'] for c in last_cookies}
                            new_cookies = [c for c in current_cookies if c['name'] not in last_names]
                            if new_cookies:
                                logger.info(f"➕ 新增cookies: {[c['name'] for c in new_cookies]}")
                                print(f"➕ 新增cookies: {', '.join([c['name'] for c in new_cookies])}")
                    
                    # 检查cookies变化和登录状态
                    if len(current_cookies) > last_cookie_count or self._detect_login_success(current_cookies):
                        # 检测到潜在的登录状态
                        if not login_detected and self._detect_login_success(current_cookies):
                            login_detected = True
                            logger.info("🎉 登录成功检测!")
                            print(f"\n🎉 登录成功检测!")
                            print(f"✓ 获取到 {len(current_cookies)} 个cookies")
                            
                            # 显示cookies详情
                            auth_cookies = []
                            other_cookies = []
                            for cookie in current_cookies:
                                if any(keyword in cookie['name'].lower() 
                                      for keyword in ['token', 'session', 'auth', 'user', 'jwt', 'access']):
                                    auth_cookies.append(cookie)
                                else:
                                    other_cookies.append(cookie)
                            
                            if auth_cookies:
                                logger.info(f"🔑 认证相关cookies: {[c['name'] for c in auth_cookies]}")
                                print(f"🔑 认证相关cookies ({len(auth_cookies)}个):")
                                for cookie in auth_cookies:
                                    value_preview = cookie['value'][:20] + "..." if len(cookie['value']) > 20 else cookie['value']
                                    print(f"  - {cookie['name']}: {value_preview}")
                                    print(f"    domain: {cookie.get('domain', 'N/A')}, secure: {cookie.get('secure', False)}")
                            
                            if other_cookies:
                                logger.info(f"📋 其他cookies: {[c['name'] for c in other_cookies]}")
                                print(f"📋 其他cookies ({len(other_cookies)}个): {', '.join([c['name'] for c in other_cookies])}")
                            
                            # 清理并保存cookies
                            logger.info("💾 开始保存cookies...")
                            print("\n💾 保存cookies到本地和服务器...")
                            self.current_cookies = self._clean_cookies(current_cookies)
                            self.save_cookies()
                            logger.info(f"✓ 本地保存成功: {self.cookies_file}")
                            print(f"✓ 本地保存成功: {len(self.current_cookies)} 个cookies")
                            
                            # 同步到服务器
                            logger.info("🌐 开始同步到服务器...")
                            if await self.sync_cookies_to_server():
                                logger.info("✓ 服务器同步成功")
                                print("✓ 服务器同步成功")
                                print("✓ 所有客户端现在可以使用登录状态")
                            else:
                                logger.error("✗ 服务器同步失败")
                                print("✗ 服务器同步失败，但本地已保存")
                        
                        last_cookies = current_cookies
                        last_cookie_count = len(current_cookies)
                    
                    check_count += 1
                    
                    # 定期状态报告
                    if check_count % 10 == 0:  # 每30秒显示一次状态
                        current_time = asyncio.get_event_loop().time()
                        status = "✅ 已登录" if login_detected else "⏳ 等待登录"
                        logger.info(f"📊 监控状态报告: {status}, 检查次数: {check_count}, 当前cookies: {len(current_cookies)}")
                        print(f"\n📊 状态报告 ({check_count * 3}秒)")
                        print(f"  登录状态: {status}")
                        print(f"  当前URL: {current_url}")
                        print(f"  Cookies数量: {len(current_cookies)}")
                        print(f"  检查次数: {check_count}")
                        if not login_detected:
                            print("  💡 提示: 请确保在浏览器中完成微信扫码登录")
                    
                    await asyncio.sleep(3)  # 每3秒检查一次
                    
            except KeyboardInterrupt:
                logger.info("用户手动停止监控")
                print("\n🛑 用户停止了cookies监控")
                
            # 最终状态报告
            final_cookies = await self.get_browser_cookies()
            logger.info(f"📋 最终状态: 登录={login_detected}, cookies={len(final_cookies)}")
            print(f"\n📋 最终状态:")
            print(f"  登录检测: {'✅ 成功' if login_detected else '❌ 未检测到'}")
            print(f"  最终cookies: {len(final_cookies)} 个")
            print(f"  本地文件: {self.cookies_file.exists()}")
            
            return login_detected
                
        except Exception as e:
            logger.error(f"手动模式出错: {e}", exc_info=True)
            print(f"\n❌ 手动模式出错: {e}")
            return False
        finally:
            print("\n🔄 清理浏览器资源...")
            await self.cleanup_browser()

    async def cleanup(self):
        """清理资源"""
        self.running = False
        await self.cleanup_browser()
        if self.session and not self.session.closed:
            await self.session.close()

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='增强版管理员工具 - AlphaLawyer微信扫码登录')
    parser.add_argument('--action', choices=['auto-login', 'manual-login', 'cookies'], 
                       default='auto-login', help='要执行的操作')
    parser.add_argument('--site', choices=['alphalawyer', 'weixin'], default='alphalawyer', help='目标网站')
    parser.add_argument('--url', help='自定义登录URL')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    args = parser.parse_args()
    
    # 设置日志级别
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("🔧 调试模式已启用")
    
    # 创建工具实例
    tool = EnhancedAdminTool(target_site=args.site)
    
    # 显示启动信息
    print("="*70)
    print("🚀 增强版管理员工具 - AlphaLawyer微信扫码登录解决方案")
    print("="*70)
    print(f"📋 操作模式: {args.action}")
    print(f"🌐 目标网站: {args.site}")
    print(f"📊 日志级别: {'DEBUG' if args.debug else 'INFO'}")
    print("="*70)
    
    try:
        if args.action == 'auto-login':
            logger.info(f"🚀 启动自动扫码登录: {args.site}")
            print("\n🚀 启动自动扫码登录模式...")
            print("📝 说明: 程序将首先尝试API自动模式，失败时自动切换到浏览器手动模式")
            
            success = await tool.auto_scan_login(args.url)
            
            if success:
                logger.info("🎉 登录流程完全成功")
                print("\n🎉 登录流程完全成功！")
                print("✅ Cookies已保存并同步到服务器")
                print("✅ 所有客户端现在可以使用登录状态")
                print("\n📊 开始持续监控cookies状态...")
                print("💡 程序将定期检查并同步cookies，按 Ctrl+C 停止")
                
                try:
                    monitor_count = 0
                    while tool.running:
                        await asyncio.sleep(30)  # 每30秒检查一次
                        monitor_count += 1
                        
                        # 定期同步cookies
                        if await tool.sync_cookies_to_server():
                            logger.debug(f"✅ 定期同步成功 (第{monitor_count}次)")
                            if monitor_count % 10 == 0:  # 每5分钟显示一次
                                print(f"📊 监控状态: 第{monitor_count}次检查，cookies同步正常")
                        else:
                            logger.warning(f"⚠️ 定期同步失败 (第{monitor_count}次)")
                            print(f"⚠️ 第{monitor_count}次同步失败，cookies可能已过期")
                            
                except KeyboardInterrupt:
                    logger.info("用户停止cookies监控")
                    print("\n🛑 用户停止了cookies监控")
            else:
                logger.error("❌ 登录流程失败")
                print("\n❌ 登录流程失败")
                print("🔍 可能的原因:")
                print("  - 网络连接问题")
                print("  - AlphaLawyer网站问题")
                print("  - 浏览器问题")
                print("  - 用户未完成微信扫码")
                
        elif args.action == 'manual-login':
            logger.info(f"🖥️ 启动手动浏览器登录: {args.site}")
            print("\n🖥️ 启动手动浏览器登录模式...")
            print("📝 说明: 程序将直接打开浏览器，等待您手动完成微信扫码登录")
            
            site_config = tool.site_configs.get(args.site)
            if not site_config:
                print(f"❌ 不支持的网站: {args.site}")
                return
                
            if args.url:
                site_config["login_url"] = args.url
                
            success = await tool._fallback_to_manual_mode(site_config)
            
            if success:
                logger.info("🎉 手动登录成功")
                print("\n🎉 手动登录成功！")
                print("✅ 开始持续监控...")
                
                try:
                    while tool.running:
                        await asyncio.sleep(30)
                        await tool.sync_cookies_to_server()
                except KeyboardInterrupt:
                    print("\n🛑 停止监控")
            else:
                print("\n❌ 手动登录失败")
                
        elif args.action == 'cookies':
            logger.info("📋 显示当前cookies")
            tool.load_cookies()
            if tool.current_cookies:
                print("\n📋 当前保存的cookies:")
                print("="*50)
                
                # 分类显示cookies
                auth_cookies = []
                other_cookies = []
                for cookie in tool.current_cookies:
                    if any(keyword in cookie['name'].lower() 
                          for keyword in ['token', 'session', 'auth', 'user', 'jwt']):
                        auth_cookies.append(cookie)
                    else:
                        other_cookies.append(cookie)
                
                if auth_cookies:
                    print("🔑 认证相关cookies:")
                    for cookie in auth_cookies:
                        value_preview = cookie['value'][:30] + "..." if len(cookie['value']) > 30 else cookie['value']
                        print(f"  {cookie['name']}: {value_preview}")
                        print(f"    domain: {cookie.get('domain')}, secure: {cookie.get('secure')}")
                
                if other_cookies:
                    print(f"\n📋 其他cookies ({len(other_cookies)}个):")
                    for cookie in other_cookies:
                        value_preview = cookie['value'][:20] + "..." if len(cookie['value']) > 20 else cookie['value']
                        print(f"  {cookie['name']}: {value_preview}")
                
                print(f"\n📊 总计: {len(tool.current_cookies)} 个cookies")
                print(f"📁 文件位置: {tool.cookies_file}")
                
                # 完整JSON输出（如果需要）
                if args.debug:
                    print("\n🔧 完整JSON输出:")
                    print(json.dumps(tool.current_cookies, ensure_ascii=False, indent=2))
            else:
                print("\n📭 没有保存的cookies")
                print("💡 请先运行登录操作: python enhanced_admin_tool.py --action auto-login")
                
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        print("\n🛑 程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
        print(f"\n❌ 程序出错: {e}")
        print("\n🔍 请检查:")
        print("  1. 服务器是否已启动")
        print("  2. 网络连接是否正常")
        print("  3. 目标网站是否可访问")
        print("  4. 浏览器是否正确安装")
        
        if args.debug:
            print("\n🔧 调试信息:")
            import traceback
            traceback.print_exc()
        else:
            print("\n💡 可以使用 --debug 参数获取详细错误信息")
            
        print("\n按Enter键退出...")
        try:
            input()
        except:
            pass
    finally:
        logger.info("🧹 清理资源...")
        await tool.cleanup()
        print("🏁 程序已退出")

if __name__ == "__main__":
    asyncio.run(main()) 