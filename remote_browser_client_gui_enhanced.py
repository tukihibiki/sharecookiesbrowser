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

import asyncio
import json
import logging
import aiohttp
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import websockets
from urllib.parse import urljoin
from playwright.async_api import async_playwright, Browser, Page
import configparser

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedRemoteBrowserClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("增强版远程浏览器客户端")
        self.root.geometry("900x700")
        
        # 配置文件路径
        self.config_file = Path("client_config.ini")
        
        # 客户端配置
        self.server_host = "localhost"
        self.server_port = "8001"
        self.base_url = f"http://{self.server_host}:{self.server_port}"
        self.ws_base_url = f"ws://{self.server_host}:{self.server_port}"
        
        # 客户端状态
        self.session_id: Optional[str] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.has_access = False
        self.allocated_domains: List[str] = []
        self.available_domains: List[Dict] = []
        
        # 浏览器相关
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.browser_initialized = False
        
        # 设置浏览器路径
        self.browser_dir = self._get_browser_dir()
        
        # 任务
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.ws_task: Optional[asyncio.Task] = None
        self.status_update_task: Optional[asyncio.Task] = None
        self.browser_monitor_task: Optional[asyncio.Task] = None
        self.access_monitor_task: Optional[asyncio.Task] = None  # 独立的权限监控任务
        
        # 创建UI
        self.create_widgets()
        
        # 加载配置
        self.load_config()
        
        # 启动异步事件循环
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.loop_thread.start()
        
        logger.info("增强版客户端GUI初始化完成")

    def _ensure_www_prefix(self, domain: str) -> str:
        """确保域名包含www前缀以便正确导航"""
        if not domain:
            return domain
        
        # 移除协议前缀（如果存在）
        original_domain = domain
        if domain.startswith(('http://', 'https://')):
            protocol = 'https://' if domain.startswith('https://') else 'http://'
            domain = domain[len(protocol):]
        else:
            protocol = 'https://'
        
        # 检查是否已经有www前缀
        if not domain.startswith('www.'):
            # 检查是否是顶级域名（不是子域名）
            parts = domain.split('.')
            if len(parts) >= 2:  # 至少有域名和顶级域名
                # 如果第一部分不是已知的子域名前缀，添加www
                common_subdomains = {'m', 'mobile', 'api', 'admin', 'blog', 'shop', 'mail', 'ftp', 
                                   'cdn', 'img', 'static', 'media', 'news', 'support', 'help'}
                if parts[0].lower() not in common_subdomains:
                    domain = f"www.{domain}"
                    self.log_message(f"🔧 自动为域名 {original_domain} 添加www前缀: {domain}")
        
        final_url = f"{protocol}{domain}"
        return final_url

    def _get_browser_dir(self) -> str:
        """获取浏览器目录路径"""
        import sys
        
        if getattr(sys, 'frozen', False):
            app_dir = Path(sys.executable).parent.absolute()
        else:
            app_dir = Path(__file__).parent.absolute()
        
        browser_dir = app_dir / 'browser'
        browser_dir.mkdir(exist_ok=True)
        return str(browser_dir)

    def _run_async_loop(self):
        """在独立线程中运行异步事件循环"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def create_widgets(self):
        """创建GUI组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
        # 服务器配置区域
        config_frame = ttk.LabelFrame(main_frame, text="服务器配置", padding="5")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        config_frame.columnconfigure(1, weight=1)
        config_frame.columnconfigure(3, weight=1)
        
        ttk.Label(config_frame, text="服务器地址:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.host_var = tk.StringVar(value=self.server_host)
        self.host_entry = ttk.Entry(config_frame, textvariable=self.host_var, width=15)
        self.host_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        ttk.Label(config_frame, text="端口:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.port_var = tk.StringVar(value=self.server_port)
        self.port_entry = ttk.Entry(config_frame, textvariable=self.port_var, width=8)
        self.port_entry.grid(row=0, column=3, sticky=tk.W, padx=(0, 10))
        
        self.save_config_btn = ttk.Button(config_frame, text="保存配置", command=self.save_config)
        self.save_config_btn.grid(row=0, column=4, padx=(5, 0))
        
        # 状态区域
        status_frame = ttk.LabelFrame(main_frame, text="连接状态", padding="5")
        status_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        status_frame.columnconfigure(1, weight=1)
        
        ttk.Label(status_frame, text="状态:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.status_var = tk.StringVar(value="未连接")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="red")
        self.status_label.grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(status_frame, text="会话ID:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        self.session_var = tk.StringVar(value="无")
        ttk.Label(status_frame, textvariable=self.session_var).grid(row=1, column=1, sticky=tk.W)
        
        # 域名选择区域
        domain_frame = ttk.LabelFrame(main_frame, text="域名选择", padding="5")
        domain_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        domain_frame.columnconfigure(0, weight=1)
        
        # 域名列表
        self.domain_listbox = tk.Listbox(domain_frame, selectmode=tk.MULTIPLE, height=6)
        self.domain_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        domain_scrollbar = ttk.Scrollbar(domain_frame, orient=tk.VERTICAL, command=self.domain_listbox.yview)
        domain_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.domain_listbox.config(yscrollcommand=domain_scrollbar.set)
        
        # 域名控制按钮
        domain_btn_frame = ttk.Frame(domain_frame)
        domain_btn_frame.grid(row=1, column=0, columnspan=2, pady=(5, 0))
        
        self.refresh_domains_btn = ttk.Button(domain_btn_frame, text="刷新域名", command=self.refresh_domains)
        self.refresh_domains_btn.grid(row=0, column=0, padx=(0, 5))
        
        self.select_all_btn = ttk.Button(domain_btn_frame, text="全选", command=self.select_all_domains)
        self.select_all_btn.grid(row=0, column=1, padx=(0, 5))
        
        self.clear_selection_btn = ttk.Button(domain_btn_frame, text="清除选择", command=self.clear_domain_selection)
        self.clear_selection_btn.grid(row=0, column=2, padx=(0, 5))
        
        # 控制按钮区域
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        
        self.connect_btn = ttk.Button(control_frame, text="连接服务器", command=self.connect_to_server, state=tk.NORMAL)
        self.connect_btn.grid(row=0, column=0, padx=(0, 5))
        
        self.request_access_btn = ttk.Button(control_frame, text="请求访问权限", command=self.request_access, state=tk.DISABLED)
        self.request_access_btn.grid(row=0, column=1, padx=(0, 5))
        
        self.release_access_btn = ttk.Button(control_frame, text="释放访问权限", command=self.release_access, state=tk.DISABLED)
        self.release_access_btn.grid(row=0, column=2, padx=(0, 5))
        
        self.open_browser_btn = ttk.Button(control_frame, text="手动打开浏览器", command=self.open_browser, state=tk.DISABLED)
        self.open_browser_btn.grid(row=0, column=3, padx=(0, 5))
        
        self.disconnect_btn = ttk.Button(control_frame, text="断开连接", command=self.disconnect_from_server, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=4)
        
        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log_message(self, message: str):
        """在GUI中显示日志信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        def update_log():
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)
        
        self.root.after(0, update_log)
        logger.info(message)

    def update_status(self, status: str, color: str = "black"):
        """更新状态显示"""
        def update():
            self.status_var.set(status)
            self.status_label.config(foreground=color)
        
        self.root.after(0, update)

    def update_session_id(self, session_id: str):
        """更新会话ID显示"""
        self.root.after(0, lambda: self.session_var.set(session_id))

    def update_buttons_state(self):
        """更新按钮状态"""
        def update():
            if self.connected:
                self.connect_btn.config(state=tk.DISABLED)
                self.disconnect_btn.config(state=tk.NORMAL)
                self.request_access_btn.config(state=tk.NORMAL if not self.has_access else tk.DISABLED)
                self.release_access_btn.config(state=tk.NORMAL if self.has_access else tk.DISABLED)
                self.open_browser_btn.config(state=tk.NORMAL if self.has_access else tk.DISABLED)
            else:
                self.connect_btn.config(state=tk.NORMAL)
                self.disconnect_btn.config(state=tk.DISABLED)
                self.request_access_btn.config(state=tk.DISABLED)
                self.release_access_btn.config(state=tk.DISABLED)
                self.open_browser_btn.config(state=tk.DISABLED)
        
        self.root.after(0, update)

    def load_config(self):
        """加载配置文件"""
        try:
            if self.config_file.exists():
                config = configparser.ConfigParser()
                config.read(self.config_file, encoding='utf-8')
                
                if 'SERVER' in config:
                    self.server_host = config['SERVER'].get('host', 'localhost')
                    self.server_port = config['SERVER'].get('port', '8001')
                    
                    self.host_var.set(self.server_host)
                    self.port_var.set(self.server_port)
                    
                    self.update_server_config()
                    
                    self.log_message(f"已加载配置: {self.server_host}:{self.server_port}")
        except Exception as e:
            self.log_message(f"加载配置失败: {str(e)}")

    def save_config(self):
        """保存配置文件"""
        try:
            config = configparser.ConfigParser()
            config['SERVER'] = {
                'host': self.host_var.get(),
                'port': self.port_var.get()
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                config.write(f)
            
            # 更新内部配置
            self.server_host = self.host_var.get()
            self.server_port = self.port_var.get()
            self.update_server_config()
            
            self.log_message(f"配置已保存: {self.server_host}:{self.server_port}")
            messagebox.showinfo("配置保存", "配置已成功保存！")
        except Exception as e:
            error_msg = f"保存配置失败: {str(e)}"
            self.log_message(error_msg)
            messagebox.showerror("保存失败", error_msg)

    def update_server_config(self):
        """更新服务器配置"""
        self.base_url = f"http://{self.server_host}:{self.server_port}"
        self.ws_base_url = f"ws://{self.server_host}:{self.server_port}"

    def refresh_domains(self):
        """刷新域名列表"""
        def run_refresh():
            asyncio.run_coroutine_threadsafe(self._refresh_domains(), self.loop)
        
        threading.Thread(target=run_refresh, daemon=True).start()

    async def _refresh_domains(self):
        """异步刷新域名列表"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/domains") as response:
                    if response.status == 200:
                        data = await response.json()
                        self.available_domains = data['domains']
                        
                        def update_list():
                            self.domain_listbox.delete(0, tk.END)
                            for domain_info in self.available_domains:
                                domain = domain_info['domain']
                                cookie_count = domain_info['cookie_count']
                                available = domain_info['available']
                                allocated_to = domain_info.get('allocated_to', [])
                                
                                status = "可用" if available else f"占用({','.join(allocated_to)})"
                                display_text = f"{domain} ({cookie_count}个cookies) - {status}"
                                
                                self.domain_listbox.insert(tk.END, display_text)
                                
                                # 如果域名不可用，设置不同颜色
                                if not available:
                                    self.domain_listbox.itemconfig(tk.END, fg='gray')
                        
                        self.root.after(0, update_list)
                        self.log_message(f"已刷新域名列表: {len(self.available_domains)}个域名")
                    else:
                        self.log_message(f"获取域名列表失败: HTTP {response.status}")
        except Exception as e:
            self.log_message(f"刷新域名列表失败: {str(e)}")

    def select_all_domains(self):
        """选择所有可用域名"""
        self.domain_listbox.selection_clear(0, tk.END)
        for i, domain_info in enumerate(self.available_domains):
            if domain_info['available']:
                self.domain_listbox.selection_set(i)

    def clear_domain_selection(self):
        """清除域名选择"""
        self.domain_listbox.selection_clear(0, tk.END)

    def get_selected_domains(self) -> List[str]:
        """获取选中的域名"""
        selected_indices = self.domain_listbox.curselection()
        selected_domains = []
        
        for index in selected_indices:
            if index < len(self.available_domains):
                domain_info = self.available_domains[index]
                if domain_info['available']:  # 只添加可用的域名
                    selected_domains.append(domain_info['domain'])
        
        return selected_domains

    def connect_to_server(self):
        """连接到服务器"""
        def run_connect():
            asyncio.run_coroutine_threadsafe(self._connect_to_server(), self.loop)
        
        threading.Thread(target=run_connect, daemon=True).start()

    async def _connect_to_server(self):
        """异步连接到服务器"""
        try:
            self.log_message(f"正在连接到服务器 {self.base_url}...")
            
            # 测试HTTP连接
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status != 200:
                        raise Exception(f"服务器健康检查失败: HTTP {response.status}")
            
            self.connected = True
            self.update_status("已连接", "green")
            self.update_buttons_state()
            self.log_message("已成功连接到服务器")
            
            # 自动刷新域名列表
            await self._refresh_domains()
            
        except Exception as e:
            self.log_message(f"连接服务器失败: {str(e)}")
            self.update_status(f"连接失败: {str(e)}", "red")

    def request_access(self):
        """请求访问权限"""
        def run_request():
            asyncio.run_coroutine_threadsafe(self._request_access(), self.loop)
        
        threading.Thread(target=run_request, daemon=True).start()

    async def _create_session(self):
        """创建新的会话"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/create_session") as response:
                    if response.status == 200:
                        result = await response.json()
                        self.session_id = result['session_id']
                        self.update_session_id(self.session_id)
                        self.log_message(f"已创建新会话: {self.session_id[:8]}...")
                    else:
                        raise Exception(f"创建会话失败: HTTP {response.status}")
        except Exception as e:
            raise Exception(f"创建会话失败: {str(e)}")

    async def _request_access(self):
        """异步请求访问权限"""
        try:
            selected_domains = self.get_selected_domains()
            
            if not selected_domains:
                self.log_message("请先选择需要的域名")
                return
            
            self.log_message(f"正在请求访问权限，选择域名: {selected_domains}")
            
            # 如果没有session_id，先创建一个
            if not self.session_id:
                await self._create_session()
            
            request_data = {
                "session_id": self.session_id,
                "domains": selected_domains,
                "priority": 0
            }
            
            self.log_message(f"使用会话ID: {self.session_id[:8]}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/access/request", json=request_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.session_id = result['session_id']
                        self.update_session_id(self.session_id)
                        
                        if result['granted']:
                            self.has_access = True
                            self.allocated_domains = result.get('allocated_domains', [])
                            self.update_status("已获得访问权限", "green")
                            self.log_message(f"✅ 已获得访问权限，分配域名: {self.allocated_domains}")
                            
                            # 启动WebSocket连接
                            await self._connect_websocket()
                            
                            # 启动心跳
                            await self._start_heartbeat()
                            
                            # 启动独立的权限监控任务
                            await self._start_access_monitor()
                            
                            # 自动启动浏览器并导航到对应网页
                            await self._auto_open_browser()
                            
                        else:
                            self.update_status(f"排队中 (位置: {result.get('position', 'N/A')})", "orange")
                            self.log_message(f"⏳ 已加入等待队列，位置: {result.get('position', 'N/A')}")
                            self.log_message(f"排队原因: {result.get('message', 'N/A')}")
                            
                            # 启动WebSocket连接监听队列状态
                            await self._connect_websocket()
                        
                        self.update_buttons_state()
                    else:
                        error_msg = f"请求访问权限失败: HTTP {response.status}"
                        self.log_message(error_msg)
                        self.update_status(error_msg, "red")
        except Exception as e:
            error_msg = f"请求访问权限失败: {str(e)}"
            self.log_message(error_msg)
            self.update_status(error_msg, "red")

    async def _connect_websocket(self):
        """连接WebSocket"""
        try:
            if self.session_id:
                ws_url = f"{self.ws_base_url}/ws/{self.session_id}"
                self.ws = await websockets.connect(ws_url)
                self.ws_task = asyncio.create_task(self._listen_websocket())
                self.log_message("WebSocket连接已建立")
        except Exception as e:
            self.log_message(f"WebSocket连接失败: {str(e)}")

    async def _listen_websocket(self):
        """监听WebSocket消息"""
        try:
            while self.ws and not self.ws.closed:
                message = await self.ws.recv()
                data = json.loads(message)
                await self._handle_websocket_message(data)
        except websockets.exceptions.ConnectionClosed:
            self.log_message("WebSocket连接已关闭")
        except Exception as e:
            self.log_message(f"WebSocket监听出错: {str(e)}")

    async def _handle_websocket_message(self, data: Dict):
        """处理WebSocket消息"""
        message_type = data.get('type')
        
        if message_type == "access_granted" or message_type == "access_granted_with_domains":
            self.has_access = True
            self.allocated_domains = data.get('allocated_domains', [])
            self.update_status("已获得访问权限", "green")
            self.log_message(f"✅ 已获得访问权限，分配域名: {self.allocated_domains}")
            self.update_buttons_state()
            
            # 启动心跳
            await self._start_heartbeat()
            
            # 启动独立的权限监控任务
            await self._start_access_monitor()
            
            # 自动启动浏览器并导航到对应网页
            await self._auto_open_browser()
            
        elif message_type == "access_revoked":
            self.has_access = False
            self.allocated_domains = []
            self.update_status("访问权限已被撤销", "red")
            self.log_message(f"❌ 访问权限已被撤销: {data.get('message', '')}")
            self.update_buttons_state()
            
        elif message_type == "timeout_warning":
            self.log_message(f"⚠️ 超时警告: {data.get('message', '')}")
            
        elif message_type == "cookies_updated":
            self.log_message(f"🔄 服务器cookies已更新: {data.get('count', 0)}个")

    async def _start_heartbeat(self):
        """启动心跳"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _start_access_monitor(self):
        """启动独立的权限监控任务"""
        if self.access_monitor_task:
            self.access_monitor_task.cancel()
        
        self.access_monitor_task = asyncio.create_task(self._access_monitor_loop())

    async def _heartbeat_loop(self):
        """心跳循环"""
        self.log_message("💓 开始心跳监控（30秒间隔）")
        try:
            while self.has_access and self.session_id:
                await asyncio.sleep(30)  # 30秒心跳间隔
                
                # 如果浏览器已关闭但权限未释放，触发释放
                if self.has_access and not self.browser_initialized:
                    self.log_message("💓 心跳检测到浏览器已关闭但权限未释放，触发自动释放")
                    await self._on_browser_closed()
                    break
                
                # 额外检查：如果有权限但浏览器对象为空，也触发释放
                if self.has_access and (not self.browser or not self.page):
                    self.log_message("💓 心跳检测到浏览器对象为空但权限未释放，触发自动释放")
                    await self._on_browser_closed()
                    break
                
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                        async with session.post(f"{self.base_url}/access/heartbeat/{self.session_id}") as response:
                            if response.status != 200:
                                self.log_message("💓 心跳失败，可能失去访问权限")
                                # 心跳失败时检查浏览器状态
                                if self.browser_initialized and self.browser and self.page:
                                    try:
                                        await self.page.evaluate("() => true")
                                    except:
                                        self.log_message("💓 心跳失败同时检测到浏览器已关闭")
                                        await self._on_browser_closed()
                                # 心跳失败时继续运行，不立即退出（可能只是临时网络问题）
                                self.log_message("💓 心跳失败，但继续监控...")
                                continue  # 改为continue而不是break
                except Exception as e:
                    self.log_message(f"💓 心跳请求出错: {str(e)}，继续监控...")
                    continue  # 改为continue而不是break
        except asyncio.CancelledError:
            self.log_message("💓 心跳任务已取消")
        except Exception as e:
            self.log_message(f"💓 心跳出错: {str(e)}")
        
        self.log_message("💓 心跳监控已停止")

    async def _access_monitor_loop(self):
        """独立的权限监控循环 - 专门监控浏览器关闭状态"""
        self.log_message("🛡️ 开始独立权限监控（每5秒检查一次）")
        try:
            while self.has_access and self.session_id:
                await asyncio.sleep(5)  # 每5秒检查一次
                
                # 如果有访问权限，检查浏览器状态
                if self.has_access:
                    # 检查1：浏览器初始化状态与权限状态不一致
                    if not self.browser_initialized:
                        self.log_message("🛡️ 权限监控检测到浏览器未初始化但拥有权限，触发释放")
                        await self._on_browser_closed()
                        break
                    
                    # 检查2：浏览器对象为空
                    if not self.browser or not self.page:
                        self.log_message("🛡️ 权限监控检测到浏览器对象为空，触发释放")
                        await self._on_browser_closed()
                        break
                    
                    # 检查3：浏览器是否仍然可用
                    try:
                        await asyncio.wait_for(self.page.evaluate("() => true"), timeout=2.0)
                    except asyncio.TimeoutError:
                        self.log_message("🛡️ 权限监控检测到浏览器响应超时，触发释放")
                        await self._on_browser_closed()
                        break
                    except Exception as e:
                        if "Target page, context or browser has been closed" in str(e) or "Browser has been closed" in str(e):
                            self.log_message("🛡️ 权限监控检测到浏览器已关闭，触发释放")
                        else:
                            self.log_message(f"🛡️ 权限监控检测到浏览器异常: {str(e)}，触发释放")
                        await self._on_browser_closed()
                        break
                
        except asyncio.CancelledError:
            self.log_message("🛡️ 权限监控任务已取消")
        except Exception as e:
            self.log_message(f"🛡️ 权限监控出错: {str(e)}")
        
        self.log_message("🛡️ 独立权限监控已停止")

    def release_access(self):
        """释放访问权限"""
        def run_release():
            asyncio.run_coroutine_threadsafe(self._release_access(), self.loop)
        
        threading.Thread(target=run_release, daemon=True).start()

    async def _release_access(self):
        """异步释放访问权限"""
        try:
            if not self.session_id:
                return
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/access/release/{self.session_id}") as response:
                    if response.status == 200:
                        result = await response.json()
                        self.has_access = False
                        self.allocated_domains = []
                        self.update_status("已释放访问权限", "blue")
                        self.log_message("✅ 已释放访问权限")
                        self.update_buttons_state()
                        
                        # 停止心跳
                        if self.heartbeat_task:
                            self.heartbeat_task.cancel()
                            
                        # 停止浏览器监控任务
                        if self.browser_monitor_task:
                            self.browser_monitor_task.cancel()
                            self.browser_monitor_task = None
                            self.log_message("🔄 已停止浏览器监控任务")
                        
                        # 停止独立权限监控任务
                        if self.access_monitor_task:
                            self.access_monitor_task.cancel()
                            self.access_monitor_task = None
                            self.log_message("🔄 已停止独立权限监控任务")
                            
                        # 关闭浏览器以释放资源
                        if self.browser:
                            try:
                                await self.browser.close()
                                self.browser = None
                                self.page = None
                                self.browser_initialized = False
                                self.log_message("🔄 浏览器已关闭，释放资源")
                            except Exception as e:
                                self.log_message(f"关闭浏览器时出错: {str(e)}")
                    else:
                        self.log_message(f"释放访问权限失败: HTTP {response.status}")
        except Exception as e:
            self.log_message(f"释放访问权限失败: {str(e)}")

    async def _auto_open_browser(self):
        """自动启动浏览器并导航到对应网页"""
        try:
            if not self.has_access or not self.allocated_domains:
                self.log_message("无法自动启动浏览器：缺少访问权限或域名分配")
                return
            
            # 获取分配域名的cookies
            self.log_message(f"正在获取域名 {self.allocated_domains} 的cookies...")
            
            cookies_data = {
                "session_id": self.session_id,
                "domains": self.allocated_domains
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/cookies/domains", json=cookies_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        cookies = result['cookies']
                        
                        self.log_message(f"已获取 {len(cookies)} 个cookies，正在启动浏览器...")
                        
                        # 初始化浏览器
                        await self._init_local_browser()
                        
                        # 应用cookies
                        await self._apply_cookies_to_browser(cookies)
                        
                        # 导航到第一个域名
                        if self.allocated_domains:
                            first_domain = self.allocated_domains[0]
                            target_url = self._ensure_www_prefix(first_domain)
                            await self.page.goto(target_url)
                            self.log_message(f"🌐 浏览器已打开并导航到 {target_url}")
                            self.log_message(f"✅ 自动启动完成，可以开始使用浏览器")
                    else:
                        self.log_message(f"获取cookies失败: HTTP {response.status}")
        except Exception as e:
            self.log_message(f"自动启动浏览器失败: {str(e)}")

    def open_browser(self):
        """手动打开浏览器"""
        def run_open():
            asyncio.run_coroutine_threadsafe(self._open_browser(), self.loop)
        
        threading.Thread(target=run_open, daemon=True).start()

    async def _open_browser(self):
        """异步打开浏览器"""
        try:
            if not self.has_access or not self.allocated_domains:
                self.log_message("需要先获得访问权限和域名分配")
                return
            
            # 获取分配域名的cookies
            self.log_message(f"正在获取域名 {self.allocated_domains} 的cookies...")
            
            cookies_data = {
                "session_id": self.session_id,
                "domains": self.allocated_domains
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/cookies/domains", json=cookies_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        cookies = result['cookies']
                        
                        self.log_message(f"已获取 {len(cookies)} 个cookies，正在启动浏览器...")
                        
                        # 初始化浏览器
                        await self._init_local_browser()
                        
                        # 应用cookies
                        await self._apply_cookies_to_browser(cookies)
                        
                        # 导航到第一个域名
                        if self.allocated_domains:
                            first_domain = self.allocated_domains[0]
                            target_url = self._ensure_www_prefix(first_domain)
                            await self.page.goto(target_url)
                            self.log_message(f"浏览器已打开并导航到 {target_url}")
                    else:
                        self.log_message(f"获取cookies失败: HTTP {response.status}")
        except Exception as e:
            self.log_message(f"打开浏览器失败: {str(e)}")

    async def _init_local_browser(self):
        """初始化本地浏览器"""
        # 检查浏览器是否真的可用
        if self.browser_initialized and self.browser and self.page:
            try:
                # 测试浏览器是否仍然可用
                await self.page.evaluate("() => true")
                return
            except Exception:
                # 浏览器已经关闭或不可用，需要重新初始化
                self.log_message("检测到浏览器已关闭，正在重新初始化...")
                self.browser_initialized = False
                self.browser = None
                self.page = None
        
        try:
            self.log_message("正在启动本地浏览器...")
            if self.playwright:
                try:
                    await self.playwright.stop()
                except:
                    pass
            self.playwright = await async_playwright().start()
            
            # 检查自定义浏览器
            browser_dir = Path(self.browser_dir)
            custom_browser_paths = [
                browser_dir / "chrome.exe",
                browser_dir / "msedge.exe", 
                browser_dir / "chromium.exe"
            ]
            
            executable_path = None
            for path in custom_browser_paths:
                if path.exists():
                    executable_path = str(path)
                    break
            
            # 启动浏览器
            if executable_path:
                self.browser = await self.playwright.chromium.launch(
                    executable_path=executable_path,
                    headless=False,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--start-maximized']
                )
            else:
                self.browser = await self.playwright.chromium.launch(
                    headless=False,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--start-maximized']
                )
            
            # 创建页面
            context = await self.browser.new_context(no_viewport=True)
            self.page = await context.new_page()
            
            # 监听浏览器关闭事件
            self.browser.on('disconnected', lambda: asyncio.create_task(self._on_browser_closed()))
            
            self.browser_initialized = True
            self.log_message("✅ 本地浏览器启动完成")
            
            # 启动浏览器状态监控
            self.browser_monitor_task = asyncio.create_task(self._monitor_browser_status())
            
        except Exception as e:
            self.log_message(f"启动本地浏览器失败: {str(e)}")
            raise

    async def _on_browser_closed(self):
        """浏览器关闭事件处理"""
        try:
            # 防止重复处理：只有在浏览器未初始化且没有访问权限时才跳过
            if not self.browser_initialized and not self.has_access:
                self.log_message("🔄 浏览器已关闭且权限已释放，跳过处理")
                return
                
            self.log_message("🔄 检测到浏览器已关闭，正在处理...")
            
            # 重置浏览器状态（在释放权限之前先重置状态，避免重复触发）
            old_browser_initialized = self.browser_initialized
            self.browser = None
            self.page = None
            self.browser_initialized = False
            
            # 停止浏览器监控任务
            if self.browser_monitor_task:
                self.browser_monitor_task.cancel()
                self.browser_monitor_task = None
                self.log_message("🔄 已停止浏览器监控任务")
            
            # 停止独立权限监控任务
            if self.access_monitor_task:
                self.access_monitor_task.cancel()
                self.access_monitor_task = None
                self.log_message("🔄 已停止独立权限监控任务")
            
            # 如果当前有访问权限，自动释放
            if self.has_access:
                self.log_message("🔓 浏览器关闭，自动释放访问权限...")
                
                # 直接调用服务器API释放权限，避免重复关闭浏览器
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                        async with session.post(f"{self.base_url}/access/release/{self.session_id}") as response:
                            if response.status == 200:
                                self.has_access = False
                                self.allocated_domains = []
                                self.update_status("浏览器关闭，已自动释放权限", "blue")
                                self.log_message("✅ 已自动释放访问权限")
                                self.update_buttons_state()
                                
                                # 停止心跳
                                if self.heartbeat_task:
                                    self.heartbeat_task.cancel()
                                    self.heartbeat_task = None
                                    self.log_message("🔄 已停止心跳任务")
                            else:
                                self.log_message(f"❌ 自动释放访问权限失败: HTTP {response.status}")
                except asyncio.TimeoutError:
                    self.log_message("❌ 自动释放访问权限超时")
                except Exception as e:
                    self.log_message(f"❌ 自动释放访问权限失败: {str(e)}")
            else:
                self.log_message("🔄 浏览器已关闭，当前无访问权限需要释放")
            
        except Exception as e:
            self.log_message(f"❌ 处理浏览器关闭事件时出错: {str(e)}")

    async def _monitor_browser_status(self):
        """监控浏览器状态"""
        self.log_message("🔍 开始监控浏览器状态（每2秒检查一次）")
        
        while self.browser_initialized and self.browser and self.page:
            try:
                await asyncio.sleep(2)  # 缩短检查间隔到2秒
                
                if not self.browser or not self.page:
                    self.log_message("🔄 监控检测到浏览器对象已失效")
                    await self._on_browser_closed()
                    break
                
                # 测试浏览器是否仍然可用
                try:
                    await asyncio.wait_for(self.page.evaluate("() => true"), timeout=1.0)
                except asyncio.TimeoutError:
                    self.log_message("🔄 监控检测到浏览器响应超时")
                    await self._on_browser_closed()
                    break
                except Exception as e:
                    # 检查是否是浏览器关闭错误
                    if "Target page, context or browser has been closed" in str(e) or "Browser has been closed" in str(e):
                        self.log_message("🔄 监控检测到浏览器已关闭")
                    else:
                        self.log_message(f"🔄 监控检测到浏览器异常: {str(e)}")
                    await self._on_browser_closed()
                    break
                
            except asyncio.CancelledError:
                self.log_message("🔄 浏览器监控任务已取消")
                break
            except Exception as e:
                self.log_message(f"🔄 浏览器监控出错: {str(e)}")
                await self._on_browser_closed()
                break
        
        self.log_message("🔍 浏览器监控已停止")

    async def _apply_cookies_to_browser(self, cookies: List[dict]):
        """应用cookies到浏览器"""
        try:
            if not self.page:
                raise Exception("浏览器页面未初始化")
            
            # 处理cookies格式
            processed_cookies = []
            for cookie in cookies:
                processed_cookie = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie.get('domain', ''),
                    'path': cookie.get('path', '/'),
                    'secure': cookie.get('secure', False),
                    'httpOnly': cookie.get('httpOnly', False),
                    'sameSite': cookie.get('sameSite', 'Lax')
                }
                
                if 'expires' in cookie:
                    processed_cookie['expires'] = cookie['expires']
                
                processed_cookies.append(processed_cookie)
            
            # 添加cookies到浏览器
            await self.page.context.add_cookies(processed_cookies)
            self.log_message(f"已应用 {len(processed_cookies)} 个cookies到浏览器")
            
        except Exception as e:
            self.log_message(f"应用cookies失败: {str(e)}")
            raise

    def disconnect_from_server(self):
        """断开服务器连接"""
        def run_disconnect():
            asyncio.run_coroutine_threadsafe(self._disconnect_from_server(), self.loop)
        
        threading.Thread(target=run_disconnect, daemon=True).start()

    async def _disconnect_from_server(self):
        """异步断开服务器连接"""
        try:
            # 释放访问权限
            if self.has_access:
                await self._release_access()
            
            # 关闭WebSocket
            if self.ws:
                await self.ws.close()
                self.ws = None
            
            # 停止任务
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            if self.ws_task:
                self.ws_task.cancel()
            if self.browser_monitor_task:
                self.browser_monitor_task.cancel()
            if self.access_monitor_task:
                self.access_monitor_task.cancel()
            
            # 关闭浏览器
            if self.browser:
                await self.browser.close()
                self.browser = None
                self.page = None
                self.browser_initialized = False
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            # 重置状态
            self.connected = False
            self.has_access = False
            self.allocated_domains = []
            self.session_id = None
            
            self.update_status("已断开连接", "red")
            self.update_session_id("无")
            self.update_buttons_state()
            self.log_message("已断开服务器连接")
            
        except Exception as e:
            self.log_message(f"断开连接时出错: {str(e)}")

    def on_closing(self):
        """窗口关闭事件"""
        try:
            # 异步清理资源
            def cleanup():
                asyncio.run_coroutine_threadsafe(self._disconnect_from_server(), self.loop)
                self.loop.call_soon_threadsafe(self.loop.stop)
            
            threading.Thread(target=cleanup, daemon=True).start()
            
            # 等待清理完成
            import time
            time.sleep(1)
            
        except:
            pass
        finally:
            self.root.destroy()

    def run(self):
        """运行GUI"""
        self.root.mainloop()

def main():
    """主函数"""
    app = EnhancedRemoteBrowserClientGUI()
    app.run()

if __name__ == "__main__":
    main() 