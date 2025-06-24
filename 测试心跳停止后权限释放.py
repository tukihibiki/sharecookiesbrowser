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
测试心跳停止后权限释放功能

模拟心跳监控停止的情况，验证独立权限监控是否能正常工作
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

class HeartbeatStopTest:
    def __init__(self):
        self.base_url = "http://localhost:8001"
        self.session_id = None
    
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
    
    async def simulate_heartbeat_failure(self):
        """模拟心跳失败（通过发送错误的会话ID）"""
        print("\n🔄 模拟心跳失败...")
        
        # 发送一个错误的会话ID来模拟心跳失败
        fake_session_id = "fake_session_12345"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/access/heartbeat/{fake_session_id}") as response:
                    print(f"💓 模拟心跳请求结果: HTTP {response.status}")
                    if response.status != 200:
                        print("✅ 成功模拟心跳失败")
                        return True
                    else:
                        print("❌ 心跳请求意外成功")
                        return False
        except Exception as e:
            print(f"❌ 心跳模拟异常: {e}")
            return False
    
    async def wait_for_auto_release(self, timeout_seconds=30):
        """等待自动权限释放"""
        print(f"\n⏰ 等待权限自动释放（最多等待{timeout_seconds}秒）...")
        
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout_seconds:
            check_count += 1
            has_access = await self.check_access_status()
            
            if not has_access:
                elapsed = time.time() - start_time
                print(f"✅ 权限已在 {elapsed:.1f} 秒后自动释放！")
                print(f"   检查次数: {check_count}")
                return True
            
            print(f"   检查 {check_count}: 权限仍然存在，继续等待...")
            await asyncio.sleep(2)  # 每2秒检查一次
        
        print(f"❌ 等待 {timeout_seconds} 秒后权限仍未释放")
        return False
    
    async def test_heartbeat_stop_scenario(self):
        """测试心跳停止场景"""
        print("\n" + "="*60)
        print("测试场景：心跳监控停止后的权限释放功能")
        print("="*60)
        
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
        
        # 5. 模拟心跳失败
        print("\n5. 模拟心跳失败...")
        if not await self.simulate_heartbeat_failure():
            return False
        
        print("\n💡 说明：")
        print("   - 正常情况下，心跳失败会导致心跳监控停止")
        print("   - 但是新的独立权限监控任务应该继续工作")
        print("   - 它会检测到客户端异常并自动释放权限")
        
        # 6. 等待权限自动释放
        print("\n6. 等待权限自动释放...")
        if await self.wait_for_auto_release(30):
            print("\n✅ 测试通过！独立权限监控正常工作")
            return True
        else:
            print("\n❌ 测试失败！权限未能自动释放")
            return False
    
    async def run_test(self):
        """运行测试"""
        start_time = time.time()
        success = await self.test_heartbeat_stop_scenario()
        end_time = time.time()
        
        print(f"\n测试耗时: {end_time - start_time:.2f} 秒")
        
        if success:
            print("🎉 测试结果: 通过")
            print("🔧 修复效果: 即使心跳停止，独立权限监控也能正常工作")
            return 0
        else:
            print("💥 测试结果: 失败")
            print("⚠️ 问题: 心跳停止后无法自动释放权限")
            return 1

async def main():
    """主函数"""
    test = HeartbeatStopTest()
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
    print("心跳停止后权限释放功能测试")
    print("请确保服务器正在运行 (localhost:8001)")
    print("-" * 60)
    
    exit_code = asyncio.run(main())
    exit(exit_code) 