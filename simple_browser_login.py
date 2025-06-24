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
智能浏览器登录工具
自动分析网页并智能管理cookies
"""

import asyncio
import json
import requests
from pathlib import Path
from playwright.async_api import async_playwright
import argparse
import sys
import re
from urllib.parse import urlparse
from typing import Dict, List, Optional, Tuple
import time

class WebsiteAnalyzer:
    """网站分析器 - 智能识别网站类型和cookies策略"""
    
    def __init__(self):
        # 网站模式识别规则
        self.site_patterns = {
            'enterprise_query': {
                'domains': ['alphalawyer.cn', 'qichacha.com', 'tianyancha.com', 'enterprise.com'],
                'keywords': ['企业查询', '工商信息', '企业信息', '公司查询', '企业征信', '法务'],
                'login_keywords': ['微信登录', '企业登录', '用户登录'],
                'strategy': 'shared_enterprise'
            },
            'legal_service': {
                'domains': ['lawfirm.com', 'legal.com', 'lawyer.com'],
                'keywords': ['法律服务', '律师', '法务', '法律咨询', '案件'],
                'login_keywords': ['律师登录', '专业登录', '会员登录'],
                'strategy': 'professional_shared'
            },
            'government': {
                'domains': ['gov.cn', '.gov.', 'court.gov.cn'],
                'keywords': ['政府', '法院', '政务', '官方', '行政'],
                'login_keywords': ['统一登录', '实名登录', '政务登录'],
                'strategy': 'secure_isolated'
            },
            'finance': {
                'domains': ['bank.com', 'finance.com', 'pay.com'],
                'keywords': ['银行', '支付', '金融', '财务', '账户'],
                'login_keywords': ['网银登录', '安全登录', '实名登录'],
                'strategy': 'secure_isolated'
            },
            'general_business': {
                'domains': ['*.com', '*.cn', '*.net'],
                'keywords': ['登录', '注册', '会员', '用户'],
                'login_keywords': ['用户登录', '会员登录', '账号登录'],
                'strategy': 'standard_shared'
            }
        }
        
        # Cookies策略配置
        self.strategies = {
            'shared_enterprise': {
                'name': '企业查询共享模式',
                'sharing': 'high',
                'security': 'medium',
                'lifetime': 7200,  # 2小时
                'description': '适用于企业查询类网站，支持多客户端共享'
            },
            'professional_shared': {
                'name': '专业服务共享模式', 
                'sharing': 'medium',
                'security': 'high',
                'lifetime': 3600,  # 1小时
                'description': '适用于专业服务网站，限制并发数的共享'
            },
            'secure_isolated': {
                'name': '安全隔离模式',
                'sharing': 'none',
                'security': 'highest',
                'lifetime': 1800,  # 30分钟
                'description': '适用于政府、金融等高安全要求网站，不共享'
            },
            'standard_shared': {
                'name': '标准共享模式',
                'sharing': 'medium',
                'security': 'medium', 
                'lifetime': 3600,  # 1小时
                'description': '适用于一般商务网站的标准共享策略'
            }
        }
    
    async def analyze_website(self, page, url: str) -> Dict:
        """分析网站并返回策略建议"""
        try:
            print(f"正在分析网站: {url}")
            
            # 解析URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            # 获取页面标题和内容
            title = await page.title()
            page_text = await page.inner_text('body')
            
            # 检测网站类型
            site_type = self._detect_site_type(domain, title, page_text)
            
            # 获取策略
            strategy = self.strategies.get(site_type['strategy'], self.strategies['standard_shared'])
            
            analysis_result = {
                'url': url,
                'domain': domain,
                'title': title,
                'site_type': site_type,
                'strategy': strategy,
                'timestamp': time.time()
            }
            
            print(f"网站分析完成:")
            print(f"  网站类型: {site_type['type']}")
            print(f"  推荐策略: {strategy['name']}")
            print(f"  安全级别: {strategy['security']}")
            print(f"  共享策略: {strategy['sharing']}")
            
            return analysis_result
            
        except Exception as e:
            print(f"网站分析失败: {e}")
            # 返回默认策略
            return {
                'url': url,
                'domain': urlparse(url).netloc,
                'title': 'Unknown',
                'site_type': {'type': 'unknown', 'strategy': 'standard_shared'},
                'strategy': self.strategies['standard_shared'],
                'timestamp': time.time()
            }
    
    def _detect_site_type(self, domain: str, title: str, content: str) -> Dict:
        """检测网站类型"""
        content_lower = content.lower()
        title_lower = title.lower()
        
        # 按优先级检查网站类型
        for site_type, config in self.site_patterns.items():
            # 检查域名匹配
            if self._match_domains(domain, config['domains']):
                return {'type': site_type, 'strategy': config['strategy'], 'confidence': 0.9}
            
            # 检查关键词匹配
            keyword_score = self._calculate_keyword_score(
                content_lower + ' ' + title_lower, 
                config['keywords'] + config['login_keywords']
            )
            
            if keyword_score > 0.6:
                return {'type': site_type, 'strategy': config['strategy'], 'confidence': keyword_score}
        
        # 默认返回通用商务类型
        return {'type': 'general_business', 'strategy': 'standard_shared', 'confidence': 0.3}
    
    def _match_domains(self, domain: str, patterns: List[str]) -> bool:
        """检查域名是否匹配模式"""
        for pattern in patterns:
            if pattern.startswith('*'):
                suffix = pattern[1:]
                if domain.endswith(suffix):
                    return True
            elif pattern in domain:
                return True
        return False
    
    def _calculate_keyword_score(self, text: str, keywords: List[str]) -> float:
        """计算关键词匹配分数"""
        matches = 0
        for keyword in keywords:
            if keyword in text:
                matches += 1
        return matches / len(keywords) if keywords else 0


class SmartBrowserLogin:
    """智能浏览器登录工具"""
    
    def __init__(self, server_url="http://localhost:8001"):
        self.server_url = server_url
        self.analyzer = WebsiteAnalyzer()
        self.visited_urls = []
        self.analysis_results = []
        
    async def start_smart_login(self):
        """启动智能登录流程"""
        print("智能浏览器登录工具")
        print("=" * 60)
        print("本工具将自动分析您访问的网站，")
        print("并根据网站类型选择最适合的cookies策略。")
        print("=" * 60)
        
        async with async_playwright() as playwright:
            # 启动浏览器
            browser = await playwright.chromium.launch(
                headless=False,
                args=['--start-maximized']
            )
            
            try:
                context = await browser.new_context(no_viewport=True)
                page = await context.new_page()
                
                # 设置页面监控
                await self._setup_comprehensive_monitoring(page, context)
                
                # 打开起始页面
                await page.goto("https://www.baidu.com")
                
                print("\n浏览器已启动！")
                print("💡 使用说明：")
                print("1. 请在浏览器中访问任何需要登录的网站")
                print("2. 完成登录操作（微信扫码、密码登录等）")
                print("3. 系统会自动检测登录状态并保存cookies")
                print("4. 支持多个网站同时登录，系统会智能分析每个网站")
                print("5. 登录完成后按回车键结束并上传所有cookies")
                print("=" * 60)
                
                # 持续监控直到用户结束
                await self._continuous_monitoring(page, context)
                
                return True
                
            except Exception as e:
                print(f"智能登录过程中出错: {e}")
                return False
            finally:
                await browser.close()

    async def _setup_comprehensive_monitoring(self, page, context):
        """设置全面的页面监控"""
        self.context = context
        self.monitored_domains = set()
        self.login_detected_domains = set()
        self.last_cookie_count = 0
        
        # 监控页面导航
        async def on_navigation(page):
            try:
                url = page.url
                if not url.startswith('data:') and not url.startswith('chrome-extension:'):
                    domain = urlparse(url).netloc
                    if domain and domain not in self.monitored_domains:
                        self.monitored_domains.add(domain)
                        print(f"🌐 检测到新域名: {domain}")
                        
                        # 延迟检测以确保页面加载完成
                        await asyncio.sleep(2)
                        await self._check_login_status(page, context)
            except Exception as e:
                print(f"导航监控错误: {e}")
        
        # 监控cookies变化
        async def on_response(response):
            try:
                # 检查是否可能是登录相关的响应
                url = response.url
                if any(keyword in url.lower() for keyword in ['login', 'auth', 'oauth', 'signin', 'wechat']):
                    print(f"🔍 检测到可能的登录响应: {url}")
                    await asyncio.sleep(1)  # 等待cookies设置
                    await self._check_login_status(page, context)
            except Exception as e:
                print(f"响应监控错误: {e}")
        
        page.on('domcontentloaded', on_navigation)
        page.on('response', on_response)

    async def _continuous_monitoring(self, page, context):
        """持续监控模式"""
        check_interval = 5  # 每5秒检查一次
        last_check_time = time.time()
        
        print("\n🔍 开始持续监控登录状态...")
        
        while True:
            try:
                # 定期检查cookies变化
                current_time = time.time()
                if current_time - last_check_time >= check_interval:
                    await self._periodic_cookie_check(page, context)
                    last_check_time = current_time
                
                # 检查用户是否要结束 (Windows兼容)
                import sys
                import msvcrt
                if msvcrt.kbhit():
                    char = msvcrt.getch().decode('utf-8', errors='ignore')
                    if char in ['\r', '\n', 'q', 'Q']:  # 回车或q键
                        print("\n用户请求结束监控...")
                        break
                
                await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"监控过程错误: {e}")
                await asyncio.sleep(5)
        
        # 最终处理所有检测到的cookies
        await self._final_cookie_processing(context)

    async def _check_login_status(self, page, context):
        """检查页面登录状态"""
        try:
            url = page.url
            domain = urlparse(url).netloc
            
            # 获取当前cookies
            current_cookies = await context.cookies()
            
            # 检查是否有新的认证cookies
            auth_cookies = [
                cookie for cookie in current_cookies 
                if any(keyword in cookie['name'].lower() 
                      for keyword in ['session', 'token', 'auth', 'user', 'login', 'jwt', 'openid'])
            ]
            
            if auth_cookies and domain not in self.login_detected_domains:
                self.login_detected_domains.add(domain)
                print(f"🎉 检测到 {domain} 的登录状态!")
                print(f"   认证cookies: {len(auth_cookies)} 个")
                
                # 分析当前网站
                analysis_result = await self.analyzer.analyze_website(page, url)
                
                # 处理cookies
                await self._process_domain_cookies(domain, current_cookies, analysis_result)
                
        except Exception as e:
            print(f"登录状态检查错误: {e}")

    async def _periodic_cookie_check(self, page, context):
        """定期检查cookies变化"""
        try:
            current_cookies = await context.cookies()
            current_count = len(current_cookies)
            
            if current_count > self.last_cookie_count:
                print(f"🍪 检测到cookies变化: {self.last_cookie_count} -> {current_count}")
                
                # 检查是否有新的认证cookies
                auth_cookies = [
                    cookie for cookie in current_cookies 
                    if any(keyword in cookie['name'].lower() 
                          for keyword in ['session', 'token', 'auth', 'user', 'login'])
                ]
                
                if auth_cookies:
                    await self._check_login_status(page, context)
                
                self.last_cookie_count = current_count
                
        except Exception as e:
            print(f"定期检查错误: {e}")

    async def _process_domain_cookies(self, domain, all_cookies, analysis_result):
        """处理特定域名的cookies"""
        try:
            # 筛选该域名相关的cookies
            domain_cookies = [
                cookie for cookie in all_cookies 
                if domain in cookie.get('domain', '') or cookie.get('domain', '').endswith(f'.{domain}')
            ]
            
            if domain_cookies:
                print(f"   检测到 {domain} 的 {len(domain_cookies)} 个cookies")
                
                # 保存到本地文件
                await self._save_domain_cookies(domain, domain_cookies, analysis_result)
                
                # 立即上传到服务器
                await self._upload_domain_cookies_immediately(domain, domain_cookies, analysis_result)
                
        except Exception as e:
            print(f"处理域名cookies错误: {e}")

    async def _save_domain_cookies(self, domain, cookies, analysis_result):
        """保存域名cookies到本地文件"""
        try:
            cookies_dir = Path("browser_data")
            cookies_dir.mkdir(exist_ok=True)
            
            domain_safe = re.sub(r'[^\w\-_.]', '_', domain)
            cookies_file = cookies_dir / f"{domain_safe}_cookies.json"
            
            cookies_data = {
                "domain": domain,
                "cookies": cookies,
                "analysis": analysis_result,
                "timestamp": time.time(),
                "count": len(cookies)
            }
            
            with cookies_file.open('w', encoding='utf-8') as f:
                json.dump(cookies_data, f, ensure_ascii=False, indent=2)
            
            print(f"   ✅ 已保存到本地: {cookies_file}")
            
        except Exception as e:
            print(f"保存域名cookies失败: {e}")

    async def _upload_domain_cookies_immediately(self, domain, cookies, analysis_result):
        """立即上传单个域名的cookies到服务器"""
        try:
            print(f"   🚀 正在上传 {domain} 的cookies到服务器...")
            
            # 获取管理员密钥
            admin_key_response = requests.get(f"{self.server_url}/admin/key", timeout=10)
            if admin_key_response.status_code != 200:
                print(f"   ❌ 无法获取管理员密钥: HTTP {admin_key_response.status_code}")
                return False
            
            admin_key = admin_key_response.json()["admin_key"]
            
            # 构建按域名分组的cookies数据
            cookies_by_domain = {domain: cookies}
            
            # 准备智能上传数据
            upload_data = {
                "cookies_by_domain": cookies_by_domain,
                "analysis": analysis_result,
                "strategy": analysis_result.get('strategy', self.analyzer.strategies['standard_shared']),
                "timestamp": time.time()
            }
            
            headers = {
                "X-Admin-Key": admin_key,
                "Content-Type": "application/json"
            }
            
            # 上传到智能cookies管理端点
            response = requests.post(
                f"{self.server_url}/admin/cookies/smart-import",
                json=upload_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ {domain} cookies上传成功!")
                print(f"   📊 处理结果: {result.get('message', '已处理')}")
                
                # 显示策略应用结果
                strategy_result = result.get('strategy_applied', {})
                if strategy_result:
                    print(f"   🎯 应用策略: {strategy_result.get('name', '未知策略')}")
                
                return True
            else:
                print(f"   ❌ 上传失败: HTTP {response.status_code}")
                if response.text:
                    print(f"   错误详情: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"   ❌ 上传 {domain} cookies失败: {e}")
            return False

    async def _final_cookie_processing(self, context):
        """最终处理所有cookies"""
        try:
            print("\n📊 开始最终cookies处理...")
            
            # 获取所有cookies
            all_cookies = await context.cookies()
            
            if not all_cookies:
                print("❌ 未检测到任何cookies")
                return False
            
            # 按域名分组
            cookies_by_domain = {}
            for cookie in all_cookies:
                domain = cookie.get('domain', '').lstrip('.')
                if domain:
                    if domain not in cookies_by_domain:
                        cookies_by_domain[domain] = []
                    cookies_by_domain[domain].append(cookie)
            
            print(f"📋 总计检测到 {len(cookies_by_domain)} 个域名的cookies:")
            for domain, domain_cookies in cookies_by_domain.items():
                print(f"   {domain}: {len(domain_cookies)} 个cookies")
            
            # 选择主要域名进行上传
            main_domain = self._select_main_domain(cookies_by_domain)
            if main_domain:
                # 创建综合分析结果
                analysis_result = {
                    'domain': main_domain,
                    'site_type': {'type': 'enterprise_query', 'strategy': 'shared_enterprise'},
                    'strategy': self.analyzer.strategies['shared_enterprise'],
                    'timestamp': time.time()
                }
                
                # 上传到服务器
                success = await self._upload_smart_cookies(cookies_by_domain, analysis_result)
                return success
            else:
                print("❌ 未找到有效的主域名")
                return False
                
        except Exception as e:
            print(f"最终处理失败: {e}")
            return False

    def _select_main_domain(self, cookies_by_domain):
        """选择主要域名"""
        # 优先选择已检测到登录的域名
        if self.login_detected_domains:
            for domain in self.login_detected_domains:
                if domain in cookies_by_domain:
                    return domain
        
        # 否则选择cookies最多的域名
        if cookies_by_domain:
            return max(cookies_by_domain.keys(), key=lambda d: len(cookies_by_domain[d]))
        
        return None

    async def _upload_smart_cookies(self, cookies_by_domain: Dict, analysis_result: Dict) -> bool:
        """智能上传cookies到服务器"""
        try:
            print("正在上传cookies到服务器...")
            
            # 获取管理员密钥
            admin_key_response = requests.get(f"{self.server_url}/admin/key", timeout=10)
            if admin_key_response.status_code != 200:
                print("无法获取管理员密钥")
                return False
            
            admin_key = admin_key_response.json()["admin_key"]
            
            # 准备智能上传数据
            upload_data = {
                "cookies_by_domain": cookies_by_domain,
                "analysis": analysis_result,
                "strategy": analysis_result['strategy'],
                "timestamp": time.time()
            }
            
            headers = {
                "X-Admin-Key": admin_key,
                "Content-Type": "application/json"
            }
            
            # 上传到智能cookies管理端点
            response = requests.post(
                f"{self.server_url}/admin/cookies/smart-import",
                json=upload_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"智能cookies上传成功")
                print(f"处理结果: {result.get('message', '已处理')}")
                
                # 显示策略应用结果
                strategy_result = result.get('strategy_applied', {})
                if strategy_result:
                    print(f"策略应用: {strategy_result}")
                
                return True
            else:
                print(f"上传cookies失败: HTTP {response.status_code}")
                if response.text:
                    print(f"错误信息: {response.text}")
                return False
                
        except Exception as e:
            print(f"上传cookies到服务器失败: {e}")
            return False


async def main():
    parser = argparse.ArgumentParser(description="智能浏览器登录工具")
    parser.add_argument("--server", default="http://localhost:8001", help="服务器地址")
    
    args = parser.parse_args()
    
    # 检查服务器是否运行
    try:
        response = requests.get(f"{args.server}/health", timeout=5)
        if response.status_code == 200:
            print("服务器连接正常")
        else:
            print("服务器响应异常")
    except Exception as e:
        print(f"无法连接到服务器 {args.server}")
        print(f"请确保服务器正在运行: {e}")
        sys.exit(1)
    
    # 开始智能登录流程
    smart_login = SmartBrowserLogin(args.server)
    success = await smart_login.start_smart_login()
    
    if success:
        print("\n智能登录和cookies管理完成！")
        print("系统已根据网站类型应用最佳策略。")
    else:
        print("\n智能登录失败")
        print("请检查登录状态和网络连接。")

if __name__ == "__main__":
    asyncio.run(main()) 