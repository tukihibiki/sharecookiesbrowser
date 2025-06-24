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

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import json
import subprocess
import time
import os
import sys
from datetime import datetime
from pathlib import Path
import webbrowser
import psutil
import requests  # 使用requests替代aiohttp避免async问题

class ServerGUIManager:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("远程浏览器服务器管理中心")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)
        
        # 服务器配置
        self.server_url = "http://localhost:8001"
        self.server_process = None
        self.admin_key = None
        # 从配置文件读取最大客户端数量，如果没有则使用默认值2
        try:
            config_file = Path("server_config.ini")
            if config_file.exists():
                import configparser
                config = configparser.ConfigParser()
                config.read(config_file, encoding='utf-8')
                self.max_clients = int(config.get('server', 'max_concurrent_clients', fallback='2'))
            else:
                self.max_clients = 2  # 默认值
        except Exception as e:
            self.max_clients = 2  # 如果读取失败，使用默认值
            print(f"读取配置文件失败，使用默认值: {e}")
        
        # 输出配置加载结果
        print(f"🔧 GUI管理器加载配置: max_concurrent_clients = {self.max_clients}")
        
        # 状态变量
        self.is_server_running = tk.BooleanVar(value=False)
        self.cookies_count = tk.StringVar(value="0")
        self.active_clients = tk.StringVar(value="0")
        self.queue_length = tk.StringVar(value="0")
        
        # 自动刷新控制
        self.auto_refresh = True
        self.refresh_thread = None
        self._server_started_logged = False
        
        self.setup_ui()
        self.start_monitoring()
        
        # 延迟1秒后进行初始数据刷新（确保GUI已完全加载）
        self.root.after(1000, self.initial_data_refresh)
        
    def setup_ui(self):
        """设置用户界面"""
        # 创建主菜单
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="退出", command=self.on_closing)
        
        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="服务器配置", command=self.show_server_config)
        
        # 创建主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部状态栏
        self.create_status_bar(main_frame)
        
        # 创建标签页
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # 服务器控制标签页
        server_frame = ttk.Frame(notebook)
        notebook.add(server_frame, text="服务器控制")
        self.create_server_control_tab(server_frame)
        
        # Cookies管理标签页
        cookies_frame = ttk.Frame(notebook)
        notebook.add(cookies_frame, text="Cookies管理")
        self.create_cookies_tab(cookies_frame)
        
        # 客户端管理标签页
        clients_frame = ttk.Frame(notebook)
        notebook.add(clients_frame, text="客户端管理")
        self.create_clients_tab(clients_frame)
        
        # 日志标签页
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="系统日志")
        self.create_log_tab(log_frame)
        
    def create_status_bar(self, parent):
        """创建状态栏"""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 服务器状态指示器
        ttk.Label(status_frame, text="服务器状态:").grid(row=0, column=0, padx=(0, 5))
        self.status_label = ttk.Label(status_frame, text="已停止", foreground="red")
        self.status_label.grid(row=0, column=1, padx=(0, 20))
        
        ttk.Label(status_frame, text="Cookies:").grid(row=0, column=2, padx=(0, 5))
        ttk.Label(status_frame, textvariable=self.cookies_count).grid(row=0, column=3, padx=(0, 20))
        
        ttk.Label(status_frame, text="活跃客户端:").grid(row=0, column=4, padx=(0, 5))
        ttk.Label(status_frame, textvariable=self.active_clients).grid(row=0, column=5, padx=(0, 20))
        
        ttk.Label(status_frame, text="排队数:").grid(row=0, column=6, padx=(0, 5))
        ttk.Label(status_frame, textvariable=self.queue_length).grid(row=0, column=7)
        
    def create_server_control_tab(self, parent):
        """创建服务器控制标签页"""
        # 服务器控制区域
        control_frame = ttk.LabelFrame(parent, text="服务器控制", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 按钮区域
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        
        # 启动/停止服务器按钮
        self.start_button = ttk.Button(button_frame, text="启动服务器", 
                                      command=self.start_server)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="停止服务器", 
                                     command=self.stop_server, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # 重启服务器按钮
        ttk.Button(button_frame, text="重启服务器", 
                  command=self.restart_server).pack(side=tk.LEFT, padx=(0, 10))
        
        # 打开网页管理按钮
        ttk.Button(button_frame, text="打开网页管理", 
                  command=self.open_web_admin).pack(side=tk.LEFT, padx=(0, 10))
        
        # 客户端数量设置
        clients_frame = ttk.Frame(control_frame)
        clients_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(clients_frame, text="最大同时在线客户端数:").pack(side=tk.LEFT)
        self.max_clients_var = tk.IntVar(value=self.max_clients)
        clients_spinbox = ttk.Spinbox(clients_frame, from_=1, to=10, 
                                     textvariable=self.max_clients_var,
                                     command=self.update_max_clients, width=10)
        clients_spinbox.pack(side=tk.LEFT, padx=(10, 0))
        
        # 服务器信息显示
        info_frame = ttk.LabelFrame(parent, text="服务器信息", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建信息显示区域
        info_text = scrolledtext.ScrolledText(info_frame, height=15, state=tk.DISABLED)
        info_text.pack(fill=tk.BOTH, expand=True)
        self.info_text = info_text
        
    def create_cookies_tab(self, parent):
        """创建Cookies管理标签页"""
        # Cookies信息区域
        info_frame = ttk.LabelFrame(parent, text="Cookies状态", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Cookies信息显示
        info_grid = ttk.Frame(info_frame)
        info_grid.pack(fill=tk.X)
        
        ttk.Label(info_grid, text="Cookies数量:").grid(row=0, column=0, sticky=tk.W)
        self.cookies_count_label = ttk.Label(info_grid, text="0")
        self.cookies_count_label.grid(row=0, column=1, padx=(10, 0), sticky=tk.W)
        
        ttk.Label(info_grid, text="登录状态:").grid(row=1, column=0, sticky=tk.W)
        self.login_status_label = ttk.Label(info_grid, text="未知")
        self.login_status_label.grid(row=1, column=1, padx=(10, 0), sticky=tk.W)
        
        ttk.Label(info_grid, text="最后更新:").grid(row=2, column=0, sticky=tk.W)
        self.last_update_label = ttk.Label(info_grid, text="从未")
        self.last_update_label.grid(row=2, column=1, padx=(10, 0), sticky=tk.W)
        
        # Cookies操作按钮
        button_frame = ttk.Frame(info_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="刷新Cookies", 
                  command=self.refresh_cookies).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="删除选中", 
                  command=self.delete_selected_cookies).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="清空所有", 
                  command=self.clear_cookies).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="导出Cookies", 
                  command=self.export_cookies).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="导入Cookies", 
                  command=self.import_cookies).pack(side=tk.LEFT, padx=(0, 10))
        
        # 第二行：选择和浏览器操作按钮
        browser_frame = ttk.Frame(info_frame)
        browser_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(browser_frame, text="🔲 全选", 
                  command=self.select_all_cookies).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(browser_frame, text="🔳 反选", 
                  command=self.invert_selection_cookies).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(browser_frame, text="🔲 清除选择", 
                  command=self.clear_selection_cookies).pack(side=tk.LEFT, padx=(0, 10))
        
        # 分隔符
        ttk.Separator(browser_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(10, 10))
        
        ttk.Button(browser_frame, text="🧠 智能浏览器登录", 
                  command=self.start_admin_browser).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(browser_frame, text="🔄 快速更新模式", 
                  command=self.auto_login_update).pack(side=tk.LEFT, padx=(0, 10))
        
        # Cookies详细显示
        cookies_frame = ttk.LabelFrame(parent, text="Cookies详情", padding=10)
        cookies_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建Treeview显示cookies（支持多选）
        columns = ('名称', '值', '域名', '路径', '安全', 'HttpOnly')
        self.cookies_tree = ttk.Treeview(cookies_frame, columns=columns, show='headings', height=15, selectmode='extended')
        
        # 定义列标题
        for col in columns:
            self.cookies_tree.heading(col, text=col)
            if col == '值':
                self.cookies_tree.column(col, width=200)
            elif col in ['安全', 'HttpOnly']:
                self.cookies_tree.column(col, width=80)
            else:
                self.cookies_tree.column(col, width=120)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(cookies_frame, orient=tk.VERTICAL, command=self.cookies_tree.yview)
        self.cookies_tree.configure(yscrollcommand=scrollbar.set)
        
        self.cookies_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
    def create_clients_tab(self, parent):
        """创建客户端管理标签页"""
        # 客户端统计信息
        stats_frame = ttk.LabelFrame(parent, text="客户端统计", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        stats_grid = ttk.Frame(stats_frame)
        stats_grid.pack(fill=tk.X)
        
        ttk.Label(stats_grid, text="当前活跃:").grid(row=0, column=0, sticky=tk.W)
        self.active_count_label = ttk.Label(stats_grid, text="0")
        self.active_count_label.grid(row=0, column=1, padx=(10, 0), sticky=tk.W)
        
        ttk.Label(stats_grid, text="排队等待:").grid(row=0, column=2, padx=(20, 0), sticky=tk.W)
        self.queue_count_label = ttk.Label(stats_grid, text="0")
        self.queue_count_label.grid(row=0, column=3, padx=(10, 0), sticky=tk.W)
        
        ttk.Label(stats_grid, text="总连接数:").grid(row=0, column=4, padx=(20, 0), sticky=tk.W)
        self.total_count_label = ttk.Label(stats_grid, text="0")
        self.total_count_label.grid(row=0, column=5, padx=(10, 0), sticky=tk.W)
        
        # 客户端管理按钮
        control_frame = ttk.Frame(stats_frame)
        control_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(control_frame, text="刷新列表", 
                  command=self.refresh_clients).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(control_frame, text="踢出选中", 
                  command=self.kick_selected_client).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(control_frame, text="提升优先级", 
                  command=self.promote_client).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(control_frame, text="降低优先级", 
                  command=self.demote_client).pack(side=tk.LEFT)
        
        # 客户端列表
        clients_frame = ttk.LabelFrame(parent, text="客户端列表", padding=10)
        clients_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建Treeview显示客户端信息
        client_columns = ('状态', 'ID', 'IP地址', '接入时间', '排队时间', '使用时间', '活跃时间', '优先级')
        self.clients_tree = ttk.Treeview(clients_frame, columns=client_columns, show='headings', height=15)
        
        # 定义列标题和宽度
        column_widths = {'状态': 80, 'ID': 100, 'IP地址': 120, '接入时间': 150, 
                        '排队时间': 100, '使用时间': 100, '活跃时间': 100, '优先级': 80}
        
        for col in client_columns:
            self.clients_tree.heading(col, text=col)
            self.clients_tree.column(col, width=column_widths.get(col, 100))
        
        # 添加滚动条
        client_scrollbar = ttk.Scrollbar(clients_frame, orient=tk.VERTICAL, command=self.clients_tree.yview)
        self.clients_tree.configure(yscrollcommand=client_scrollbar.set)
        
        self.clients_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        client_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
    def create_log_tab(self, parent):
        """创建日志标签页"""
        # 日志控制区域
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(control_frame, text="清空日志", 
                  command=self.clear_log).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(control_frame, text="保存日志", 
                  command=self.save_log).pack(side=tk.LEFT, padx=(0, 10))
        
        # 自动滚动选项
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="自动滚动", 
                       variable=self.auto_scroll_var).pack(side=tk.LEFT, padx=(20, 0))
        
        # 日志显示区域
        self.log_text = scrolledtext.ScrolledText(parent, height=25, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ================ 服务器控制方法 ================
    def start_server(self):
        """启动服务器"""
        try:
            self.log_message("正在启动服务器...")
            
            # 启动服务器进程
            server_script = Path(__file__).parent / "remote_browser_server.py"
            if not server_script.exists():
                raise FileNotFoundError("找不到服务器脚本文件")
            
            # 使用subprocess启动服务器（后台运行，重定向输出）
            self.server_process = subprocess.Popen([
                sys.executable, str(server_script)
            ], 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1)
            
            # 启动输出读取线程
            threading.Thread(target=self._read_server_output, daemon=True).start()
            
            # 等待服务器启动
            self.root.after(3000, self.check_server_status)
            
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动服务器: {str(e)}")
            self.log_message(f"服务器启动失败: {str(e)}")
            
    def _read_server_output(self):
        """读取服务器输出并显示在GUI中"""
        try:
            if not self.server_process:
                return
                
            for line in iter(self.server_process.stdout.readline, ''):
                if line.strip():
                    # 过滤掉一些不重要的日志
                    if any(skip in line for skip in ['INFO:uvicorn', 'GET /', 'POST /', 'WebSocket']):
                        continue
                    self.root.after(0, self._update_server_info, f"[服务器] {line.strip()}")
                    
                # 检查进程是否还在运行
                if self.server_process.poll() is not None:
                    break
                    
        except Exception as e:
            self.root.after(0, self.log_message, f"读取服务器输出时出错: {str(e)}")
            
    def _update_server_info(self, message):
        """更新服务器信息显示"""
        try:
            self.info_text.config(state=tk.NORMAL)
            self.info_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} {message}\n")
            self.info_text.see(tk.END)
            self.info_text.config(state=tk.DISABLED)
        except Exception as e:
            self.log_message(f"更新服务器信息失败: {str(e)}")
            
    def stop_server(self):
        """停止服务器"""
        try:
            self.log_message("正在停止服务器...")
            
            if self.server_process:
                try:
                    # 先尝试优雅关闭
                    self.server_process.terminate()
                    self.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 如果超时，强制杀死进程
                    self.server_process.kill()
                    self.server_process.wait()
                finally:
                    # 关闭输出流
                    if self.server_process.stdout:
                        self.server_process.stdout.close()
                    self.server_process = None
            
            # 强制杀死相关进程
            self.kill_server_processes()
            
            self.is_server_running.set(False)
            self.status_label.config(text="已停止", foreground="red")
            
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            
            self.log_message("服务器已停止")
            self._update_server_info("[系统] 服务器进程已终止")
            
        except Exception as e:
            messagebox.showerror("停止失败", f"无法停止服务器: {str(e)}")
            self.log_message(f"服务器停止失败: {str(e)}")
            
    def restart_server(self):
        """重启服务器"""
        self.log_message("正在重启服务器...")
        self.stop_server()
        self.root.after(2000, self.start_server)  # 延迟2秒后启动
        
    def kill_server_processes(self):
        """强制终止服务器相关进程"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['cmdline'] and 'remote_browser_server.py' in str(proc.info['cmdline']):
                        proc.kill()
                        self.log_message(f"已终止进程 PID: {proc.info['pid']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            self.log_message(f"清理进程时出错: {str(e)}")

    def open_web_admin(self):
        """打开网页管理界面"""
        if not self.is_server_running.get():
            messagebox.showwarning("警告", "服务器未运行，请先启动服务器")
            return
            
        try:
            # 打开浏览器到FastAPI的自动文档页面
            admin_url = f"{self.server_url}/docs"
            webbrowser.open(admin_url)
            self.log_message(f"已打开网页管理界面: {admin_url}")
            
            # 显示管理员密钥信息
            admin_key = self._get_admin_key()
            if admin_key:
                messagebox.showinfo("管理员密钥", 
                    f"网页管理界面已打开\n\n"
                    f"访问地址: {admin_url}\n"
                    f"管理员密钥: {admin_key}\n\n"
                    f"您可以使用FastAPI文档界面测试管理API，\n"
                    f"在需要X-Admin-Key的地方输入上述密钥。")
            
        except Exception as e:
            messagebox.showerror("启动失败", f"无法打开网页管理: {str(e)}")
            
    def update_max_clients(self):
        """更新最大客户端数量"""
        new_max_clients = self.max_clients_var.get()
        if new_max_clients != self.max_clients:
            self.max_clients = new_max_clients
            self.log_message(f"最大同时在线客户端数设置为: {self.max_clients}")
            # 如果服务器正在运行，实时更新服务器配置
            if self.is_server_running.get():
                threading.Thread(target=lambda: self._update_server_max_clients_async(self.max_clients), daemon=True).start()
                
    def _update_server_max_clients_async(self, max_clients: int):
        """异步更新服务器最大客户端数"""
        try:
            admin_key = self._get_admin_key()
            if not admin_key:
                self.root.after(0, self.log_message, "无法获取管理员密钥，无法更新服务器配置")
                return
            
            update_data = {"max_clients": max_clients}
            headers = {"X-Admin-Key": admin_key, "Content-Type": "application/json"}
            
            response = requests.post(
                f"{self.server_url}/admin/server/config/max-clients",
                json=update_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                self.root.after(0, self.log_message, f"服务器配置已更新: {result.get('message', '最大客户端数已设置')}")
            elif response.status_code == 401:
                self.root.after(0, self.log_message, "管理员密钥无效，无法更新服务器配置")
            else:
                self.root.after(0, self.log_message, f"更新服务器配置失败: HTTP {response.status_code}")
                
        except Exception as e:
            self.root.after(0, self.log_message, f"更新服务器配置时出错: {str(e)}")

    def show_server_config(self):
        """显示服务器配置对话框"""
        config_window = tk.Toplevel(self.root)
        config_window.title("服务器配置")
        config_window.geometry("400x300")
        config_window.transient(self.root)
        config_window.grab_set()
        
        # 服务器URL配置
        ttk.Label(config_window, text="服务器URL:").pack(pady=(10, 5))
        url_var = tk.StringVar(value=self.server_url)
        ttk.Entry(config_window, textvariable=url_var, width=50).pack(pady=(0, 10))
        
        # 保存按钮
        def save_config():
            self.server_url = url_var.get()
            self.log_message(f"服务器URL已更新为: {self.server_url}")
            config_window.destroy()
            
        ttk.Button(config_window, text="保存", command=save_config).pack(pady=10)

    # ================ Cookies管理方法 ================
    def refresh_cookies(self):
        """刷新Cookies信息"""
        threading.Thread(target=self._refresh_cookies_sync, daemon=True).start()
        
    def _refresh_cookies_sync(self):
        """同步刷新Cookies"""
        try:
            response = requests.get(f"{self.server_url}/cookies", timeout=5)
            if response.status_code == 200:
                data = response.json()
                # 记录获取到的数据结构
                self.root.after(0, self.log_message, f"获取Cookies数据: {len(data.get('cookies', []))}个, 登录状态: {data.get('logged_in', 'Unknown')}")
                self.root.after(0, self._update_cookies_display, data)
            else:
                self.root.after(0, self.log_message, f"获取Cookies失败: {response.status_code}")
        except Exception as e:
            self.root.after(0, self.log_message, f"刷新Cookies错误: {str(e)}")
            
    def _update_cookies_display(self, cookies_data):
        """更新Cookies显示"""
        try:
            cookies = cookies_data.get('cookies', [])
            logged_in = cookies_data.get('logged_in', False)
            last_updated = cookies_data.get('last_updated', '从未')
            
            # 详细记录数据解析过程
            self.log_message(f"解析Cookies数据: cookies={len(cookies)}, logged_in={logged_in}, last_updated={last_updated}")
            
            # 更新状态显示
            self.cookies_count.set(str(len(cookies)))
            self.cookies_count_label.config(text=str(len(cookies)))
            
            # 重点：登录状态更新
            login_text = "已登录" if logged_in else "未登录"
            self.login_status_label.config(text=login_text)
            self.log_message(f"登录状态标签已更新为: {login_text}")
            
            self.last_update_label.config(text=last_updated)
            
            # 清空并更新cookies树视图
            for item in self.cookies_tree.get_children():
                self.cookies_tree.delete(item)
                
            for cookie in cookies:
                values = (
                    cookie.get('name', ''),
                    cookie.get('value', '')[:50] + '...' if len(cookie.get('value', '')) > 50 else cookie.get('value', ''),
                    cookie.get('domain', ''),
                    cookie.get('path', ''),
                    '是' if cookie.get('secure', False) else '否',
                    '是' if cookie.get('httpOnly', False) else '否'
                )
                self.cookies_tree.insert('', tk.END, values=values)
                
            self.log_message(f"Cookies信息已更新完成: {len(cookies)}个, 登录状态: {login_text}")
            
        except Exception as e:
            self.log_message(f"更新Cookies显示失败: {str(e)}")

    def clear_cookies(self):
        """清空Cookies"""
        if messagebox.askyesno("确认", "确定要清空所有Cookies吗？"):
            threading.Thread(target=self._clear_cookies_async, daemon=True).start()
            
    def _clear_cookies_async(self):
        """异步清空Cookies"""
        try:
            admin_key = self._get_admin_key()
            if not admin_key:
                self.root.after(0, self.log_message, "无法获取管理员密钥")
                return
            
            headers = {"X-Admin-Key": admin_key}
            response = requests.delete(f"{self.server_url}/admin/cookies", headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                self.root.after(0, self.log_message, f"{result.get('message', '已清空所有Cookies')}")
                # 刷新Cookies显示
                self.root.after(1000, self.refresh_cookies)
            elif response.status_code == 401:
                self.root.after(0, self.log_message, "管理员密钥无效")
            else:
                self.root.after(0, self.log_message, f"清空Cookies失败: HTTP {response.status_code}")
                
        except Exception as e:
            self.root.after(0, self.log_message, f"清空Cookies时出错: {str(e)}")

    def export_cookies(self):
        """导出Cookies"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="导出Cookies",
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
            )
            
            if file_path:
                threading.Thread(target=lambda: self._export_cookies_sync(file_path), daemon=True).start()
                
        except Exception as e:
            messagebox.showerror("导出失败", f"导出Cookies失败: {str(e)}")
            
    def _export_cookies_sync(self, file_path):
        """同步导出Cookies"""
        try:
            response = requests.get(f"{self.server_url}/cookies", timeout=5)
            if response.status_code == 200:
                data = response.json()
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.root.after(0, self.log_message, f"Cookies已导出到: {file_path}")
            else:
                self.root.after(0, self.log_message, f"导出失败: {response.status_code}")
        except Exception as e:
            self.root.after(0, self.log_message, f"导出Cookies错误: {str(e)}")

    def import_cookies(self):
        """导入Cookies"""
        try:
            file_path = filedialog.askopenfilename(
                title="导入Cookies",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
            )
            
            if file_path:
                threading.Thread(target=lambda: self._import_cookies_sync(file_path), daemon=True).start()
                
        except Exception as e:
            messagebox.showerror("导入失败", f"导入Cookies失败: {str(e)}")
            
    def _import_cookies_sync(self, file_path):
        """同步导入Cookies"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
            
            # 提取cookies数组
            cookies = cookies_data.get('cookies', []) if isinstance(cookies_data, dict) else cookies_data
            
            if not cookies:
                self.root.after(0, self.log_message, "❌ 文件中没有找到有效的Cookies数据")
                return
            
            # 调用导入API
            admin_key = self._get_admin_key()
            if not admin_key:
                self.root.after(0, self.log_message, "无法获取管理员密钥")
                return
            
            import_data = {"cookies": cookies}
            headers = {"X-Admin-Key": admin_key, "Content-Type": "application/json"}
            
            response = requests.post(
                f"{self.server_url}/admin/cookies/import",
                json=import_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                self.root.after(0, self.log_message, f"✅ {result.get('message', f'已导入 {len(cookies)} 个Cookies')}")
                # 刷新Cookies显示
                self.root.after(1000, self.refresh_cookies)
            elif response.status_code == 401:
                self.root.after(0, self.log_message, "❌ 管理员密钥无效")
            else:
                self.root.after(0, self.log_message, f"❌ 导入Cookies失败: HTTP {response.status_code}")
                
        except Exception as e:
            self.root.after(0, self.log_message, f"❌ 导入Cookies错误: {str(e)}")
    
    def select_all_cookies(self):
        """全选所有cookies"""
        try:
            all_items = self.cookies_tree.get_children()
            self.cookies_tree.selection_set(all_items)
            self.log_message(f"已全选 {len(all_items)} 个cookies")
        except Exception as e:
            self.log_message(f"全选失败: {str(e)}")
    
    def invert_selection_cookies(self):
        """反选cookies"""
        try:
            all_items = self.cookies_tree.get_children()
            selected_items = self.cookies_tree.selection()
            
            # 清除当前选择
            self.cookies_tree.selection_remove(selected_items)
            
            # 选择未被选中的项目
            unselected_items = [item for item in all_items if item not in selected_items]
            self.cookies_tree.selection_set(unselected_items)
            
            self.log_message(f"已反选，当前选中 {len(unselected_items)} 个cookies")
        except Exception as e:
            self.log_message(f"反选失败: {str(e)}")
    
    def clear_selection_cookies(self):
        """清除选择"""
        try:
            self.cookies_tree.selection_remove(self.cookies_tree.selection())
            self.log_message("已清除所有选择")
        except Exception as e:
            self.log_message(f"清除选择失败: {str(e)}")
    
    def delete_selected_cookies(self):
        """删除选中的cookies"""
        try:
            selected_items = self.cookies_tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请先选择要删除的cookies")
                return
            
            # 获取选中的cookies信息
            selected_cookies = []
            for item in selected_items:
                values = self.cookies_tree.item(item)['values']
                cookie_info = {
                    'name': values[0],
                    'value': values[1],
                    'domain': values[2],
                    'path': values[3]
                }
                selected_cookies.append(cookie_info)
            
            # 确认删除
            result = messagebox.askyesno(
                "确认删除", 
                f"确定要删除选中的 {len(selected_cookies)} 个cookies吗？\n\n"
                f"删除的cookies包括：\n" + 
                "\n".join([f"• {c['name']} ({c['domain']})" for c in selected_cookies[:5]]) +
                (f"\n... 还有 {len(selected_cookies) - 5} 个" if len(selected_cookies) > 5 else "")
            )
            
            if result:
                # 在后台线程中执行删除
                threading.Thread(target=self._delete_cookies_async, args=(selected_cookies,), daemon=True).start()
                
        except Exception as e:
            messagebox.showerror("错误", f"删除cookies失败: {str(e)}")
            self.log_message(f"删除cookies失败: {str(e)}")
    
    def _delete_cookies_async(self, cookies_to_delete):
        """异步删除选中的cookies"""
        try:
            admin_key = self._get_admin_key()
            if not admin_key:
                self.root.after(0, self.log_message, "无法获取管理员密钥")
                return
            
            headers = {"X-Admin-Key": admin_key, "Content-Type": "application/json"}
            data = {"cookies_to_delete": cookies_to_delete}
            
            # 调用删除API
            response = requests.post(f"{self.server_url}/admin/cookies/delete", 
                                   headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                deleted_count = result.get('deleted_count', 0)
                remaining_count = result.get('remaining_count', 0)
                
                self.root.after(0, self.log_message, 
                               f"✅ 成功删除 {deleted_count} 个cookies，剩余 {remaining_count} 个")
                
                # 刷新显示
                self.root.after(0, self.refresh_cookies)
            else:
                error_msg = f"删除失败: HTTP {response.status_code}"
                try:
                    error_detail = response.json().get('detail', '')
                    if error_detail:
                        error_msg += f" - {error_detail}"
                except:
                    pass
                self.root.after(0, self.log_message, error_msg)
                
        except Exception as e:
            self.root.after(0, self.log_message, f"删除cookies时出错: {str(e)}")

    def start_admin_browser(self):
        """启动管理员浏览器"""
        if not self.is_server_running.get():
            messagebox.showwarning("警告", "服务器未运行，请先启动服务器")
            return
            
        try:
            self.log_message("正在启动管理员浏览器...")
            
            # 启动简化版浏览器登录工具
            login_script = Path(__file__).parent / "simple_browser_login.py"
            if login_script.exists():
                # 在新的控制台窗口中启动浏览器登录工具
                subprocess.Popen([
                    sys.executable, str(login_script), 
                    "--server", self.server_url
                ], creationflags=subprocess.CREATE_NEW_CONSOLE)
                
                self.log_message("智能浏览器登录已启动")
                messagebox.showinfo("智能浏览器登录", 
                    "智能浏览器登录工具已启动！\n\n"
                    "🧠 智能功能：\n"
                    "• 自动分析网站类型\n"
                    "• 智能选择cookies策略\n"
                    "• 自动优化共享设置\n\n"
                    "📝 操作步骤：\n"
                    "1. 在浏览器中访问任何需要登录的网站\n"
                    "2. 完成登录操作（微信扫码、密码等）\n"
                    "3. 登录成功后按回车键\n"
                    "4. 系统会自动分析并应用最佳策略\n\n"
                    "完成后可以点击'刷新Cookies'查看更新结果")
            else:
                messagebox.showerror("错误", "找不到浏览器登录工具")
                
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动管理员浏览器: {str(e)}")
            self.log_message(f"启动管理员浏览器失败: {str(e)}")

    def auto_login_update(self):
        """自动登录更新（简化版）"""
        if not self.is_server_running.get():
            messagebox.showwarning("警告", "服务器未运行，请先启动服务器")
            return
            
        result = messagebox.askyesno("快速更新模式", 
            "这将启动快速更新流程：\n\n"
            "🚀 快速模式特点：\n"
            "• 无需手动操作浏览器\n"
            "• 自动打开到登录页面\n"
            "• 完全后台处理\n\n"
            "📝 操作步骤：\n"
            "1. 自动打开浏览器到指定登录页面\n"
            "2. 您手动完成登录操作\n"
            "3. 系统自动处理并更新cookies\n\n"
            "是否继续？")
        
        if result:
            try:
                self.log_message("启动自动登录更新...")
                
                # 在后台线程中启动登录更新
                threading.Thread(target=self._auto_login_update_async, daemon=True).start()
                
            except Exception as e:
                messagebox.showerror("启动失败", f"无法启动自动登录: {str(e)}")
                self.log_message(f"自动登录启动失败: {str(e)}")

    def _auto_login_update_async(self):
        """异步执行自动登录更新"""
        try:
            login_script = Path(__file__).parent / "simple_browser_login.py"
            if not login_script.exists():
                self.root.after(0, self.log_message, "找不到登录工具脚本")
                return
            
            self.root.after(0, self.log_message, "正在启动自动登录...")
            
            # 启动登录脚本
            result = subprocess.run([
                sys.executable, str(login_script), 
                "--server", self.server_url
            ], capture_output=True, text=True, timeout=300)  # 5分钟超时
            
            if result.returncode == 0:
                self.root.after(0, self.log_message, "自动登录更新成功完成")
                # 自动刷新cookies显示
                self.root.after(1000, self.refresh_cookies)
                self.root.after(0, lambda: messagebox.showinfo("成功", "Cookies更新成功！"))
            else:
                self.root.after(0, self.log_message, f"自动登录失败: {result.stderr}")
                self.root.after(0, lambda: messagebox.showerror("失败", f"自动登录失败:\n{result.stderr}"))
                
        except subprocess.TimeoutExpired:
            self.root.after(0, self.log_message, "自动登录超时")
            self.root.after(0, lambda: messagebox.showwarning("超时", "登录操作超时，请手动完成"))
        except Exception as e:
            self.root.after(0, self.log_message, f"自动登录出错: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"自动登录出错: {str(e)}"))

    # ================ 客户端管理方法 ================
    def refresh_clients(self):
        """刷新客户端列表"""
        threading.Thread(target=self._refresh_clients_sync, daemon=True).start()
        
    def _refresh_clients_sync(self):
        """同步刷新客户端信息"""
        try:
            # 尝试获取详细信息，如果失败则使用基本信息
            try:
                admin_key = self._get_admin_key()
                if admin_key:
                    headers = {"X-Admin-Key": admin_key}
                    response = requests.get(f"{self.server_url}/admin/clients/detailed", headers=headers, timeout=5)
                    if response.status_code == 200:
                        detailed_data = response.json()
                        self.root.after(0, self._update_clients_display_detailed, detailed_data)
                        return
            except Exception:
                pass  # 如果详细信息失败，继续使用基本信息
            
            # 使用基本信息作为后备
            response = requests.get(f"{self.server_url}/access/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.root.after(0, self._update_clients_display, data)
            else:
                self.root.after(0, self.log_message, f"获取客户端状态失败: {response.status_code}")
        except Exception as e:
            self.root.after(0, self.log_message, f"刷新客户端信息错误: {str(e)}")
            
    def _update_clients_display(self, status_data):
        """更新客户端显示"""
        try:
            active_client = status_data.get('active_client')
            queue_details = status_data.get('queue_details', [])
            active_client_info = status_data.get('active_client_info', {})
            
            # 更新统计信息
            active_count = 1 if active_client else 0
            queue_count = len(queue_details)
            total_count = active_count + queue_count
            
            self.active_clients.set(str(active_count))
            self.queue_length.set(str(queue_count))
            self.active_count_label.config(text=str(active_count))
            self.queue_count_label.config(text=str(queue_count))
            self.total_count_label.config(text=str(total_count))
            
            # 清空并更新客户端树视图
            for item in self.clients_tree.get_children():
                self.clients_tree.delete(item)
                
            # 添加活跃客户端
            if active_client:
                usage_time = active_client_info.get('usage_minutes', 0)
                inactive_time = active_client_info.get('inactive_minutes', 0)
                
                values = (
                    '活跃',
                    active_client[:8] + '...',
                    '未知',  # IP地址需要从其他地方获取
                    '未知',  # 接入时间
                    '0分钟',  # 排队时间
                    f"{usage_time:.1f}分钟",
                    f"{inactive_time:.1f}分钟前",
                    '高'
                )
                self.clients_tree.insert('', tk.END, values=values)
                
            # 添加排队客户端
            for i, client_info in enumerate(queue_details):
                values = (
                    f'排队第{client_info["position"]}位',
                    client_info['client_id'][:8] + '...',
                    '未知',
                    '未知',
                    f"{client_info['wait_minutes']:.1f}分钟",
                    '0分钟',
                    '排队中',
                    str(client_info.get('priority', 0))
                )
                self.clients_tree.insert('', tk.END, values=values)
                
            self.log_message(f"客户端信息已更新: {active_count}个活跃, {queue_count}个排队")
            
        except Exception as e:
            self.log_message(f"更新客户端显示失败: {str(e)}")
    
    def _update_clients_display_detailed(self, detailed_data):
        """更新客户端显示（使用详细信息）"""
        try:
            clients = detailed_data.get('clients', [])
            summary = detailed_data.get('summary', {})
            
            # 更新统计信息
            active_count = summary.get('active', 0)
            queue_count = summary.get('queued', 0)
            total_count = summary.get('total', 0)
            
            self.active_clients.set(str(active_count))
            self.queue_length.set(str(queue_count))
            self.active_count_label.config(text=str(active_count))
            self.queue_count_label.config(text=str(queue_count))
            self.total_count_label.config(text=str(total_count))
            
            # 清空并更新客户端树视图
            for item in self.clients_tree.get_children():
                self.clients_tree.delete(item)
            
            # 添加所有客户端（活跃和排队）
            for client in clients:
                status_text = "活跃" if client['status'] == 'active' else f"排队第{client.get('position', 0)}位"
                
                # 格式化时间显示
                usage_time = client.get('usage_time', 0)
                if isinstance(usage_time, (int, float)):
                    usage_time_str = f"{usage_time:.1f}分钟" if usage_time > 0 else "0分钟"
                else:
                    usage_time_str = str(usage_time)
                
                queue_time = client.get('queue_time', 0)
                if isinstance(queue_time, (int, float)):
                    queue_time_str = f"{queue_time:.1f}分钟" if queue_time > 0 else "0分钟"
                else:
                    queue_time_str = str(queue_time)
                
                last_activity = client.get('last_activity', '未知')
                if isinstance(last_activity, (int, float)):
                    last_activity_str = f"{last_activity:.1f}分钟前" if last_activity > 0 else "刚刚活跃"
                elif last_activity == "排队中":
                    last_activity_str = "排队中"
                else:
                    last_activity_str = str(last_activity)
                
                # 格式化连接时间
                connect_time = client.get('connect_time', 'unknown')
                if connect_time != 'unknown' and connect_time != '未知':
                    try:
                        from datetime import datetime
                        ct = datetime.fromisoformat(connect_time.replace('Z', '+00:00'))
                        connect_time_str = ct.strftime('%H:%M:%S')
                    except:
                        connect_time_str = connect_time
                else:
                    connect_time_str = '未知'
                
                values = (
                    status_text,
                    client['client_id'][:8] + '...',
                    client.get('ip_address', '未知'),
                    connect_time_str,
                    queue_time_str,
                    usage_time_str,
                    last_activity_str,
                    str(client.get('priority', 0))
                )
                self.clients_tree.insert('', tk.END, values=values)
            
            self.log_message(f"详细客户端信息已更新: {active_count}个活跃, {queue_count}个排队")
            
        except Exception as e:
            self.log_message(f"更新详细客户端显示失败: {str(e)}")
            # 如果详细信息处理失败，尝试基本信息
            if 'clients' in detailed_data:
                self._update_clients_display(detailed_data)

    def kick_selected_client(self):
        """踢出选中的客户端"""
        selection = self.clients_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要踢出的客户端")
            return
            
        # 获取选中客户端的信息
        item = selection[0]
        values = self.clients_tree.item(item, 'values')
        if not values:
            messagebox.showwarning("警告", "无法获取客户端信息")
            return
            
        client_id_short = values[1]  # 显示的是截断的ID
        client_status = values[0]
        
        if messagebox.askyesno("确认", f"确定要踢出客户端 {client_id_short} 吗？"):
            threading.Thread(target=lambda: self._kick_client_async(client_id_short, client_status), daemon=True).start()

    def promote_client(self):
        """提升客户端优先级"""
        selection = self.clients_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要提升优先级的客户端")
            return
        self.log_message("提升优先级功能待服务器API实现")

    def demote_client(self):
        """降低客户端优先级"""
        selection = self.clients_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要降低优先级的客户端")
            return
        self.log_message("降低优先级功能待服务器API实现")

    def _kick_client_async(self, client_id_short: str, client_status: str):
        """异步踢出客户端"""
        try:
            # 首先获取管理员密钥
            admin_key = self._get_admin_key()
            if not admin_key:
                self.root.after(0, self.log_message, "无法获取管理员密钥")
                return
            
            # 获取完整的客户端列表以找到完整的client_id
            response = requests.get(f"{self.server_url}/access/status", timeout=5)
            if response.status_code != 200:
                self.root.after(0, self.log_message, f"获取客户端列表失败: {response.status_code}")
                return
                
            status_data = response.json()
            full_client_id = None
            
            # 查找完整的client_id
            active_client = status_data.get('active_client')
            if active_client and active_client.startswith(client_id_short.replace('...', '')):
                full_client_id = active_client
            
            if not full_client_id:
                # 在排队列表中查找
                for client_info in status_data.get('queue_details', []):
                    if client_info['client_id'].startswith(client_id_short.replace('...', '')):
                        full_client_id = client_info['client_id']
                        break
            
            if not full_client_id:
                self.root.after(0, self.log_message, f"找不到客户端 {client_id_short} 的完整ID")
                return
            
            # 调用踢出API
            kick_data = {"reason": "GUI管理员踢出"}
            headers = {"X-Admin-Key": admin_key, "Content-Type": "application/json"}
            
            response = requests.post(
                f"{self.server_url}/admin/clients/{full_client_id}/kick",
                json=kick_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                self.root.after(0, self.log_message, f"成功踢出客户端 {client_id_short}: {result.get('message', '已踢出')}")
                # 刷新客户端列表
                self.root.after(1000, self.refresh_clients)
            elif response.status_code == 401:
                self.root.after(0, self.log_message, "管理员密钥无效")
            elif response.status_code == 404:
                self.root.after(0, self.log_message, f"客户端 {client_id_short} 不存在或已断开")
            else:
                self.root.after(0, self.log_message, f"踢出客户端失败: HTTP {response.status_code}")
                
        except Exception as e:
            self.root.after(0, self.log_message, f"踢出客户端时出错: {str(e)}")

    def _get_admin_key(self) -> str:
        """获取管理员密钥"""
        try:
            if self.admin_key:
                return self.admin_key
                
            response = requests.get(f"{self.server_url}/admin/key", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.admin_key = data.get("admin_key")
                return self.admin_key
            else:
                self.log_message(f"获取管理员密钥失败: HTTP {response.status_code}")
                return None
        except Exception as e:
            self.log_message(f"获取管理员密钥时出错: {str(e)}")
            return None

    # ================ 状态检查和监控方法 ================
    def check_server_status(self):
        """检查服务器状态"""
        threading.Thread(target=self._check_server_status_sync, daemon=True).start()
        
    def _check_server_status_sync(self):
        """同步检查服务器状态"""
        try:
            response = requests.get(f"{self.server_url}/health", timeout=5)
            if response.status_code == 200:
                self.root.after(0, self._update_server_running, True)
                return
        except Exception:
            pass
        self.root.after(0, self._update_server_running, False)
        
    def _update_server_running(self, running):
        """更新服务器运行状态"""
        self.is_server_running.set(running)
        if running:
            self.status_label.config(text="运行中", foreground="green")
            if not self._server_started_logged:
                self.log_message("服务器启动成功")
                self._server_started_logged = True
        else:
            self.status_label.config(text="已停止", foreground="red")
            self._server_started_logged = False

    def update_cookies_info(self):
        """更新Cookies信息"""
        threading.Thread(target=self._refresh_cookies_sync, daemon=True).start()

    def update_clients_info(self):
        """更新客户端信息"""
        threading.Thread(target=self._refresh_clients_sync, daemon=True).start()

    # ================ 日志相关方法 ================
    def clear_log(self):
        """清空日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def save_log(self):
        """保存日志"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="保存日志",
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                self.log_message(f"日志已保存到: {file_path}")
                
        except Exception as e:
            messagebox.showerror("保存失败", f"保存日志失败: {str(e)}")
        
    def log_message(self, message):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        if self.auto_scroll_var.get():
            self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ================ 监控和生命周期管理 ================
    def initial_data_refresh(self):
        """初始数据刷新"""
        self.log_message("🔄 执行初始数据刷新...")
        if self.is_server_running.get():
            self.log_message("✅ 服务器运行中，开始刷新Cookies数据")
            self.refresh_cookies()
        else:
            self.log_message("⚠️ 服务器未运行，检查服务器状态")
            self.check_server_status()
            # 如果服务器运行，延迟再次尝试刷新
            self.root.after(2000, lambda: self.refresh_cookies() if self.is_server_running.get() else None)

    def start_monitoring(self):
        """启动监控线程"""
        self.refresh_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.refresh_thread.start()
        
    def monitoring_loop(self):
        """监控循环"""
        while self.auto_refresh:
            try:
                # 检查服务器状态
                self.check_server_status()
                
                # 如果服务器运行中，更新各种信息
                if self.is_server_running.get():
                    self.update_cookies_info()
                    self.update_clients_info()
                    
                time.sleep(5)  # 每5秒刷新一次
                
            except Exception as e:
                print(f"监控循环错误: {e}")
                time.sleep(10)
                
    def on_closing(self):
        """关闭程序时的清理操作"""
        self.auto_refresh = False
        if self.server_process:
            self.stop_server()
        self.root.destroy()
        
    def run(self):
        """运行GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

if __name__ == "__main__":
    app = ServerGUIManager()
    app.run() 