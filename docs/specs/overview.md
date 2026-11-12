# 系统概述

## 组件

### 1. 文档存储 (`docs/`)
- MkDocs Markdown 源文件
- 架构决策记录 (ADR) 目录
- 规范文档 (specs/) 目录
- 运行手册 (runbooks/) 目录
- 模块文档 (modules/) 目录，每个模块包含 `index.md` 和 `meta.yaml`

### 2. 索引生成 (`ingest.py`)
- 读取 Git 中的 Markdown 文件
- 解析模块的 `meta.yaml` 文件
- 进行标题级 Markdown 分块（H1/H2/H3），保持 `heading_path`
- 使用 tree-sitter 提取代码符号（Python 和 TypeScript），否则使用正则表达式
- 生成嵌入向量（Gemini API + OpenRouter 后备）
- 创建向量索引负载，包括路径、标题路径、模块名和提交 SHA

### 3. 向量存储
- Qdrant 本地持久化客户端 (`.doc-kb/qdrant`)
- SQLite 向量存储后备 (`.doc-kb/vector_index.db`)
- 支持增量更新（基于 git diff）和完整重建

### 4. MCP 服务器 (`mcp_server.py`)
五种 MCP 工具用于与代码代理通信：

#### `search_docs(query, limit=10, filter=None)`
- 参数：
  - `query` (字符串)：要搜索的查询文本
  - `limit` (整数)：要返回的最大结果数量，默认值为 10
  - `filter` (字典)：可选的过滤条件（如模块名、所有者等）
- 返回：与查询相似度最高的文档片段列表，每个片段包含：
  - `id` (字符串)：向量 ID
  - `score` (浮点数)：相似度评分
  - `payload` (字典)：文档负载（路径、标题、模块名等）
  - `embedding` (向量)：嵌入向量

#### `get_module_context(module, limit=5)`
- 参数：
  - `module` (字符串)：要检索的模块名称
  - `limit` (整数)：要返回的上下文片段数量，默认值为 5
- 返回：包含模块上下文的结构化结果：
  - `module` (字符串)：模块名称
  - `meta` (字典)：从 `meta.yaml` 读取的元数据
  - `chunks` (列表)：与模块相关的文档片段，每个片段包含：
    - `heading_path` (字符串)：文档标题路径
    - `content` (字符串)：文档片段内容
    - `score` (浮点数)：相关性评分
  - `total_chunks` (整数)：找到的模块片段总数

#### `list_changed_since(since_commit, modules=None)`
- 参数：
  - `since_commit` (字符串)：要比较的 Git 提交 SHA
  - `modules` (列表)：可选的要检查的模块列表，留空表示检查所有模块
- 返回：自指定提交 SHA 以来修改的模块列表：
  - `modules` (列表)：更改的模块名称列表
  - `total_files_changed` (整数)：更改的文件总数
  - `total_new_files` (整数)：新增的文件总数
  - `total_deleted_files` (整数)：删除的文件总数
  - `git_diff_summary` (字典)：每个更改模块的详细 Git diff 摘要

#### `get_auth_summary()`
- 参数：无
- 返回：auth 模块的简要摘要：
  - `module` (字符串)：模块名称 ('auth')
  - `status` (字符串)：模块状态
  - `owner` (字符串)：所有者团队
  - `security_features` (列表)：安全功能列表
  - `authentication_flow` (字符串)：主要认证流程描述
  - `permissions` (列表)：权限系统组件
  - `token_management` (字典)：令牌生命周期和策略
  - `session_management` (字典)：会话处理机制

#### `get_module_info(module)`
- 参数：
  - `module` (字符串)：要检索信息的模块名称
- 返回：指定模块的详细信息：
  - `module` (字符串)：模块名称
  - `meta` (字典)：从 `meta.yaml` 加载的完整元数据
  - `source_path` (字符串)：模块文档的 Git 路径
  - `last_commit` (字符串)：模块的最后 Git 提交 SHA
  - `related_code` (列表)：引用的相关代码路径
  - `related_docs` (列表)：引用的相关文档路径
  - `tags` (列表)：模块的标签列表

### 5. MkDocs 网站 (`mkdocs.yml`)
- Material 主题
- 导航：主页、模块、ADR、规范文档、运行手册
- 文档扩展支持代码高亮和锚点链接

### 6. 代码代理桥接
- OpenCode 通过 MCP 服务器连接
- 可以查询文档、获取上下文、检查更改状态
- 用于实时开发支持和文档检索

## 数据流

1. **编写 Markdown** → Git 提交
2. **Git 钩子**（post-commit）→ 触发 `ingest.py` 的增量处理
3. **处理**：
   - Markdown 文件分割成标题级块
   - 解析模块 `meta.yaml`
   - 使用 tree-sitter 提取代码符号
   - 生成嵌入向量
4. **向量索引**：
   - 将向量存储在 Qdrant 本地模式中（`.doc-kb/qdrant`）
   - 带有 SQLite 后备
5. **MCP 查询**：
   - 代理通过 5 个工具查询向量索引
   - 检索文档片段、模块上下文、更改历史
6. **MkDocs 渲染**：
   - Markdown 文件渲染为静态网站
   - 托管 ADR、规范文档和运行手册

## 详细信息

### 文件结构

```
.docs-kb/
├── docs/
│   ├── adr/0001-use-qdrant.md
│   ├── specs/overview.md
│   ├── specs/ingest-pipeline.md
│   ├── runbooks/rebuild-index.md
│   ├── runbooks/query-mcp.md
│   └── modules/auth/index.md
├── src/
│   ├── auth/jwt.py
│   ├── auth/session.py
│   └── middleware/session.ts
├── ingest.py
├── mcp_server.py
├── requirements.txt
├── Makefile
├── .gitignore
└── .githooks/post-commit
```

### 技术栈

- **语言**：Python (ingest, MCP server), TypeScript (middleware), Markdown
- **向量数据库**：Qdrant (本地), SQLite (后备)
- **嵌入模型**：Gemini Embedding API, OpenRouter 后备
- **文档生成**：MkDocs Material
- **代理支持**：MCP (Model Context Protocol)
- **认证**：JWT + 会话管理
- **版本控制**：Git (源代码和文档)

### 扩展性

- 可以通过添加新的 MCP 工具支持更多代理功能
- 可以添加额外的嵌入模型提供商
- 可以使用分布式 Qdrant 设置进行扩展
- 可以添加额外的模块类型和文档结构

## 主要组件详细信息

### JWT 认证 (`src/auth/jwt.py`)
- 使用 HMAC-SHA256 实现
- 包含签发、验证和演示代码
- 支持可配置的过期时间和密钥

### 会话管理 (`src/auth/session.py`)
- 支持 Redis/Memcached 存储的内存会话
- 包含创建、验证和撤销功能
- 支持跨进程会话管理

### Express 中间件 (`src/middleware/session.ts`)
- 支持 JWT 和 Cookie 会话认证
- 提供用户提取和权限检查
- 遵循 Express.js 中间件模式

### 索引生成 (`ingest.py`)
- 支持增量构建（基于 git diff）和完整重建
- 带有树形结构解析的 Markdown 处理
- 向量索引管理和容错

### MCP 服务器 (`mcp_server.py`)
- 提供 5 个标准工具用于文档检索
- 支持持续查询和模块上下文检索
- 集成代码代理和文档知识库

### MkDocs 网站 (`mkdocs.yml`)
- Material Design 主题
- 完整的导航结构
- 支持代码高亮和文档锚点