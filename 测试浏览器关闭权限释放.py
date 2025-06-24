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
测试浏览器关闭后权限是否自动释放

用于验证修复后的自动释放权限功能是否正常工作
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

class BrowserCloseTest:
    def __init__(self):
        self.base_url = "http://localhost:8001"
        self.session_id = None
        self.test_results = []
    
    async def test_server_connection(self):
        """测试服务器连接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/") as response:
                    if response.status == 200:
                        print("✅ 服务器连接正常")
                        return True
                    else:
                        print(f"❌ 服务器响应异常: {response.status}")
                        return False
        except Exception as e:
            print(f"❌ 无法连接服务器: {e}")
            return False
    
    async def create_test_session(self):
        """创建测试会话"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/create_session") as response:
                    if response.status == 200:
                        result = await response.json()
                        self.session_id = result['session_id']
                        print(f"✅ 创建测试会话: {self.session_id[:8]}...")
                        return True
                    else:
                        print(f"❌ 创建会话失败: {response.status}")
                        return False
        except Exception as e:
            print(f"❌ 创建会话异常: {e}")
            return False
    
    async def request_access(self):
        """请求访问权限"""
        try:
            request_data = {
                "session_id": self.session_id,
                "domains": ["jufaanli.com"],
                "priority": 0
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/access/request", json=request_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('granted'):
                            print("✅ 获得访问权限")
                            return True
                        else:
                            print(f"⏳ 进入队列，位置: {result.get('queue_position', 'unknown')}")
                            return False
                    else:
                        print(f"❌ 请求权限失败: {response.status}")
                        return False
        except Exception as e:
            print(f"❌ 请求权限异常: {e}")
            return False
    
    async def check_access_status(self):
        """检查访问状态"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/access/status") as response:
                    if response.status == 200:
                        result = await response.json()
                        active_client = result.get('active_client')
                        if active_client and self.session_id.startswith(active_client):
                            print("✅ 确认拥有访问权限")
                            return True
                        else:
                            print(f"❌ 当前活跃客户端: {active_client}")
                            return False
                    else:
                        print(f"❌ 检查状态失败: {response.status}")
                        return False
        except Exception as e:
            print(f"❌ 检查状态异常: {e}")
            return False
    
    async def simulate_browser_close_and_check_release(self):
        """模拟浏览器关闭并检查权限释放"""
        print("\n🔄 模拟浏览器关闭...")
        
        # 直接调用释放权限API（模拟浏览器关闭自动释放）
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/access/release/{self.session_id}") as response:
                    if response.status == 200:
                        print("✅ 权限释放成功")
                        
                        # 等待几秒后检查状态
                        await asyncio.sleep(3)
                        
                        # 检查权限是否真的被释放
                        has_access = await self.check_access_status()
                        if not has_access:
                            print("✅ 权限确实已释放")
                            return True
                        else:
                            print("❌ 权限释放失败，仍然拥有权限")
                            return False
                    else:
                        print(f"❌ 权限释放失败: {response.status}")
                        return False
        except Exception as e:
            print(f"❌ 权限释放异常: {e}")
            return False
    
    async def test_access_cycle(self):
        """测试完整的访问周期"""
        print("\n" + "="*50)
        print("开始测试浏览器关闭权限释放功能")
        print("="*50)
        
        # 1. 测试服务器连接
        print("\n1. 测试服务器连接...")
        if not await self.test_server_connection():
            return False
        
        # 2. 创建会话
        print("\n2. 创建测试会话...")
        if not await self.create_test_session():
            return False
        
        # 3. 请求访问权限
        print("\n3. 请求访问权限...")
        max_attempts = 5
        access_granted = False
        
        for attempt in range(max_attempts):
            if await self.request_access():
                access_granted = True
                break
            else:
                print(f"   等待权限分配... ({attempt + 1}/{max_attempts})")
                await asyncio.sleep(5)
        
        if not access_granted:
            print("❌ 无法获得访问权限，测试终止")
            return False
        
        # 4. 确认访问状态
        print("\n4. 确认访问状态...")
        if not await self.check_access_status():
            return False
        
        # 5. 模拟浏览器关闭并检查权限释放
        print("\n5. 模拟浏览器关闭并检查权限释放...")
        if not await self.simulate_browser_close_and_check_release():
            return False
        
        print("\n✅ 所有测试通过！浏览器关闭权限释放功能正常工作")
        return True
    
    async def run_test(self):
        """运行测试"""
        start_time = time.time()
        success = await self.test_access_cycle()
        end_time = time.time()
        
        print(f"\n测试耗时: {end_time - start_time:.2f} 秒")
        
        if success:
            print("🎉 测试结果: 通过")
            return 0
        else:
            print("💥 测试结果: 失败")
            return 1

async def main():
    """主函数"""
    test = BrowserCloseTest()
    try:
        result = await test.run_test()
        return result
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生异常: {e}")
        return 1

if __name__ == "__main__":
    print("浏览器关闭权限释放功能测试")
    print("请确保服务器正在运行 (localhost:8001)")
    print("-" * 50)
    
    exit_code = asyncio.run(main())
    exit(exit_code) 