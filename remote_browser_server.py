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

from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
import json
import logging
import re
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pathlib import Path
import uvicorn
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import uuid
import os
import secrets
import hashlib
import psutil
import configparser
from logging.handlers import RotatingFileHandler

# 日志配置
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "remote_browser_server.log"
handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[handler, logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- 全局状态管理 ---
class AppState:
    server_state: ServerState
    access_coordinator: AccessCoordinator
    connection_manager: ConnectionManager
    admin_browser_task: Optional[asyncio.Task] = None
    cookie_update_task: Optional[asyncio.Task] = None

app = FastAPI(title="Remote Browser Server")
app.state = AppState()

class ConnectionManager:
    """管理WebSocket连接"""
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_info: Dict[str, Dict] = {}  # 存储客户端详细信息

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        
        # 记录客户端信息
        client_ip = self._get_client_ip(websocket)
        self.client_info[session_id] = {
            "ip_address": client_ip,
            "connect_time": datetime.now(),
            "websocket": websocket
        }
        
        logger.info(f"客户端会话 {session_id[:8]} 已连接 (IP: {client_ip})")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.client_info:
            del self.client_info[session_id]
        logger.info(f"客户端会话 {session_id[:8]} 已断开")
    
    def _get_client_ip(self, websocket: WebSocket) -> str:
        """获取客户端IP地址"""
        try:
            # 优先检查X-Forwarded-For头（代理服务器）
            headers = dict(websocket.headers)
            forwarded_for = headers.get('x-forwarded-for')
            if forwarded_for:
                # 取第一个IP（真实客户端IP）
                return forwarded_for.split(',')[0].strip()
            
            # 检查X-Real-IP头
            real_ip = headers.get('x-real-ip')
            if real_ip:
                return real_ip
            
            # 获取直连IP
            if hasattr(websocket, 'client') and websocket.client:
                return websocket.client.host
            
            return "unknown"
        except Exception as e:
            logger.warning(f"获取客户端IP失败: {e}")
            return "unknown"
    
    def get_client_info(self, session_id: str) -> Dict:
        """获取客户端信息"""
        return self.client_info.get(session_id, {})

    async def send_personal_message(self, message: str, session_id: str):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

class AccessCoordinator:
    """访问协调器 - 实现客户端排队和并发控制"""
    def __init__(self, connection_manager: ConnectionManager, server_state: ServerState):
        self.access_lock = asyncio.Lock()
        self.active_clients: Dict[str, Dict] = {}
        self.waiting_queue: List[Dict] = []
        self.monitoring_task: Optional[asyncio.Task] = None
        self.connection_manager = connection_manager
        self.server_state = server_state
        self.load_config()

    def load_config(self):
        """加载配置"""
        config_section = self.server_state.server_config['server'] if self.server_state.server_config.has_section('server') else None
        
        if config_section:
            self.max_concurrent_clients = config_section.getint('max_concurrent_clients', 2)
            self.heartbeat_interval = config_section.getint('heartbeat_interval', 30)
            self.max_inactive_minutes = config_section.getint('max_inactive_minutes', 10)
        else:
            # 如果配置部分不存在，使用默认值
            self.max_concurrent_clients = 2
            self.heartbeat_interval = 30
            self.max_inactive_minutes = 10
            
        logger.info(f"访问协调器配置加载: max_concurrent_clients={self.max_concurrent_clients}")

    async def start_monitoring(self):
        if self.monitoring_task is None:
            self.monitoring_task = asyncio.create_task(self._monitor_active_client())
            logger.info("📡 开始监控活跃客户端状态")

    async def stop_monitoring(self):
        if self.monitoring_task:
            self.monitoring_task.cancel()
            self.monitoring_task = None
            logger.info("📡 停止监控活跃客户端状态")

    async def request_access(self, client_id: str, priority: int = 0, requested_domains: List[str] = None) -> Dict[str, Any]:
        async with self.access_lock:
            current_time = datetime.now()

            if not requested_domains:
                return await self._traditional_access_request(client_id, priority, current_time)

            logger.info(f"🌐 客户端 {client_id[:8]} 请求域名: {requested_domains}")
            allocation_check = self.server_state.can_allocate_domains(client_id, requested_domains)

            if client_id in self.active_clients and set(requested_domains) == set(self.active_clients[client_id].get("allocated_domains", [])):
                self.active_clients[client_id]["last_activity"] = current_time
                return {"granted": True, "status": "already_active_with_same_domains", "message": "您已经是活跃客户端，域名已分配", "allocated_domains": requested_domains}

            is_in_queue = any(item['client_id'] == client_id for item in self.waiting_queue)

            if is_in_queue and (not allocation_check['can_allocate'] or len(self.active_clients) >= self.max_concurrent_clients):
                return await self._queue_for_domain_access(client_id, priority, current_time, requested_domains, allocation_check)

            if allocation_check['can_allocate'] and len(self.active_clients) < self.max_concurrent_clients:
                if is_in_queue:
                    self.waiting_queue = [item for item in self.waiting_queue if item['client_id'] != client_id]
                
                self.active_clients[client_id] = {"start_time": current_time, "last_activity": current_time, "allocated_domains": requested_domains}
                self.server_state.allocate_domains_to_client(client_id, requested_domains)
                return {"granted": True, "status": "direct_grant_with_domains", "message": "访问权限和域名已分配", "allocated_domains": requested_domains}

            return await self._queue_for_domain_access(client_id, priority, current_time, requested_domains, allocation_check)

    async def _traditional_access_request(self, client_id: str, priority: int, current_time: datetime) -> Dict[str, Any]:
        if client_id in self.active_clients:
            self.active_clients[client_id]["last_activity"] = current_time
            return {"granted": True, "status": "already_active", "message": "您已经是当前活跃客户端"}

        if len(self.active_clients) < self.max_concurrent_clients:
            self.active_clients[client_id] = {"start_time": current_time, "last_activity": current_time}
            return {"granted": True, "status": "direct_grant", "message": "访问权限已分配"}
        
        return await self._add_to_queue(client_id, priority, current_time)

    async def _queue_for_domain_access(self, client_id: str, priority: int, current_time: datetime, requested_domains: List[str], allocation_check: Dict) -> Dict[str, Any]:
        # ... (queueing logic as corrected before)
        position = self._get_client_position(client_id)
        if not any(item['client_id'] == client_id for item in self.waiting_queue):
             self.waiting_queue.append({"client_id": client_id, "request_time": current_time, "priority": priority, "requested_domains": requested_domains})
             # sort queue by priority
             self.waiting_queue.sort(key=lambda x: x['priority'], reverse=True)
             position = self._get_client_position(client_id)

        if not allocation_check['can_allocate'] and allocation_check.get('unavailable_domains'):
            first_unavailable = allocation_check['unavailable_domains'][0]
            reason = f"域名'{first_unavailable['domain']}'不可用({first_unavailable['reason']})"
        elif allocation_check['conflicts']:
            reason = "域名已被占用"
        else:
            reason = "服务器满载"
        
        return {"granted": False, "status": "queued_for_domains", "message": f"已加入等待队列，当前位置：{position}，原因：{reason}", "position": position}

    async def _add_to_queue(self, client_id: str, priority: int, current_time: datetime) -> Dict[str, Any]:
        # ... (queueing logic as corrected before)
        position = self._get_client_position(client_id)
        if not any(item['client_id'] == client_id for item in self.waiting_queue):
             self.waiting_queue.append({"client_id": client_id, "request_time": current_time, "priority": priority})
             self.waiting_queue.sort(key=lambda x: x['priority'], reverse=True)
             position = self._get_client_position(client_id)

        return {"granted": False, "status": "queued", "message": f"已加入等待队列，当前位置：{position}", "position": position}
    
    def _get_client_position(self, client_id: str) -> int:
        for i, item in enumerate(self.waiting_queue):
            if item["client_id"] == client_id:
                return i + 1
        return 0

    async def release_access(self, client_id: str, reason: str = "manual_release"):
        async with self.access_lock:
            if client_id in self.active_clients:
                del self.active_clients[client_id]
                self.server_state.release_domains_from_client(client_id)
                logger.info(f"🔓 客户端 {client_id[:8]} 释放访问权限（原因：{reason}）")
                await self._assign_next_client()

    async def _assign_next_client(self):
        if self.waiting_queue:
            next_in_line = self.waiting_queue.pop(0)
            client_id = next_in_line['client_id']
            # Simplified grant logic for brevity
            await self._grant_access_to_client(next_in_line, next_in_line.get("requested_domains", []))

    async def _grant_access_to_client(self, queue_item: Dict, domains: List[str]):
        client_id = queue_item['client_id']
        self.active_clients[client_id] = {"start_time": datetime.now(), "last_activity": datetime.now(), "allocated_domains": domains}
        if domains:
            self.server_state.allocate_domains_to_client(client_id, domains)
        
        notification = {"type": "access_granted", "message": "您的访问权限已获得批准", "allocated_domains": domains}
        await self.connection_manager.send_personal_message(json.dumps(notification), client_id)
        
    async def _monitor_active_client(self):
        while True:
            await asyncio.sleep(60)
            async with self.access_lock:
                current_time = datetime.now()
                timed_out_clients = []
                for client_id, info in self.active_clients.items():
                    if (current_time - info["last_activity"]).total_seconds() > self.max_inactive_minutes * 60:
                        timed_out_clients.append(client_id)
                
                for client_id in timed_out_clients:
                    logger.warning(f"⏰ 客户端 {client_id[:8]} 超时未响应，自动释放")
                    await self.release_access(client_id, "timeout")

    async def update_activity(self, client_id: str) -> bool:
        async with self.access_lock:
            if client_id in self.active_clients:
                self.active_clients[client_id]["last_activity"] = datetime.now()
                return True
            return False

    async def cleanup_stale_clients(self):
        async with self.access_lock:
            self.active_clients.clear()
            self.waiting_queue.clear()
            self.server_state.domain_allocations.clear()
            logger.info("🧹 已清理所有陈旧的客户端会话和队列")

    async def get_status(self) -> Dict[str, Any]:
        """获取访问协调器状态"""
        async with self.access_lock:
            active_client = None
            active_client_info = {}
            
            if self.active_clients:
                active_client = list(self.active_clients.keys())[0]
                client_info = self.active_clients[active_client]
                current_time = datetime.now()
                usage_time = (current_time - client_info["start_time"]).total_seconds() / 60
                inactive_time = (current_time - client_info["last_activity"]).total_seconds() / 60
                
                active_client_info = {
                    "usage_minutes": round(usage_time, 1),
                    "inactive_minutes": round(inactive_time, 1)
                }
            
            queue_details = []
            for i, item in enumerate(self.waiting_queue):
                current_time = datetime.now()
                wait_time = (current_time - item["request_time"]).total_seconds() / 60
                
                queue_details.append({
                    "position": i + 1,
                    "client_id": item["client_id"],
                    "priority": item.get("priority", 0),
                    "wait_minutes": round(wait_time, 1),
                    "requested_domains": item.get("requested_domains", [])
                })
            
            return {
                "active_client": active_client,
                "active_client_info": active_client_info,
                "active_count": len(self.active_clients),
                "max_concurrent": self.max_concurrent_clients,
                "queue_length": len(self.waiting_queue),
                "queue_details": queue_details
            }

    async def remove_from_queue(self, client_id: str) -> Dict[str, Any]:
        """从等待队列中移除客户端"""
        async with self.access_lock:
            old_length = len(self.waiting_queue)
            self.waiting_queue = [item for item in self.waiting_queue if item["client_id"] != client_id]
            new_length = len(self.waiting_queue)
            
            return {
                "removed": old_length - new_length > 0,
                "old_queue_length": old_length,
                "new_queue_length": new_length
            }

    def set_max_concurrent_clients(self, max_clients: int):
        """设置最大并发客户端数并保存到配置文件"""
        self.max_concurrent_clients = max_clients
        
        # 更新配置文件
        if not self.server_state.server_config.has_section('server'):
            self.server_state.server_config.add_section('server')
        
        self.server_state.server_config.set('server', 'max_concurrent_clients', str(max_clients))
        
        try:
            with self.server_state.config_file.open('w', encoding='utf-8') as f:
                self.server_state.server_config.write(f)
            logger.info(f"最大并发客户端数已更新为 {max_clients} 并保存到配置文件")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

# ... (ServerState class remains largely the same, methods are fine)
class ServerState:
    def __init__(self):
        self.config_file = Path("server_config.ini")
        self.server_config = configparser.ConfigParser() # 初始化为空的ConfigParser
        self._load_server_config() # 加载配置
        self.global_cookies: List[Dict] = []
        self.available_domains: Dict[str, int] = {}
        self.domain_allocations: Dict[str, str] = {} # {domain: client_id}
        self.sessions: Dict[str, Dict] = {}
        self.is_logged_in = False
        self.cookies_last_updated = None  # 添加cookies最后更新时间
        
        # 管理员浏览器相关
        self.playwright = None
        self.admin_browser = None  
        self.admin_context = None
        self.admin_page = None
        self.admin_key = self._load_or_create_admin_key()

    def _load_server_config(self):
        """加载或创建服务器配置文件"""
        try:
            if self.config_file.exists():
                self.server_config.read(self.config_file, encoding='utf-8')
            else:
                # 如果文件不存在，创建默认配置
                self.server_config['server'] = {
                    'max_concurrent_clients': '2',
                    'heartbeat_interval': '30',
                    'max_inactive_minutes': '10'
                }
                with self.config_file.open('w', encoding='utf-8') as f:
                    self.server_config.write(f)
                logger.info(f"已创建默认配置文件: {self.config_file}")
        except Exception as e:
            logger.error(f"加载或创建配置文件失败: {e}")
            # 即使加载失败，也提供一个默认的 'server' section
            if not self.server_config.has_section('server'):
                self.server_config.add_section('server')

    def can_allocate_domains(self, client_id: str, requested_domains: List[str]) -> Dict[str, Any]:
        conflicts = []
        unavailable = []
        can_allocate = True
        for domain in requested_domains:
            if domain in self.domain_allocations and self.domain_allocations[domain] != client_id:
                conflicts.append(domain)
                can_allocate = False
            if domain not in self.available_domains:
                unavailable.append({"domain": domain, "reason": "domain_not_exists"})
                can_allocate = False
        return {"can_allocate": can_allocate, "conflicts": conflicts, "unavailable_domains": unavailable, "available_domains": list(self.available_domains.keys())}
    
    def allocate_domains_to_client(self, client_id: str, domains: List[str]):
        for domain in domains:
            self.domain_allocations[domain] = client_id

    def release_domains_from_client(self, client_id: str):
        released = []
        for domain, owner_id in list(self.domain_allocations.items()):
            if owner_id == client_id:
                del self.domain_allocations[domain]
                released.append(domain)
        return released
    
    async def load_cookies_from_disk(self):
        """从磁盘加载cookies"""
        try:
            cookies_dir = Path("browser_data")
            main_cookies_file = cookies_dir / "shared_cookies.json"
            
            if main_cookies_file.exists():
                with main_cookies_file.open('r', encoding='utf-8') as f:
                    cookies_data = json.load(f)
                
                self.global_cookies = cookies_data.get('cookies', [])
                self.is_logged_in = cookies_data.get('logged_in', False)
                
                # 解析时间戳
                last_updated_str = cookies_data.get('last_updated')
                if last_updated_str:
                    try:
                        self.cookies_last_updated = datetime.fromisoformat(last_updated_str)
                    except:
                        self.cookies_last_updated = None
                
                logger.info(f"✅ 从磁盘加载cookies: {len(self.global_cookies)}个")
                logger.info(f"   登录状态: {self.is_logged_in}")
                logger.info(f"   最后更新: {self.cookies_last_updated}")
                
            else:
                # 如果文件不存在，创建空的cookies
                self.global_cookies = []
                self.is_logged_in = False
                self.cookies_last_updated = None
                logger.info("📁 cookies文件不存在，初始化为空")
            
            self.update_available_domains()
            
        except Exception as e:
            logger.error(f"从磁盘加载cookies失败: {e}")
            # 出错时使用空的cookies
            self.global_cookies = []
            self.is_logged_in = False
            self.cookies_last_updated = None
            self.update_available_domains()

    def update_available_domains(self):
        self.available_domains.clear()
        for cookie in self.global_cookies:
            domain = cookie.get("domain")
            if domain:
                # remove leading dot if exists
                if domain.startswith("."):
                    domain = domain[1:]
                self.available_domains[domain] = self.available_domains.get(domain, 0) + 1
        logger.info(f"更新可用域名: {len(self.available_domains)}个域名")

    def _load_or_create_admin_key(self) -> str:
        """加载或创建管理员密钥"""
        try:
            key_file = Path("browser_data/admin_key.txt")
            key_file.parent.mkdir(exist_ok=True)
            
            if key_file.exists():
                admin_key = key_file.read_text(encoding='utf-8').strip()
            else:
                # 生成新的管理员密钥
                admin_key = secrets.token_urlsafe(32)
                key_file.write_text(admin_key, encoding='utf-8')
                logger.info("已生成新的管理员密钥")
            
            return admin_key
        except Exception as e:
            logger.error(f"管理员密钥处理失败: {e}")
            return "admin123"  # 回退到默认密钥

    def verify_admin_key(self, key: str) -> bool:
        """验证管理员密钥"""
        return key == self.admin_key

    async def save_cookies_to_disk(self):
        """保存cookies到磁盘"""
        try:
            cookies_dir = Path("browser_data")
            cookies_dir.mkdir(exist_ok=True)
            
            # 保存主要cookies文件
            main_cookies_file = cookies_dir / "shared_cookies.json"
            cookies_data = {
                "cookies": self.global_cookies,
                "logged_in": self.is_logged_in,
                "last_updated": self.cookies_last_updated.isoformat() if self.cookies_last_updated else None,
                "count": len(self.global_cookies),
                "available_domains": self.available_domains,
                "timestamp": datetime.now().isoformat()
            }
            
            with main_cookies_file.open('w', encoding='utf-8') as f:
                json.dump(cookies_data, f, ensure_ascii=False, indent=2)
            
            # 按域名分组保存
            cookies_by_domain = {}
            for cookie in self.global_cookies:
                domain = cookie.get('domain', '').lstrip('.')
                if domain:
                    if domain not in cookies_by_domain:
                        cookies_by_domain[domain] = []
                    cookies_by_domain[domain].append(cookie)
            
            # 为每个域名保存单独的文件
            for domain, domain_cookies in cookies_by_domain.items():
                domain_safe = re.sub(r'[^\w\-_.]', '_', domain)
                domain_file = cookies_dir / f"{domain_safe}_cookies.json"
                
                domain_data = {
                    "domain": domain,
                    "cookies": domain_cookies,
                    "count": len(domain_cookies),
                    "timestamp": datetime.now().isoformat()
                }
                
                with domain_file.open('w', encoding='utf-8') as f:
                    json.dump(domain_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 保存 {len(self.global_cookies)} 个cookies到磁盘 ({len(cookies_by_domain)} 个域名)")
            
        except Exception as e:
            logger.error(f"保存cookies失败: {e}")


# --- 辅助函数 ---
async def init_admin_browser():
    """初始化管理员浏览器 - 真实Playwright实现"""
    try:
        server_state = app.state.server_state
        
        if not server_state.playwright:
            logger.info("正在启动Playwright...")
            server_state.playwright = await async_playwright().start()

        if not server_state.admin_browser:
            logger.info("正在启动管理员浏览器...")
            server_state.admin_browser = await server_state.playwright.chromium.launch(
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

        # 创建管理员浏览器上下文 - 用于cookies管理
        if not server_state.admin_context:
            logger.info("正在创建管理员浏览器上下文...")
            server_state.admin_context = await server_state.admin_browser.new_context(
                no_viewport=True
            )
            
            # 创建管理员页面
            server_state.admin_page = await server_state.admin_context.new_page()
            
            # 设置页面事件监听 - 自动检测cookies变化
            server_state.admin_page.on("response", lambda response: asyncio.create_task(handle_admin_response(response)))
            
            logger.info("管理员浏览器上下文创建成功")
            
            # 关键修复：浏览器上下文创建后，立即加载保存的cookies
            await load_saved_cookies_to_browser()

        logger.info("✅ 管理员浏览器初始化完成")
    except Exception as e:
        logger.error(f"管理员浏览器初始化失败: {e}")
        raise

async def load_saved_cookies_to_browser():
    """将保存的cookies加载到管理员浏览器中"""
    try:
        server_state = app.state.server_state
        
        if not server_state.admin_context:
            logger.warning("管理员浏览器上下文未初始化，无法加载cookies")
            return
            
        if not server_state.global_cookies:
            logger.info("没有保存的cookies需要加载到浏览器")
            return
            
        logger.info(f"正在将 {len(server_state.global_cookies)} 个保存的cookies加载到管理员浏览器...")
        
        # 处理cookies格式，确保与Playwright兼容
        cookies_to_load = []
        for cookie in server_state.global_cookies:
            try:
                # 确保cookie格式正确
                if cookie.get('name') and cookie.get('value'):
                    processed_cookie = {
                        'name': str(cookie['name']),
                        'value': str(cookie['value']),
                        'domain': cookie.get('domain', ''),
                        'path': cookie.get('path', '/'),
                        'secure': bool(cookie.get('secure', False)),
                        'httpOnly': bool(cookie.get('httpOnly', False)),
                        'sameSite': cookie.get('sameSite', 'Lax')
                    }
                    
                    # 处理expires
                    if 'expires' in cookie and cookie['expires'] is not None:
                        try:
                            expires = float(cookie['expires'])
                            if expires > 0:
                                processed_cookie['expires'] = expires
                        except (ValueError, TypeError):
                            pass
                    
                    cookies_to_load.append(processed_cookie)
                    logger.debug(f"准备加载cookie: {cookie['name']} (domain: {cookie.get('domain')})")
                    
            except Exception as e:
                logger.warning(f"处理cookie {cookie.get('name', 'unknown')} 时出错: {e}")
        
        # 将cookies添加到浏览器上下文
        if cookies_to_load:
            await server_state.admin_context.add_cookies(cookies_to_load)
            logger.info(f"✅ 已将 {len(cookies_to_load)} 个cookies加载到管理员浏览器")
        else:
            logger.warning("⚠️ 没有有效的cookies可以加载到浏览器")
            
    except Exception as e:
        logger.error(f"加载cookies到浏览器失败: {e}")

async def handle_admin_response(response):
    """处理管理员页面响应，自动检测cookies变化"""
    try:
        # 在关键响应后更新cookies
        critical_keywords = ['login', 'auth', 'session', 'token', 'signin', 'sso', 'oauth']
        if any(keyword in response.url.lower() for keyword in critical_keywords):
            logger.info(f"管理员页面检测到关键响应: {response.url}")
            await asyncio.sleep(0.5)  # 等待cookies设置完成
            await auto_update_cookies_from_admin()
            
    except Exception as e:
        logger.error(f"处理管理员响应时出错: {e}")

async def auto_update_cookies_from_admin():
    """自动从管理员浏览器获取cookies并更新到服务器 - 改进版本"""
    try:
        server_state = app.state.server_state
        
        if not server_state.admin_context:
            logger.warning("管理员浏览器上下文不存在，无法自动更新cookies")
            return
            
        logger.debug("开始自动从管理员浏览器获取cookies...")
        
        # 获取管理员浏览器的cookies
        cookies = await server_state.admin_context.cookies()
        
        # 标准化cookies格式
        standardized_cookies = []
        for cookie in cookies:
            if cookie.get('name') and cookie.get('value'):
                standardized_cookie = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie.get('domain', ''),
                    'path': cookie.get('path', '/'),
                    'secure': cookie.get('secure', False),
                    'httpOnly': cookie.get('httpOnly', False),
                    'sameSite': cookie.get('sameSite', 'Lax')
                }
                
                if 'expires' in cookie and cookie['expires'] != -1:
                    standardized_cookie['expires'] = cookie['expires']
                
                standardized_cookies.append(standardized_cookie)
        
        # 检查cookies是否有变化
        if standardized_cookies != server_state.global_cookies:
            old_count = len(server_state.global_cookies)
            new_count = len(standardized_cookies)
            
            server_state.global_cookies = standardized_cookies
            server_state.cookies_last_updated = datetime.now()
            
            # 检查登录状态
            await check_login_status()
            
            logger.info(f"🔄 管理员自动更新cookies: {old_count} → {new_count} 个")
            
            # 更新可用域名
            server_state.update_available_domains()
            
            # 保存到磁盘
            await server_state.save_cookies_to_disk()
            
            # 通知所有客户端
            await notify_clients_cookies_updated()
        else:
            logger.debug("cookies无变化，跳过更新")
                
    except Exception as e:
        logger.error(f"自动更新cookies失败: {e}")

async def check_login_status():
    """检查登录状态"""
    try:
        server_state = app.state.server_state
        
        # 检查是否有认证相关的cookies
        auth_cookies = ['sessionid', 'token', 'uid', 'sid', 'PHPSESSID', 'JSESSIONID', 'auth', 'login']
        has_auth_cookie = any(
            any(auth_keyword in cookie['name'].lower() for auth_keyword in auth_cookies)
            for cookie in server_state.global_cookies
        )
        
        # 检查当前页面URL是否表明已登录
        is_on_login_page = False
        if server_state.admin_page:
            current_url = server_state.admin_page.url
            login_indicators = ['login', 'signin', 'auth', 'sso']
            is_on_login_page = any(indicator in current_url.lower() for indicator in login_indicators)
        
        # 判断登录状态
        was_logged_in = server_state.is_logged_in
        server_state.is_logged_in = has_auth_cookie and not is_on_login_page
        
        if server_state.is_logged_in and not was_logged_in:
            logger.info("检测到管理员已登录！")
        elif not server_state.is_logged_in and was_logged_in:
            logger.info("检测到管理员已退出登录")
            
    except Exception as e:
        logger.error(f"检查登录状态失败: {e}")

async def notify_clients_cookies_updated():
    """通知所有客户端cookies已更新"""
    try:
        connection_manager = app.state.connection_manager
        server_state = app.state.server_state
        
        message = json.dumps({
            "type": "cookies_updated",
            "timestamp": datetime.now().isoformat(),
            "count": len(server_state.global_cookies),
            "logged_in": server_state.is_logged_in
        })
        
        await connection_manager.broadcast(message)
        logger.info(f"已通知所有客户端cookies更新")
    except Exception as e:
        logger.error(f"通知客户端cookies更新失败: {e}")

async def extract_cookies_from_browser():
    """从管理员浏览器提取最新的cookies - 防卡死版本"""
    try:
        server_state = app.state.server_state
        
        if not server_state.admin_context:
            logger.warning("管理员浏览器上下文不存在，无法提取cookies")
            return
            
        logger.info("正在从管理员浏览器提取最新cookies...")
        
        # 添加超时保护，防止卡死
        try:
            # 设置5秒超时，防止浏览器响应超时导致卡死
            browser_cookies = await asyncio.wait_for(
                server_state.admin_context.cookies(), 
                timeout=5.0
            )
            
            if browser_cookies:
                # 标准化cookies格式
                standardized_cookies = []
                for cookie in browser_cookies:
                    if cookie.get('name') and cookie.get('value'):
                        standardized_cookie = {
                            'name': cookie['name'],
                            'value': cookie['value'],
                            'domain': cookie.get('domain', ''),
                            'path': cookie.get('path', '/'),
                            'secure': cookie.get('secure', False),
                            'httpOnly': cookie.get('httpOnly', False),
                            'sameSite': cookie.get('sameSite', 'Lax')
                        }
                        
                        if 'expires' in cookie and cookie['expires'] != -1:
                            standardized_cookie['expires'] = cookie['expires']
                        
                        standardized_cookies.append(standardized_cookie)
                
                # 更新服务器cookies
                if standardized_cookies != server_state.global_cookies:
                    server_state.global_cookies = standardized_cookies
                    server_state.cookies_last_updated = datetime.now()
                    logger.info(f"✅ 从浏览器提取并更新了 {len(standardized_cookies)} 个cookies")
                else:
                    logger.info("浏览器cookies与服务器cookies一致，无需更新")
                    
            else:
                logger.info("浏览器中没有cookies")
                
        except asyncio.TimeoutError:
            logger.warning("⚠️ 浏览器cookies提取超时(5秒)，跳过提取步骤")
            logger.info("💡 将使用服务器内存中的cookies进行保存")
            
    except Exception as e:
        logger.error(f"从浏览器提取cookies失败: {e}")
        logger.info("💡 将使用服务器内存中的cookies进行保存")


@app.on_event("startup")
async def startup_event():
    print("--> 服务器启动中...")
    app.state.connection_manager = ConnectionManager()
    app.state.server_state = ServerState()
    app.state.access_coordinator = AccessCoordinator(
        connection_manager=app.state.connection_manager,
        server_state=app.state.server_state
    )
    
    print("--> 清理访问协调器状态...")
    await app.state.access_coordinator.cleanup_stale_clients()
    
    print("--> 从磁盘加载cookies...")
    await app.state.server_state.load_cookies_from_disk()
    
    print("--> 初始化管理员浏览器...")
    app.state.admin_browser_task = asyncio.create_task(init_admin_browser())
    
    print("--> 启动访问协调器监控...")
    await app.state.access_coordinator.start_monitoring()
    
    print("--> 服务器启动完成！")
    
    try:
        from server_api_extensions import init_server_manager, admin_router
        init_server_manager(app.state.server_state, app.state.access_coordinator, app.state.connection_manager)
        # 注册管理API路由
        app.include_router(admin_router)
        logger.info("API扩展模块已加载，管理路由已注册")
    except ImportError:
        logger.warning("未找到server_api_extensions模块，部分管理功能不可用")

@app.on_event("shutdown")
async def shutdown_event():
    print("--> 服务器关闭中...")
    
    try:
        # 停止访问协调器监控
        if app.state.access_coordinator:
            await app.state.access_coordinator.stop_monitoring()
        
        # 步骤1: 从浏览器提取最新cookies (带超时保护)
        print("📥 步骤1: 从管理员浏览器提取最新cookies...")
        try:
            await asyncio.wait_for(extract_cookies_from_browser(), timeout=8.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ cookies提取步骤超时，继续执行后续步骤")
        
        # 步骤2: 保存cookies到磁盘 (带超时保护)
        print("💾 步骤2: 保存cookies到磁盘...")
        try:
            await asyncio.wait_for(app.state.server_state.save_cookies_to_disk(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ cookies保存超时，但可能已部分完成")
        
        # 步骤3: 关闭浏览器 (带超时保护)
        print("🌐 步骤3: 关闭管理员浏览器...")
        try:
            if app.state.server_state.admin_browser:
                await asyncio.wait_for(app.state.server_state.admin_browser.close(), timeout=5.0)
            if app.state.server_state.playwright:
                await asyncio.wait_for(app.state.server_state.playwright.stop(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ 浏览器关闭超时，强制终止")
        except Exception as e:
            logger.warning(f"⚠️ 浏览器关闭时出错: {e}")
        
        # 取消后台任务
        if hasattr(app.state, 'admin_browser_task') and app.state.admin_browser_task:
            app.state.admin_browser_task.cancel()
        if hasattr(app.state, 'cookie_update_task') and app.state.cookie_update_task:
            app.state.cookie_update_task.cancel()
            
    except Exception as e:
        logger.error(f"服务器关闭过程中出错: {e}")
    
    print("--> 服务器已关闭")

# --- API Endpoints ---
@app.post("/create_session")
async def create_session(request: Request):
    session_id = str(uuid.uuid4())
    request.app.state.server_state.sessions[session_id] = {"created_at": datetime.now()}
    return {"session_id": session_id}

@app.post("/access/request")
async def request_access_endpoint(request: Request):
    data = await request.json()
    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少session_id")
    result = await request.app.state.access_coordinator.request_access(
        client_id=session_id,
        priority=data.get("priority", 0),
        requested_domains=data.get("domains")
    )
    result['session_id'] = session_id
    return JSONResponse(content=result)

@app.get("/domains")
async def get_domains_info(request: Request):
    """获取域名详细信息列表"""
    server_state = request.app.state.server_state
    access_coordinator = request.app.state.access_coordinator
    
    domains_info = []
    
    # 获取每个域名的cookies数量
    cookies_by_domain = {}
    for cookie in server_state.global_cookies:
        domain = cookie.get('domain', '').lstrip('.')
        if domain:
            cookies_by_domain[domain] = cookies_by_domain.get(domain, 0) + 1
    
    # 构建域名信息列表
    for domain in server_state.available_domains:
        # 检查域名是否被分配
        allocated_to = []
        available = True
        
        async with access_coordinator.access_lock:
            for client_id, client_domains in access_coordinator.active_clients.items():
                if domain in client_domains:
                    allocated_to.append(client_id)
                    available = False
        
        domain_info = {
            "domain": domain,
            "cookie_count": cookies_by_domain.get(domain, 0),
            "available": available,
            "allocated_to": allocated_to
        }
        domains_info.append(domain_info)
    
    return {"domains": domains_info}

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/cookies")
async def get_cookies(request: Request):
    """获取当前cookies信息"""
    server_state = request.app.state.server_state
    return {
        "success": True,
        "cookies": server_state.global_cookies,
        "logged_in": server_state.is_logged_in,
        "last_updated": server_state.cookies_last_updated.isoformat() if server_state.cookies_last_updated else None,
        "count": len(server_state.global_cookies)
    }

@app.get("/access/status")
async def get_access_status(request: Request):
    """获取访问状态信息"""
    coordinator = request.app.state.access_coordinator
    
    async with coordinator.access_lock:
        active_client = None
        if coordinator.active_clients:
            # 获取第一个活跃客户端
            active_client = list(coordinator.active_clients.keys())[0]
        
        queue_details = []
        for i, item in enumerate(coordinator.waiting_queue):
            queue_details.append({
                "position": i + 1,
                "client_id": item["client_id"],
                "priority": item["priority"],
                "request_time": item["request_time"].isoformat(),
                "requested_domains": item.get("requested_domains", [])
            })
        
        return {
            "active_client": active_client,
            "active_count": len(coordinator.active_clients),
            "max_concurrent": coordinator.max_concurrent_clients,
            "queue_length": len(coordinator.waiting_queue),
            "queue_details": queue_details,
            "timestamp": datetime.now().isoformat()
        }

@app.post("/access/release/{session_id}")
async def release_access_endpoint(session_id: str, request: Request):
    """释放访问权限"""
    result = await request.app.state.access_coordinator.release_access(session_id, "manual_release")
    return JSONResponse(content=result)

@app.post("/cookies/domains")
async def get_cookies_for_domains(request: Request):
    """获取指定域名的cookies"""
    try:
        data = await request.json()
        session_id = data.get("session_id")
        requested_domains = data.get("domains", [])
        
        if not session_id:
            raise HTTPException(status_code=400, detail="缺少session_id")
        
        if not requested_domains:
            raise HTTPException(status_code=400, detail="缺少domains")
        
        server_state = request.app.state.server_state
        access_coordinator = request.app.state.access_coordinator
        
        # 验证客户端是否有权限访问这些域名
        async with access_coordinator.access_lock:
            if session_id not in access_coordinator.active_clients:
                raise HTTPException(status_code=403, detail="无访问权限")
            
            client_info = access_coordinator.active_clients[session_id]
            allocated_domains = client_info.get("allocated_domains", [])
            unauthorized_domains = [d for d in requested_domains if d not in allocated_domains]
            
            if unauthorized_domains:
                raise HTTPException(
                    status_code=403, 
                    detail=f"无权限访问域名: {unauthorized_domains}"
                )
        
        # 过滤指定域名的cookies
        domain_cookies = []
        for cookie in server_state.global_cookies:
            cookie_domain = cookie.get('domain', '').lstrip('.')
            if cookie_domain in requested_domains:
                domain_cookies.append(cookie)
        
        return {
            "success": True,
            "cookies": domain_cookies,
            "domains": requested_domains,
            "count": len(domain_cookies)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取cookies失败: {str(e)}")

@app.get("/admin/key")
async def get_admin_key(request: Request):
    """获取管理员密钥"""
    server_state = request.app.state.server_state
    return {"admin_key": server_state.admin_key}

@app.post("/admin/cookies")
async def update_cookies(
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """管理员手动更新cookies"""
    server_state = request.app.state.server_state
    
    # 验证管理员密钥
    if not server_state.verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    try:
        data = await request.json()
        
        # 智能合并cookies
        if 'cookies' in data:
            old_count = len(server_state.global_cookies)
            new_cookies = data['cookies']
            
            # 检查是否为强制覆盖模式
            force_replace = data.get('force_replace', False)
            
            if force_replace:
                # 强制覆盖模式：直接替换所有cookies
                server_state.global_cookies = new_cookies
                logger.info(f"🔧 管理员强制覆盖cookies: {old_count} → {len(new_cookies)} 个")
                final_count = len(new_cookies)
                action_msg = f"已强制覆盖为 {final_count} 个cookies"
            else:
                # 智能合并模式：在原基础上增加新cookies
                existing_cookies = server_state.global_cookies.copy()
                cookie_keys = set()  # 用于去重的key集合
                merged_cookies = []
                
                # 首先添加新的cookies（优先级更高）
                for cookie in new_cookies:
                    cookie_key = f"{cookie.get('name', '')}_{cookie.get('domain', '')}"
                    if cookie_key not in cookie_keys:
                        merged_cookies.append(cookie)
                        cookie_keys.add(cookie_key)
                
                # 然后添加不冲突的原有cookies
                for cookie in existing_cookies:
                    cookie_key = f"{cookie.get('name', '')}_{cookie.get('domain', '')}"
                    if cookie_key not in cookie_keys:
                        merged_cookies.append(cookie)
                        cookie_keys.add(cookie_key)
                
                server_state.global_cookies = merged_cookies
                final_count = len(merged_cookies)
                logger.info(f"🔧 管理员智能合并cookies: 原有{old_count}个 + 新增{len(new_cookies)}个 = 合并后{final_count}个")
                action_msg = f"已智能合并，新增 {len(new_cookies)} 个，总计 {final_count} 个cookies"
            
            server_state.cookies_last_updated = datetime.now()
            
            # 更新登录状态
            if 'logged_in' in data:
                server_state.is_logged_in = data['logged_in']
            else:
                await check_login_status()
            
            # 更新可用域名
            server_state.update_available_domains()
            
            # 保存到磁盘
            await server_state.save_cookies_to_disk()
            
            # 通知客户端
            await notify_clients_cookies_updated()
            
            return {
                "success": True,
                "message": action_msg,
                "old_count": old_count,
                "new_count": final_count,
                "new_cookies_added": len(new_cookies) if not force_replace else final_count,
                "mode": "force_replace" if force_replace else "smart_merge",
                "logged_in": server_state.is_logged_in,
                "available_domains": len(server_state.available_domains)
            }
        else:
            raise HTTPException(status_code=400, detail="缺少cookies数据")
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON数据")
    except Exception as e:
        logger.error(f"管理员更新cookies失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")

@app.post("/admin/navigate")
async def admin_navigate(
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """管理员浏览器导航"""
    server_state = request.app.state.server_state
    
    # 验证管理员密钥
    if not server_state.verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    try:
        data = await request.json()
        url = data.get('url')
        
        if not url:
            raise HTTPException(status_code=400, detail="缺少URL参数")
        
        if not server_state.admin_page:
            raise HTTPException(status_code=503, detail="管理员浏览器未初始化")
        
        # 导航到指定URL
        await server_state.admin_page.goto(url)
        
        logger.info(f"🌐 管理员浏览器导航到: {url}")
        
        return {
            "success": True,
            "message": f"已导航到: {url}",
            "current_url": server_state.admin_page.url
        }
        
    except Exception as e:
        logger.error(f"管理员浏览器导航失败: {e}")
        raise HTTPException(status_code=500, detail=f"导航失败: {str(e)}")
    
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.app.state.connection_manager.connect(websocket, session_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket.app.state.connection_manager.disconnect(session_id)
        await websocket.app.state.access_coordinator.release_access(session_id, "disconnected")

def main():
    print("\n=== Remote Browser Server ===")
    print("监听地址: 0.0.0.0")
    print("监听端口: 8001")
    print("=====================================\n")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")

if __name__ == "__main__":
    main()
