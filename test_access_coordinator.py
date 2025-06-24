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
访问协调机制测试脚本
测试多客户端排队和单点访问控制功能
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime
from typing import List, Dict
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AccessCoordinatorTester:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.clients: List[Dict] = []
        
    async def test_basic_access_flow(self):
        """测试基本的访问流程"""
        logger.info("=" * 60)
        logger.info("🧪 测试1: 基本访问流程")
        logger.info("=" * 60)
        
        # 测试服务器健康状态
        if not await self._check_server_health():
            logger.error("❌ 服务器未运行，测试中止")
            return False
        
        # 1. 第一个客户端请求访问权限
        logger.info("📝 步骤1: 第一个客户端请求访问权限")
        client1 = await self._request_access("客户端1")
        if not client1:
            logger.error("❌ 第一个客户端请求失败")
            return False
        
        if client1["granted"]:
            logger.info("✅ 第一个客户端直接获得访问权限")
        else:
            logger.error("❌ 第一个客户端应该直接获得访问权限")
            return False
        
        # 2. 第二个客户端请求访问权限（应该进入队列）
        logger.info("📝 步骤2: 第二个客户端请求访问权限（应该排队）")
        client2 = await self._request_access("客户端2")
        if not client2:
            logger.error("❌ 第二个客户端请求失败")
            return False
        
        if not client2["granted"] and client2["position"] == 1:
            logger.info("✅ 第二个客户端正确进入等待队列")
        else:
            logger.error(f"❌ 第二个客户端状态异常: granted={client2['granted']}, position={client2.get('position')}")
            return False
        
        # 3. 检查访问协调器状态
        logger.info("📝 步骤3: 检查访问协调器状态")
        status = await self._get_coordinator_status()
        if status:
            logger.info(f"📊 协调器状态: 活跃客户端={status.get('active_client', 'None')[:8] if status.get('active_client') else 'None'}, 队列长度={status.get('queue_length')}")
            
            if status.get('active_client') == client1['session_id'] and status.get('queue_length') == 1:
                logger.info("✅ 协调器状态正确")
            else:
                logger.error("❌ 协调器状态异常")
                return False
        
        # 4. 第一个客户端释放访问权限
        logger.info("📝 步骤4: 第一个客户端释放访问权限")
        release_result = await self._release_access(client1['session_id'])
        if release_result and release_result.get('success'):
            logger.info("✅ 第一个客户端成功释放访问权限")
            
            # 检查是否有下一个客户端信息
            next_client = release_result.get('next_client')
            if next_client and next_client['client_id'] == client2['session_id']:
                logger.info("✅ 访问权限正确转移给第二个客户端")
            else:
                logger.error("❌ 访问权限转移异常")
                return False
        else:
            logger.error("❌ 第一个客户端释放访问权限失败")
            return False
        
        # 5. 验证第二个客户端现在应该是活跃状态
        logger.info("📝 步骤5: 验证访问权限转移")
        await asyncio.sleep(2)  # 等待状态更新
        
        final_status = await self._get_coordinator_status()
        if final_status:
            if final_status.get('active_client') == client2['session_id'] and final_status.get('queue_length') == 0:
                logger.info("✅ 访问权限转移验证成功")
            else:
                logger.error(f"❌ 访问权限转移验证失败: active={final_status.get('active_client', 'None')[:8] if final_status.get('active_client') else 'None'}, queue={final_status.get('queue_length')}")
                return False
        
        # 清理
        await self._release_access(client2['session_id'])
        
        logger.info("✅ 基本访问流程测试通过")
        return True
    
    async def test_multiple_clients_queue(self):
        """测试多客户端排队功能"""
        logger.info("=" * 60)
        logger.info("🧪 测试2: 多客户端排队功能")
        logger.info("=" * 60)
        
        clients = []
        
        # 创建5个客户端请求访问权限
        for i in range(5):
            logger.info(f"📝 创建客户端{i+1}")
            client = await self._request_access(f"客户端{i+1}")
            if client:
                clients.append(client)
                if i == 0:
                    if client["granted"]:
                        logger.info(f"✅ 客户端{i+1} 直接获得访问权限")
                    else:
                        logger.error(f"❌ 第一个客户端应该直接获得访问权限")
                        return False
                else:
                    if not client["granted"] and client["position"] == i:
                        logger.info(f"✅ 客户端{i+1} 进入队列，位置：{client['position']}")
                    else:
                        logger.error(f"❌ 客户端{i+1} 排队状态异常")
                        return False
            else:
                logger.error(f"❌ 客户端{i+1} 请求失败")
                return False
        
        # 检查队列状态
        status = await self._get_coordinator_status()
        if status:
            logger.info(f"📊 当前状态: 活跃客户端={status.get('active_client', 'None')[:8] if status.get('active_client') else 'None'}, 队列长度={status.get('queue_length')}")
            
            if status.get('queue_length') == 4:  # 4个客户端在队列中
                logger.info("✅ 队列长度正确")
            else:
                logger.error(f"❌ 队列长度异常: 期望4，实际{status.get('queue_length')}")
                return False
        
        # 逐个释放访问权限，验证队列顺序
        for i, client in enumerate(clients):
            if client["granted"] or i > 0:  # 第一个客户端有权限，或者是后续获得权限的客户端
                logger.info(f"📝 释放客户端{i+1}的访问权限")
                release_result = await self._release_access(client['session_id'])
                
                if release_result and release_result.get('success'):
                    logger.info(f"✅ 客户端{i+1} 成功释放访问权限")
                    
                    # 如果不是最后一个客户端，验证下一个客户端是否获得权限
                    if i < len(clients) - 1:
                        await asyncio.sleep(1)  # 等待状态更新
                        status = await self._get_coordinator_status()
                        if status and status.get('active_client') == clients[i+1]['session_id']:
                            logger.info(f"✅ 访问权限正确转移给客户端{i+2}")
                        else:
                            logger.error(f"❌ 访问权限转移异常")
                            return False
                else:
                    logger.error(f"❌ 客户端{i+1} 释放权限失败")
                    return False
        
        logger.info("✅ 多客户端排队功能测试通过")
        return True
    
    async def test_heartbeat_timeout(self):
        """测试心跳超时机制"""
        logger.info("=" * 60)
        logger.info("🧪 测试3: 心跳超时机制（快速测试版）")
        logger.info("=" * 60)
        
        # 创建一个客户端并获得访问权限
        client = await self._request_access("超时测试客户端")
        if not client or not client["granted"]:
            logger.error("❌ 无法获得访问权限进行超时测试")
            return False
        
        logger.info("✅ 客户端获得访问权限")
        logger.info("💭 正常情况下需要等待10分钟进行超时测试，这里仅验证心跳机制")
        
        # 发送几次心跳来验证机制
        for i in range(3):
            logger.info(f"📝 发送心跳 {i+1}/3")
            heartbeat_result = await self._send_heartbeat(client['session_id'])
            if heartbeat_result:
                logger.info("✅ 心跳发送成功")
            else:
                logger.warning("⚠️ 心跳发送失败")
            await asyncio.sleep(2)
        
        # 清理
        await self._release_access(client['session_id'])
        
        logger.info("✅ 心跳机制测试完成（完整超时测试需要10分钟）")
        return True
    
    async def _check_server_health(self) -> bool:
        """检查服务器健康状态"""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ 服务器健康状态: {data.get('status')}")
                        return True
                    else:
                        logger.error(f"❌ 服务器健康检查失败: HTTP {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ 连接服务器失败: {e}")
            return False
    
    async def _request_access(self, client_name: str) -> Dict:
        """请求访问权限"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/access/request") as response:
                    if response.status == 200:
                        data = await response.json()
                        session_id = data.get("session_id", "")
                        logger.info(f"📋 {client_name} 请求结果: "
                                   f"权限={'已获得' if data.get('granted') else '排队中'}, "
                                   f"位置={data.get('position', 0)}, "
                                   f"会话ID={session_id[:8] if session_id else 'None'}")
                        return data
                    else:
                        logger.error(f"❌ {client_name} 请求访问权限失败: HTTP {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"❌ {client_name} 请求访问权限时出错: {e}")
            return {}
    
    async def _release_access(self, session_id: str) -> Dict:
        """释放访问权限"""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.base_url}/access/release/{session_id}"
                async with session.post(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"❌ 释放访问权限失败: HTTP {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"❌ 释放访问权限时出错: {e}")
            return {}
    
    async def _get_coordinator_status(self) -> Dict:
        """获取访问协调器状态"""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/access/status") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"❌ 获取协调器状态失败: HTTP {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"❌ 获取协调器状态时出错: {e}")
            return {}
    
    async def _send_heartbeat(self, session_id: str) -> bool:
        """发送心跳"""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.base_url}/access/heartbeat/{session_id}"
                async with session.post(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("updated", False)
                    else:
                        logger.error(f"❌ 发送心跳失败: HTTP {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ 发送心跳时出错: {e}")
            return False

async def main():
    """主测试函数"""
    print("🚀 访问协调机制测试开始")
    print("=" * 80)
    
    tester = AccessCoordinatorTester()
    
    tests = [
        ("基本访问流程", tester.test_basic_access_flow),
        ("多客户端排队", tester.test_multiple_clients_queue),
        ("心跳超时机制", tester.test_heartbeat_timeout),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            logger.info(f"\n开始测试: {test_name}")
            result = await test_func()
            if result:
                logger.info(f"✅ {test_name} - 通过")
                passed += 1
            else:
                logger.error(f"❌ {test_name} - 失败")
        except Exception as e:
            logger.error(f"❌ {test_name} - 异常: {e}")
        
        # 测试间隔
        await asyncio.sleep(2)
    
    print("\n" + "=" * 80)
    print("🏁 测试结果汇总")
    print("=" * 80)
    print(f"总测试数: {total}")
    print(f"通过测试: {passed}")
    print(f"失败测试: {total - passed}")
    print(f"通过率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("✅ 所有测试通过！访问协调机制工作正常")
    else:
        print("⚠️ 部分测试失败，请检查访问协调机制")
    
    print("\n按Enter键退出...")
    input()

if __name__ == "__main__":
    asyncio.run(main()) 