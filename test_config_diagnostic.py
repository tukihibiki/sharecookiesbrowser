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
配置诊断脚本
用于检查服务器配置文件和当前设置状态
"""

import json
import requests
from pathlib import Path
import configparser
from datetime import datetime

def check_config_file():
    """检查配置文件状态"""
    print("=== 配置文件检查 ===")
    
    config_file = Path("server_config.ini")
    if config_file.exists():
        print(f"✅ 配置文件存在: {config_file.absolute()}")
        
        # 读取配置文件内容
        config = configparser.ConfigParser()
        config.read(config_file, encoding='utf-8')
        
        print("📋 配置文件内容:")
        for section in config.sections():
            print(f"  [{section}]")
            for key, value in config[section].items():
                print(f"    {key} = {value}")
        
        # 检查关键设置
        if 'server' in config:
            max_clients = config['server'].get('max_concurrent_clients', 'NOT_SET')
            print(f"🔧 最大并发客户端数: {max_clients}")
        else:
            print("⚠️ 未找到 [server] 配置段")
    else:
        print("❌ 配置文件不存在")

def check_server_api():
    """检查服务器API状态"""
    print("\n=== 服务器API检查 ===")
    
    try:
        # 检查调试配置API
        response = requests.get("http://localhost:8001/debug/config", timeout=5)
        if response.status_code == 200:
            debug_info = response.json()
            print("🔧 调试配置信息:")
            print(json.dumps(debug_info, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 调试配置API失败: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 无法连接到服务器: {e}")
    
    try:
        # 检查访问状态API
        response = requests.get("http://localhost:8001/access/status", timeout=5)
        if response.status_code == 200:
            status_info = response.json()
            print("\n🚦 访问协调器状态:")
            print(json.dumps(status_info, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 访问状态API失败: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 无法获取访问状态: {e}")

def simulate_client_request():
    """模拟客户端请求"""
    print("\n=== 模拟客户端请求 ===")
    
    try:
        # 创建会话
        session_response = requests.post("http://localhost:8001/create_session", timeout=5)
        if session_response.status_code != 200:
            print(f"❌ 创建会话失败: {session_response.status_code}")
            return
        
        session_id = session_response.json()["session_id"]
        print(f"✅ 会话创建成功: {session_id}")
        
        # 请求访问权限
        access_data = {
            "session_id": session_id,
            "priority": 0
        }
        
        access_response = requests.post("http://localhost:8001/access/request", 
                                      json=access_data, timeout=5)
        if access_response.status_code == 200:
            access_result = access_response.json()
            print("🎫 访问请求结果:")
            print(json.dumps(access_result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 访问请求失败: {access_response.status_code}")
            print(f"错误详情: {access_response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 模拟客户端请求失败: {e}")

def main():
    print(f"配置诊断脚本 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    check_config_file()
    check_server_api()
    simulate_client_request()
    
    print("\n=" * 50)
    print("诊断完成！")
    print("\n💡 建议:")
    print("1. 检查配置文件中的max_concurrent_clients值")
    print("2. 确认服务器是否正确加载了配置")
    print("3. 查看服务器日志中的详细信息")
    print("4. 如果问题仍然存在，请重启服务器")

if __name__ == "__main__":
    main() 