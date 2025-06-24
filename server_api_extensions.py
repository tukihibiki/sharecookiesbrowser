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
服务器API扩展模块
为GUI管理界面提供额外的管理功能API接口
"""

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 创建API路由器
admin_router = APIRouter(prefix="/admin", tags=["admin"])

class ServerManager:
    """服务器管理类 - 为GUI提供管理功能"""
    
    def __init__(self, server_state, access_coordinator, connection_manager):
        self.server_state = server_state
        self.access_coordinator = access_coordinator
        self.connection_manager = connection_manager
        # 获取AccessCoordinator的当前设置，而不是覆盖它
        self.max_concurrent_clients = access_coordinator.max_concurrent_clients
        logger.info(f"ServerManager初始化：从AccessCoordinator获取最大并发数 = {self.max_concurrent_clients}")
        
    async def get_server_info(self) -> Dict[str, Any]:
        """获取服务器详细信息"""
        try:
            # 获取访问协调器状态
            access_status = await self.access_coordinator.get_status()
            
            # 获取连接管理器状态
            connection_count = len(self.connection_manager.active_connections)
            
            # 获取cookies信息
            cookies_info = {
                "count": len(self.server_state.global_cookies),
                "logged_in": self.server_state.is_logged_in,
                "last_updated": self.server_state.cookies_last_updated.isoformat() if self.server_state.cookies_last_updated else None
            }
            
            return {
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "access_coordinator": access_status,
                "connections": {
                    "total": connection_count,
                    "active_clients": access_status.get("active_client") is not None,
                    "queue_length": access_status.get("queue_length", 0)
                },
                "cookies": cookies_info,
                "config": {
                    "max_concurrent_clients": self.max_concurrent_clients
                }
            }
        except Exception as e:
            logger.error(f"获取服务器信息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def update_max_clients(self, max_clients: int) -> Dict[str, Any]:
        """更新最大并发客户端数"""
        try:
            if max_clients < 1 or max_clients > 10:
                raise ValueError("最大客户端数必须在1-10之间")
            
            old_value = self.max_concurrent_clients
            
            # 通过访问协调器更新设置（会自动保存到配置文件）
            self.access_coordinator.set_max_concurrent_clients(max_clients)
            
            # 同步本地设置
            self.max_concurrent_clients = max_clients
            
            logger.info(f"通过GUI更新最大并发客户端数: {old_value} -> {max_clients}")
            
            return {
                "success": True,
                "old_value": old_value,
                "new_value": max_clients,
                "message": f"最大并发客户端数已更新为 {max_clients}，配置已保存"
            }
        except Exception as e:
            logger.error(f"更新最大客户端数失败: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def kick_client(self, client_id: str, reason: str = "admin_kick") -> Dict[str, Any]:
        """踢出指定客户端"""
        try:
            # 释放客户端的访问权限
            release_result = await self.access_coordinator.release_access(client_id, reason)
            
            # 从等待队列中移除
            queue_result = await self.access_coordinator.remove_from_queue(client_id)
            
            # 断开WebSocket连接
            if client_id in self.connection_manager.active_connections:
                try:
                    websocket = self.connection_manager.active_connections[client_id]
                    await websocket.close(code=1000, reason="Admin kicked")
                except:
                    pass
                finally:
                    self.connection_manager.disconnect(client_id)
            
            logger.info(f"客户端 {client_id[:8]} 已被管理员踢出 (原因: {reason})")
            
            return {
                "success": True,
                "client_id": client_id,
                "reason": reason,
                "release_result": release_result,
                "queue_result": queue_result,
                "message": f"客户端 {client_id[:8]} 已被踢出"
            }
        except Exception as e:
            logger.error(f"踢出客户端失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def update_client_priority(self, client_id: str, priority: int) -> Dict[str, Any]:
        """更新客户端优先级"""
        try:
            # 查找客户端在队列中的位置
            old_priority = 0
            client_found = False
            
            async with self.access_coordinator.access_lock:
                for item in self.access_coordinator.waiting_queue:
                    if item["client_id"] == client_id:
                        old_priority = item["priority"]
                        item["priority"] = priority
                        client_found = True
                        break
                
                if client_found:
                    # 重新排序队列
                    self.access_coordinator.waiting_queue.sort(
                        key=lambda x: x["priority"], reverse=True
                    )
                    
                    new_position = self.access_coordinator._get_client_position(client_id)
                    
                    logger.info(f"客户端 {client_id[:8]} 优先级已更新: {old_priority} -> {priority}, 新位置: {new_position}")
                    
                    return {
                        "success": True,
                        "client_id": client_id,
                        "old_priority": old_priority,
                        "new_priority": priority,
                        "new_position": new_position,
                        "message": f"客户端优先级已更新为 {priority}"
                    }
                else:
                    raise HTTPException(status_code=404, detail="客户端不在等待队列中")
        except Exception as e:
            logger.error(f"更新客户端优先级失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def clear_cookies(self) -> Dict[str, Any]:
        """清空所有Cookies"""
        try:
            old_count = len(self.server_state.global_cookies)
            
            self.server_state.global_cookies = []
            self.server_state.is_logged_in = False
            self.server_state.cookies_last_updated = datetime.now()
            
            # 保存到磁盘
            await self.server_state.save_cookies_to_disk()
            
            # 通知所有客户端
            notification = {
                "type": "cookies_cleared",
                "message": "Cookies已被管理员清空",
                "timestamp": datetime.now().isoformat()
            }
            await self.connection_manager.broadcast(json.dumps(notification))
            
            logger.info(f"管理员清空了所有Cookies (原有 {old_count} 个)")
            
            return {
                "success": True,
                "cleared_count": old_count,
                "message": f"已清空 {old_count} 个Cookies"
            }
        except Exception as e:
            logger.error(f"清空Cookies失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def import_cookies(self, cookies_data: List[Dict]) -> Dict[str, Any]:
        """导入Cookies"""
        try:
            old_count = len(self.server_state.global_cookies)
            
            # 验证cookies格式
            valid_cookies = []
            for cookie in cookies_data:
                if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
                    valid_cookies.append(cookie)
            
            if not valid_cookies:
                raise ValueError("没有有效的cookies数据")
            
            self.server_state.global_cookies = valid_cookies
            self.server_state.is_logged_in = True
            self.server_state.cookies_last_updated = datetime.now()
            
            # 保存到磁盘
            await self.server_state.save_cookies_to_disk()
            
            # 通知所有客户端
            notification = {
                "type": "cookies_updated",
                "message": f"Cookies已更新 ({len(valid_cookies)} 个)",
                "timestamp": datetime.now().isoformat()
            }
            await self.connection_manager.broadcast(json.dumps(notification))
            
            logger.info(f"管理员导入了 {len(valid_cookies)} 个Cookies (原有 {old_count} 个)")
            
            return {
                "success": True,
                "imported_count": len(valid_cookies),
                "old_count": old_count,
                "message": f"已导入 {len(valid_cookies)} 个Cookies"
            }
        except Exception as e:
            logger.error(f"导入Cookies失败: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def smart_import_cookies(self, smart_data: Dict[str, Any]) -> Dict[str, Any]:
        """智能导入和管理Cookies"""
        try:
            cookies_by_domain = smart_data.get("cookies_by_domain", {})
            analysis_result = smart_data.get("analysis", {})
            strategy = smart_data.get("strategy", {})
            
            logger.info(f"智能导入cookies - 网站类型: {analysis_result.get('site_type', {}).get('type', 'unknown')}")
            logger.info(f"应用策略: {strategy.get('name', 'unknown')}")
            
            # 统计信息
            total_cookies = sum(len(cookies) for cookies in cookies_by_domain.values())
            main_domain = analysis_result.get("domain", "")
            
            if not total_cookies:
                raise ValueError("没有有效的cookies数据")
            
            # 根据策略处理cookies
            strategy_result = await self._apply_cookies_strategy(cookies_by_domain, strategy, analysis_result)
            
            # 合并所有域名的cookies到现有的全局cookies中
            new_cookies = []
            for domain, cookies in cookies_by_domain.items():
                for cookie in cookies:
                    # 确保cookie有domain字段
                    if 'domain' not in cookie:
                        cookie['domain'] = domain
                    new_cookies.append(cookie)
            
            if new_cookies:
                old_count = len(self.server_state.global_cookies)
                
                # 智能合并：避免重复，优先保留新cookies
                existing_cookies = self.server_state.global_cookies.copy()
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
                
                self.server_state.global_cookies = merged_cookies
                
                logger.info(f"🔄 智能合并cookies: 原有{old_count}个 + 新增{len(new_cookies)}个 = 合并后{len(merged_cookies)}个")
                self.server_state.is_logged_in = True
                self.server_state.cookies_last_updated = datetime.now()
                
                # 更新可用域名
                self.server_state.update_available_domains()
                
                # 保存到磁盘
                await self.server_state.save_cookies_to_disk()
                
                # 保存智能分析结果
                await self._save_smart_analysis(analysis_result, strategy, cookies_by_domain)
                
                # 根据策略决定通知方式
                notification_type = self._get_notification_type(strategy)
                notification = {
                    "type": notification_type,
                    "message": f"智能合并cookies (新增{len(new_cookies)}个，总计{len(merged_cookies)}个，{len(cookies_by_domain)}个域名) - {strategy.get('name', '标准模式')}",
                    "strategy": strategy,
                    "domain": main_domain,
                    "total_cookies": len(merged_cookies),
                    "new_cookies": len(new_cookies),
                    "domains_count": len(cookies_by_domain),
                    "timestamp": datetime.now().isoformat()
                }
                
                # 根据共享策略决定是否广播
                if strategy.get("sharing") != "none":
                    await self.connection_manager.broadcast(json.dumps(notification))
                
                logger.info(f"智能导入完成 - 主域名: {main_domain}, 总Cookies: {len(merged_cookies)}个 (新增{len(new_cookies)}个，{len(cookies_by_domain)}个域名), 策略: {strategy.get('name')}")
                
                return {
                    "success": True,
                    "total_domains": len(cookies_by_domain),
                    "total_cookies": len(merged_cookies),
                    "main_domain": main_domain,
                    "new_cookies_count": len(new_cookies),
                    "merged_cookies_count": len(merged_cookies),
                    "old_count": old_count,
                    "strategy_applied": strategy_result,
                    "analysis": analysis_result,
                    "cookies_by_domain": {domain: len(cookies) for domain, cookies in cookies_by_domain.items()},
                    "message": f"智能合并成功 - {strategy.get('name')} 策略已应用，新增 {len(new_cookies)} 个cookies，总计 {len(merged_cookies)} 个cookies"
                }
            else:
                raise ValueError("没有有效的cookies数据")
                
        except Exception as e:
            logger.error(f"智能导入Cookies失败: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def delete_selected_cookies(self, cookies_to_delete: List[Dict]) -> Dict[str, Any]:
        """删除选中的Cookies"""
        try:
            if not cookies_to_delete:
                raise ValueError("没有指定要删除的cookies")
            
            # 获取当前cookies
            current_cookies = self.server_state.global_cookies.copy()
            original_count = len(current_cookies)
            
            if original_count == 0:
                return {
                    "success": True,
                    "deleted_count": 0,
                    "remaining_count": 0,
                    "message": "当前没有cookies可以删除"
                }
            
            # 创建要删除的cookies的匹配键
            delete_keys = set()
            for cookie_to_delete in cookies_to_delete:
                # 使用name+domain+path作为唯一标识
                key = f"{cookie_to_delete.get('name', '')}_{cookie_to_delete.get('domain', '')}_{cookie_to_delete.get('path', '/')}"
                delete_keys.add(key)
            
            # 过滤出要保留的cookies
            remaining_cookies = []
            deleted_count = 0
            
            for cookie in current_cookies:
                cookie_key = f"{cookie.get('name', '')}_{cookie.get('domain', '')}_{cookie.get('path', '/')}"
                
                if cookie_key in delete_keys:
                    deleted_count += 1
                    logger.info(f"删除cookie: {cookie.get('name')} (域名: {cookie.get('domain')})")
                else:
                    remaining_cookies.append(cookie)
            
            # 更新全局cookies
            self.server_state.global_cookies = remaining_cookies
            remaining_count = len(remaining_cookies)
            
            # 更新登录状态
            if remaining_count == 0:
                self.server_state.is_logged_in = False
                logger.info("所有cookies已删除，登录状态重置为未登录")
            
            # 更新时间戳
            self.server_state.cookies_last_updated = datetime.now()
            
            # 更新可用域名
            self.server_state.update_available_domains()
            
            # 保存到磁盘
            await self.server_state.save_cookies_to_disk()
            
            # 广播更新通知
            notification = {
                "type": "cookies_deleted",
                "message": f"管理员删除了 {deleted_count} 个cookies，剩余 {remaining_count} 个",
                "deleted_count": deleted_count,
                "remaining_count": remaining_count,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.connection_manager.broadcast(json.dumps(notification))
            
            logger.info(f"✅ cookies删除完成: 删除 {deleted_count} 个，剩余 {remaining_count} 个")
            
            return {
                "success": True,
                "deleted_count": deleted_count,
                "remaining_count": remaining_count,
                "original_count": original_count,
                "message": f"成功删除 {deleted_count} 个cookies，剩余 {remaining_count} 个cookies"
            }
            
        except Exception as e:
            logger.error(f"删除cookies失败: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _apply_cookies_strategy(self, cookies_by_domain: Dict, strategy: Dict, analysis: Dict) -> Dict:
        """应用cookies策略"""
        try:
            strategy_name = strategy.get("name", "未知策略")
            sharing_level = strategy.get("sharing", "medium")
            security_level = strategy.get("security", "medium")
            lifetime = strategy.get("lifetime", 3600)
            
            # 根据策略调整访问协调器设置
            if sharing_level == "high":
                # 高共享：允许更多并发
                max_clients = min(self.max_concurrent_clients + 1, 5)
            elif sharing_level == "none":
                # 无共享：限制为1个客户端
                max_clients = 1
            else:
                # 中等共享：保持当前设置
                max_clients = self.max_concurrent_clients
            
            # 如果需要调整并发数
            if max_clients != self.max_concurrent_clients:
                await self.update_max_clients(max_clients)
                logger.info(f"根据策略 {strategy_name} 调整最大并发数: {self.max_concurrent_clients} -> {max_clients}")
            
            # 记录策略应用
            strategy_log = {
                "strategy_name": strategy_name,
                "sharing_level": sharing_level,
                "security_level": security_level,
                "lifetime_seconds": lifetime,
                "max_clients_adjusted": max_clients,
                "domain_count": len(cookies_by_domain),
                "applied_at": datetime.now().isoformat()
            }
            
            return strategy_log
            
        except Exception as e:
            logger.error(f"应用cookies策略失败: {e}")
            return {"error": str(e)}
    
    async def _save_smart_analysis(self, analysis: Dict, strategy: Dict, cookies_by_domain: Dict):
        """保存智能分析结果到磁盘"""
        try:
            analysis_data = {
                "analysis_result": analysis,
                "applied_strategy": strategy,
                "cookies_summary": {
                    domain: len(cookies) for domain, cookies in cookies_by_domain.items()
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # 这里可以保存到特定文件，暂时记录到日志
            logger.info(f"智能分析结果已记录: {analysis_data}")
            
        except Exception as e:
            logger.error(f"保存智能分析结果失败: {e}")
    
    def _get_notification_type(self, strategy: Dict) -> str:
        """根据策略获取通知类型"""
        sharing = strategy.get("sharing", "medium")
        security = strategy.get("security", "medium")
        
        if sharing == "none":
            return "cookies_private_update"
        elif security == "highest":
            return "cookies_secure_update"
        elif sharing == "high":
            return "cookies_shared_update"
        else:
            return "cookies_updated"

# 全局服务器管理器实例（将在main应用中初始化）
server_manager: Optional[ServerManager] = None
server_state_ref = None

def init_server_manager(server_state, access_coordinator, connection_manager):
    """初始化服务器管理器"""
    global server_manager, server_state_ref
    server_manager = ServerManager(server_state, access_coordinator, connection_manager)
    server_state_ref = server_state
    logger.info(f"服务器管理器已初始化，最大并发数: {server_manager.max_concurrent_clients}")

def verify_admin_key(key: str) -> bool:
    """验证管理员密钥"""
    if server_state_ref:
        return server_state_ref.verify_admin_key(key)
    return False

# ================ API路由定义 ================

@admin_router.get("/server/info")
async def get_server_info(x_admin_key: str = Header(..., description="管理员密钥")):
    """获取服务器详细信息"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    # 验证管理员密钥
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    return await server_manager.get_server_info()

@admin_router.post("/server/config/max-clients")
async def update_max_clients(
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """更新最大并发客户端数"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    # 验证管理员密钥
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    try:
        data = await request.json()
        max_clients = data.get("max_clients")
        
        if not isinstance(max_clients, int):
            raise ValueError("max_clients必须是整数")
        
        return await server_manager.update_max_clients(max_clients)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@admin_router.post("/clients/{client_id}/kick")
async def kick_client(
    client_id: str,
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """踢出指定客户端"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    # 验证管理员密钥
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    try:
        data = await request.json()
        reason = data.get("reason", "admin_kick")
        
        return await server_manager.kick_client(client_id, reason)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@admin_router.post("/clients/{client_id}/priority")
async def update_client_priority(
    client_id: str,
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """更新客户端优先级"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    try:
        data = await request.json()
        priority = data.get("priority")
        
        if not isinstance(priority, int):
            raise ValueError("priority必须是整数")
        
        return await server_manager.update_client_priority(client_id, priority)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@admin_router.delete("/cookies")
async def clear_cookies(x_admin_key: str = Header(..., description="管理员密钥")):
    """清空所有Cookies"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    # 验证管理员密钥
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    return await server_manager.clear_cookies()

@admin_router.post("/cookies/import")
async def import_cookies(
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """导入Cookies"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    try:
        data = await request.json()
        cookies_data = data.get("cookies", [])
        
        if not isinstance(cookies_data, list):
            raise ValueError("cookies必须是数组格式")
        
        return await server_manager.import_cookies(cookies_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@admin_router.post("/cookies/smart-import")
async def smart_import_cookies(
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """智能导入和管理Cookies"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    # 验证管理员密钥
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    try:
        smart_data = await request.json()
        
        # 验证必要字段
        required_fields = ["cookies_by_domain", "analysis", "strategy"]
        for field in required_fields:
            if field not in smart_data:
                raise ValueError(f"缺少必要字段: {field}")
        
        return await server_manager.smart_import_cookies(smart_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@admin_router.post("/cookies/delete")
async def delete_selected_cookies(
    request: Request,
    x_admin_key: str = Header(..., description="管理员密钥")
):
    """删除选中的Cookies"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    # 验证管理员密钥
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    try:
        data = await request.json()
        cookies_to_delete = data.get("cookies_to_delete", [])
        
        if not isinstance(cookies_to_delete, list):
            raise ValueError("cookies_to_delete必须是数组格式")
        
        if not cookies_to_delete:
            raise ValueError("没有指定要删除的cookies")
        
        return await server_manager.delete_selected_cookies(cookies_to_delete)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@admin_router.get("/clients/detailed")
async def get_detailed_clients_info(x_admin_key: str = Header(..., description="管理员密钥")):
    """获取详细的客户端信息（包括IP地址等）"""
    if not server_manager:
        raise HTTPException(status_code=500, detail="服务器管理器未初始化")
    
    # 验证管理员密钥
    if not verify_admin_key(x_admin_key):
        raise HTTPException(status_code=401, detail="无效的管理员密钥")
    
    try:
        # 获取基本状态
        basic_status = await server_manager.access_coordinator.get_status()
        
        # 添加连接详情
        detailed_clients = []
        
        # 处理活跃客户端
        if basic_status.get("active_client"):
            client_id = basic_status["active_client"]
            client_info = basic_status.get("active_client_info", {})
            
            # 获取连接信息
            connection_info = server_manager.connection_manager.get_client_info(client_id)
            ip_address = connection_info.get("ip_address", "unknown")
            connect_time = connection_info.get("connect_time")
            
            detailed_clients.append({
                "client_id": client_id,
                "status": "active",
                "ip_address": ip_address,
                "connect_time": connect_time.isoformat() if connect_time else "unknown",
                "queue_time": 0,
                "usage_time": client_info.get("usage_minutes", 0),
                "last_activity": client_info.get("inactive_minutes", 0),
                "priority": 999,  # 活跃客户端最高优先级
                "position": 0
            })
        
        # 处理排队客户端
        for client_info in basic_status.get("queue_details", []):
            client_id = client_info["client_id"]
            
            # 获取连接信息
            connection_info = server_manager.connection_manager.get_client_info(client_id)
            ip_address = connection_info.get("ip_address", "unknown")
            connect_time = connection_info.get("connect_time")
            
            detailed_clients.append({
                "client_id": client_id,
                "status": "queued",
                "ip_address": ip_address,
                "connect_time": connect_time.isoformat() if connect_time else "unknown",
                "queue_time": client_info["wait_minutes"],
                "usage_time": 0,
                "last_activity": "排队中",
                "priority": client_info.get("priority", 0),
                "position": client_info["position"]
            })
        
        return {
            "clients": detailed_clients,
            "summary": {
                "total": len(detailed_clients),
                "active": 1 if basic_status.get("active_client") else 0,
                "queued": len(basic_status.get("queue_details", [])),
                "max_concurrent": server_manager.max_concurrent_clients
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取详细客户端信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 