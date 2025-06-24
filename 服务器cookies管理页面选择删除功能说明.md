# 服务器Cookies管理页面选择删除功能说明

## 功能概述

为服务器GUI管理界面的Cookies管理页面添加了选中删除功能，支持多选和批量删除操作，提升了Cookies管理的便利性和精确性。

## 新增功能

### 1. 界面改进

#### 按钮布局优化
- **第一行操作按钮**：
  - `刷新Cookies` - 重新获取最新cookies数据
  - `删除选中` - 删除用户选中的cookies（新增）
  - `清空所有` - 清空所有cookies（原"清空Cookies"按钮）
  - `导出Cookies` - 导出cookies到文件
  - `导入Cookies` - 从文件导入cookies

#### 选择操作按钮
- **第二行选择按钮**：
  - `🔲 全选` - 选中所有cookies
  - `🔳 反选` - 反选当前选择状态
  - `🔲 清除选择` - 清除所有选择
  - 分隔符 - 与浏览器操作按钮区分
  - `🧠 智能浏览器登录` - 原有功能
  - `🔄 快速更新模式` - 原有功能

#### Treeview多选支持
- 启用`selectmode='extended'`模式
- 支持Ctrl+点击、Shift+点击等多选操作
- 支持键盘导航选择

### 2. 核心功能

#### 选择操作
```python
def select_all_cookies(self):
    """全选所有cookies"""
    
def invert_selection_cookies(self):
    """反选cookies"""
    
def clear_selection_cookies(self):
    """清除选择"""
```

#### 删除功能
```python
def delete_selected_cookies(self):
    """删除选中的cookies"""
    # 1. 检查是否有选中项
    # 2. 提取选中cookies信息
    # 3. 显示确认对话框
    # 4. 异步执行删除操作

def _delete_cookies_async(self, cookies_to_delete):
    """异步删除选中的cookies"""
    # 调用服务器API执行删除
```

### 3. 服务器端API

#### 新增删除端点
```http
POST /admin/cookies/delete
Content-Type: application/json
X-Admin-Key: <管理员密钥>

{
  "cookies_to_delete": [
    {
      "name": "cookie_name",
      "value": "cookie_value", 
      "domain": "example.com",
      "path": "/"
    }
  ]
}
```

#### 服务器处理逻辑
```python
async def delete_selected_cookies(self, cookies_to_delete: List[Dict]) -> Dict[str, Any]:
    """删除选中的Cookies"""
    # 1. 验证输入参数
    # 2. 创建删除匹配键（name+domain+path）
    # 3. 过滤保留的cookies
    # 4. 更新全局状态
    # 5. 保存到磁盘
    # 6. 广播通知客户端
```

## 功能特点

### 1. 精确匹配删除
- 使用`name + domain + path`作为唯一标识
- 避免误删相似cookies
- 支持精确控制删除范围

### 2. 用户友好体验
- **智能提示**：显示将要删除的cookies详情
- **确认对话框**：防止误操作
- **批量预览**：最多显示5个cookies，超出部分显示数量
- **操作反馈**：实时显示选择数量和操作结果

### 3. 安全保障
- **管理员权限**：需要有效的管理员密钥
- **确认机制**：删除前必须用户确认
- **状态更新**：删除后自动更新登录状态
- **持久化**：立即保存到磁盘

### 4. 实时同步
- **状态广播**：删除操作实时通知所有客户端
- **界面刷新**：删除完成后自动刷新显示
- **日志记录**：详细记录操作过程和结果

## 使用场景

### 1. 精确清理
- 删除特定域名的过期cookies
- 清理测试环境的临时cookies
- 移除有问题的认证cookies

### 2. 批量管理
- 选择多个相关cookies一次删除
- 按域名批量清理cookies
- 快速移除无用的跟踪cookies

### 3. 问题排查
- 删除可能导致问题的特定cookies
- 清理冲突的登录状态cookies
- 移除损坏的会话cookies

## 操作流程

### 1. 选择Cookies
```
1. 在Cookies管理页面查看cookies列表
2. 使用鼠标点击选择单个cookie
3. 使用Ctrl+点击选择多个cookies
4. 或使用"全选"、"反选"按钮批量选择
```

### 2. 执行删除
```
1. 点击"删除选中"按钮
2. 查看确认对话框中的cookies详情
3. 确认删除操作
4. 等待处理完成并查看结果
```

### 3. 验证结果
```
1. 查看日志输出的删除结果
2. 观察cookies数量变化
3. 验证相关功能是否正常
```

## 技术实现

### 1. 前端改进
- **UI优化**：重新设计按钮布局，增强视觉层次
- **多选支持**：启用Treeview的extended选择模式
- **交互优化**：添加选择操作的快捷按钮
- **异步处理**：使用线程池避免UI阻塞

### 2. 后端扩展
- **API设计**：RESTful风格的删除端点
- **数据处理**：基于唯一键的精确匹配算法
- **状态管理**：完整的全局状态更新流程
- **持久化**：自动保存到磁盘文件

### 3. 安全措施
- **权限验证**：管理员密钥验证
- **参数校验**：严格的输入参数验证
- **错误处理**：完善的异常捕获和处理
- **日志审计**：详细的操作日志记录

## 后续优化

### 1. 高级筛选
- 按域名筛选cookies
- 按过期时间筛选
- 按cookie类型筛选

### 2. 批量操作
- 导出选中cookies
- 复制选中cookies
- 编辑选中cookies属性

### 3. 可视化增强
- cookies依赖关系图
- 域名分布统计
- 使用频率分析

这个功能显著提升了服务器管理员对cookies的精确控制能力，使得cookies管理更加灵活和高效。 