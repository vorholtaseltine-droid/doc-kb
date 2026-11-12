# 查询 MCP 服务器

## 概述

MCP (Model Context Protocol) 服务器是一个以 HTTP 协议设计的 API，它允许 AI 代理（如 OpenCode）与文档知识库进行交互。它的作用是将向量索引中的数据转换为易于使用的工具接口，支持代理查询、检索和分析文档内容。

## 运行 MCP 服务器

### 1. 启动服务器

```bash
# 启动 MCP 服务器（标准输入输出传输）
make mcp

# 或直接运行
python3 mcp_server.py
```

### 2. 安装和配置 OpenCode

在 OpenCode 中配置 MCP 服务器连接：

```json
{
  "mcpServers": {
    "doc-kb": {
      "command": "python3",
      "args": ["mcp_server.py"],
      "cwd": "/path/to/doc-kb"
    }
  }
}
```

### 3. 验证连接

在 OpenCode 终端中运行以下命令以测试连接：

```
# 列出可用工具
<server_name>list_tools
```

## 可用的 5 个工具

### 1. `search_docs`

**描述：** 向量相似度搜索文档

**参数：**
- `query` (字符串，必需)：要搜索的查询文本
- `limit` (整数，可选)：返回的最大结果数量，默认为 10
- `filter` (字典，可选)：可选的过滤条件（如模块、所有者等）

**返回：**
- `results` (数组)：搜索结果，每个结果包含：
  - `id` (字符串)：向量 ID
  - `score` (浮点数)：相似度评分
  - `payload` (字典)：包含元数据的文档片段
  - `embedding` (数组)：嵌入向量

**示例查询：**
```
<server_name>search_docs query="JWT 认证流程" limit=5
```

### 2. `get_module_context`

**描述：** 获取特定模块的上下文信息

**参数：**
- `module` (字符串，必需)：模块名称
- `limit` (整数，可选)：返回的上下文片段数量，默认为 5

**返回：**
- `module_info` (字典)：包含模块元数据的结构化结果
- `chunks` (数组)：相关文档片段，每个片段包含：
  - `heading_path` (字符串)：文档标题路径
  - `content` (字符串)：文档片段内容
  - `score` (浮点数)：相关性评分
- `total_chunks` (整数)：找到的模块片段总数

**示例查询：**
```
<server_name>get_module_context module="auth" limit=3
```

### 3. `list_changed_since`

**描述：** 列出自指定提交 SHA 以来更改的模块

**参数：**
- `since_commit` (字符串，必需)：要比较的 Git 提交 SHA
- `modules` (数组，可选)：可选的要检查的模块列表，留空表示检查所有模块

**返回：**
- `changed_modules` (数组)：更改的模块名称列表
- `total_files_changed` (整数)：更改的文件总数
- `total_new_files` (整数)：新增的文件总数
- `total_deleted_files` (整数)：删除的文件总数
- `git_diff_summary` (字典)：每个更改模块的详细 Git diff 摘要

**示例查询：**
```
<server_name>list_changed_since since_commit="abc123def456"
```

### 4. `get_auth_summary`

**描述：** 获取 auth 模块的简要摘要

**参数：**
- 无

**返回：**
- `summary` (字典)：包含 auth 模块信息的结构化摘要
  - `module` (字符串)：模块名称 ('auth')
  - `status` (字符串)：模块状态
  - `owner` (字符串)：所有者团队
  - `security_features` (数组)：安全功能列表
  - `authentication_flow` (字符串)：主要认证流程描述
  - `permissions` (数组)：权限系统组件
  - `token_management` (字典)：令牌生命周期和策略
  - `session_management` (字典)：会话处理机制

**示例查询：**
```
<server_name>get_auth_summary
```

### 5. `get_module_info`

**描述：** 获取指定模块的详细信息

**参数：**
- `module` (字符串，必需)：要检索信息的模块名称

**返回：**
- `module_info` (字典)：包含以下字段的详细信息：
  - `module` (字符串)：模块名称
  - `meta` (字典)：从 `meta.yaml` 加载的完整元数据
  - `source_path` (字符串)：模块文档的 Git 路径
  - `last_commit` (字符串)：模块的最后 Git 提交 SHA
  - `related_code` (数组)：引用的相关代码路径
  - `related_docs` (数组)：引用的相关文档路径
  - `tags` (数组)：模块的标签列表

**示例查询：**
```
<server_name>get_module_info module="auth"
```

## 高级使用示例

### 1. 获取完整的认证流程

```bash
# 获取 auth 模块的完整上下文
<server_name>get_module_context module="auth" limit=10

# 然后搜索相关的 JWT 文档
<server_name>search_docs query="JWT 令牌验证" limit=5 filter="auth"
```

### 2. 跟踪最近的更改

```bash
# 获取最后 5 个提交的更改摘要
<server_name>list_changed_since since_commit="HEAD~5"

# 获取特定模块的详细更改
<server_name>list_changed_since since_commit="abc123" modules=["auth", "api"]
```

### 3. 结合搜索和上下文

```bash
# 先搜索，然后获取上下文
<server_name>search_docs query="session 管理" limit=3
<server_name>get_module_context module="auth" limit=5
```

### 4. 获取模块信息

```bash
# 获取所有模块的信息
<server_name>get_module_info module="auth"
<server_name>get_module_info module="api"
<server_name>get_module_info module="database"
```

## 故障排除

### 1. 连接问题

如果无法连接 MCP 服务器：

```bash
# 检查服务器是否在运行
ps aux | grep mcp_server.py

# 检查是否有端口冲突
netstat -tlnp | grep :PORT

# 重新启动服务器
pkill -f mcp_server.py
make mcp
```

### 2. 工具调用失败

如果工具返回空结果或错误：

```bash
# 验证查询参数
<server_name>search_docs query="test query" limit=1

# 检查向量索引状态
<server_name>get_module_info module="auth"
```

### 3. 性能问题

如果查询响应缓慢：

```bash
# 检查向量存储状态
python3 -c "
from qdrant_client import QdrantClient
client = QdrantClient(path='.doc-kb/qdrant')
print(f'Collection exists: {client.collection_exists(\"vectors\")}')
if client.collection_exists(\"vectors\"):
    info = client.get_collection(\"vectors\")
    print(f'Total vectors: {info.points_count}')
"

# 考虑重建索引
make ingest INGEST_ARGS=--full
```

### 4. 认证相关问题

如果 auth 工具返回不完整的信息：

```bash
# 检查 auth 模块文档
find docs/modules/auth -name "*.md" -exec cat {} \;

# 验证 meta.yaml
cat docs/modules/auth/meta.yaml
```

## 脚本集成

### 1. 使用 MCP 客户端脚本

```python
import subprocess
import json

def query_mcp(server_name, tool_name, **params):
    """查询 MCP 服务器"""
    cmd = ["/path/to/opencode", f"--server={server_name}", 
           f"--tool={tool_name}"]
    
    for key, value in params.items():
        cmd.extend([f"--{key}={value}"])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

# 示例用法
result = query_mcp("doc-kb", "search_docs", query="JWT", limit=5)
print(f"找到 {len(result['results'])} 个结果")
```

### 2. OpenCode 的 MCP 配置

在 OpenCode 中配置 MCP 服务器连接：

```json
{
  "mcpServers": {
    "doc-kb": {
      "command": "python3",
      "args": ["mcp_server.py"],
      "cwd": "/path/to/doc-kb",
      "env": {
        "PYTHONPATH": "/path/to/doc-kb/src"
      }
    }
  }
}
```

### 3. 自动化脚本

```bash
#!/bin/bash

# 查询 MCP 服务器并格式化输出
query_mcp() {
  local query="$1"
  local limit="${2:-5}"
  
  # 使用 OpenCode 的 MCP 客户端查询
  result=$(opencode mcp query "doc-kb" "search_docs" 
    query="$query" limit="$limit")
  
  echo "查询 '$query' 找到结果："
  echo "$result" | jq '.results | length' 2>/dev/null || echo "$result"
}

# 使用示例
query_mcp "JWT 认证流程" 10
```

## 未来扩展

### 1. 缓存查询结果

```bash
# 添加查询缓存以提高性能
cache_dir=".doc-kb/mcp_cache"
mkdir -p "$cache_dir"

# 缓存查询结果
function cached_query() {
  local key="${1}:limit=${2}"
  local cache_file="$cache_dir/$key.json"
  
  if [[ -f "$cache_file" ]]; then
    cat "$cache_file"
  else
    local result="$(<server_name>search_docs query="$1" limit="$2")"
    echo "$result" > "$cache_file"
    echo "$result"
  fi
}
```

### 2. 批量查询

```python
# 批量查询多个模块
modules = ["auth", "api", "database", "cache"]
results = {}

for module in modules:
    results[module] = query_mcp("doc-kb", "get_module_info", module=module)

# 打印摘要
for module, info in results.items():
    print(f"{module}: {info.get('meta', {}).get('status', 'N/A')}")
```

### 3. 查询日志记录

```python
# 记录查询以供审计
import json
import datetime

def log_query(query_type, params, result):
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "query_type": query_type,
        "params": params,
        "result_count": len(result.get("results", [])) if "results" in result else 0,
        "success": True
    }
    
    with open(".doc-kb/mcp_queries.log", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
```

## 示例输出

### 搜索示例

**查询：** `<server_name>search_docs query="session 管理" limit=3`

**返回：**
```json
{
  "results": [
    {
      "id": "docs/modules/auth#section-2",
      "score": 0.87,
      "payload": {
        "heading_path": "modules/auth#index",
        "content": "### 会话管理\n\n本节介绍如何管理用户会话...",
        "module": "auth",
        "commit_sha": "abc123def456"
      },
      "embedding": [0.123, 0.456, ...]
    }
  ],
  "query_time_ms": 45,
  "total_found": 1
}
```

### 模块上下文示例

**查询：** `<server_name>get_module_context module="auth" limit=2`

**返回：**
```json
{
  "module_info": {
    "module": "auth",
    "owner": "team-platform",
    "status": "stable",
    "security_features": ["JWT", "session", "rate_limit"]
  },
  "chunks": [
    {
      "heading_path": "modules/auth#认证流程",
      "content": "## 认证流程\n\n1. 用户登录...\n2. 验证凭证...\n3. 签发令牌...",
      "score": 0.92
    }
  ],
  "total_chunks": 12
}
```

### 更改跟踪示例

**查询：** `<server_name>list_changed_since since_commit="abc123"`

**返回：**
```json
{
  "changed_modules": ["auth", "api"],
  "total_files_changed": 3,
  "total_new_files": 1,
  "total_deleted_files": 0,
  "git_diff_summary": {
    "auth": "2 files changed, 45 insertions, 12 deletions",
    "api": "1 file changed, 23 insertions"
  },
  "next_commit": "def456"
}
```

这些示例展示了 MCP 服务器如何为代理提供结构化、可查询的文档访问。每个工具都旨在满足特定的代理需求，从简单搜索到复杂上下文检索。