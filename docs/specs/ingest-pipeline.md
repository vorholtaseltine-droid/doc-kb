# 索引构建流水线规范

## 总述

索引构建系统负责将 Git 中的 Markdown 文档转换为向量索引，这些向量索引随后可以被 MCP 服务器用于搜索和检索。整个过程是增量的，由 post-commit git 钩子触发，但也可以通过命令手动执行完整重建。

## 处理流程

### 1. Markdown 文件获取

1.1 Git 存储库中的所有 `.md` 文件都会被处理

1.2 每个模块通过其 `meta.yaml` 文件定义

1.3 使用 `git diff` 获取自上次构建以来的变更文件（增量模式），或获取整个存储库（完整模式）

### 2. 文件预处理

2.1 读取并解析 `meta.yaml` 文件
2.2 验证 YAML 结构和必需字段
2.3 提取模块元数据：`module`、`owner`、`status`、`tags` 等
2.4 使用 Tree-Sitter 解析 Markdown 文件以提取代码符号，如果不可用则使用正则表达式

### 3. Markdown 分块

3.1 使用标题级策略进行分块（H1/H2/H3）
3.2 每个块都包含以下字段：
   - `heading_path`：用于唯一标识的标题路径字符串
   - `content`：实际的 Markdown 内容
   - `level`：从 1 开始的标题级别
   - `module`：所属的模块名称
   - `commit_sha`：最后修改该块的 Git 提交哈希
   - `meta`：从 `meta.yaml` 提取的模块元数据

3.3 示例分块结构：
```yaml
chunk:
  heading_path: "docs/modules/auth#认证"
  content: "| 认证类型 | 支持 |
|-------------|-------|
| JWT        | 是    |
| 会话      | 是    |"
  level: 2
  module: "auth"
  commit_sha: "abc123def456"
  meta:
    module: "auth"
    owner: "team-platform"
    status: "stable"
```

### 4. 代码符号提取

4.1 如果 Tree-Sitter 可用：
   - 使用 `tree-sitter-python` 解析 Python 文件
   - 使用 `tree-sitter-typescript` 解析 TypeScript 文件
   - 提取函数、类、变量和导入符号
   
4.2 如果 Tree-Sitter 不可用：
   - 使用正则表达式从代码文件中提取符号
   - 支持常见的模式：`def function_name()`, `class ClassName:`, `import module`, 等

4.3 符号提取结果存储在每个块的 `symbols` 字段中

### 5. 嵌入向量生成

5.1 使用 Gemini Embedding API 生成主嵌入向量：
   - 模型：`gemini-embedding-001`
   - 使用 `requests` 库进行 HTTP 调用
   - 包含错误重试和速率限制处理

5.2 如果 Gemini API 失败，使用 OpenRouter 后备：
   - 模型：`text-embedding-3-small`
   - 从 OpenRouter API 获取嵌入向量

5.3 存储在每个块的 `embedding` 字段中

### 6. 向量索引构建

6.1 向量存储初始化：
   - 首选 Qdrant 本地客户端 (`.doc-kb/qdrant`)
   - Qdrant 不可用时使用 SQLite 向量存储后备

6.2 向量索引结构：
   - 每个向量代表一个 Markdown 块
   - 负载包括所有元数据字段
   - 使用 `heading_path` 作为向量 ID

6.3 索引更新：
   - 根据需要删除旧向量
   - 插入新/更新的向量
   - 维护 `commit_sha` 到向量的映射

### 7. 状态管理

7.1 维护 `.doc-kb/manifest.json` 文件：
```json
{
  "last_full_build": "2024-01-15T10:30:00Z",
  "last_incremental_build": "2024-01-15T14:45:00Z",
  "processed_commits": [
    "abc123def456",
    "def789abc123"
  ],
  "total_chunks": 1250,
  "total_symbols": 3420,
  "vector_store_type": "qdrant"
}
```

7.2 增量处理逻辑：
   - 比较当前 git HEAD 与 `manifest.json` 中记录的最后处理提交
   - 只处理新的或修改的文件
   - 如果记录的提交不在当前 git 历史中，执行完整重建

## 命令和参数

### `make ingest` - 增量构建

构建自上次成功构建以来的变更部分。命令选项：

```bash
make ingest [INGEST_ARGS=--full]
```

可选的 `INGEST_ARGS`：

- `--full`：执行完整重建而非增量处理
- `--module=MODULE_NAME`：只处理指定的模块
- `--debug`：启用详细的调试输出
- `--skip-validation`：跳过元数据验证

### `make ingest --full` - 完整重建

构建存储库中的所有 Markdown 文件。命令选项：

```bash
make ingest INGEST_ARGS=--full
```

### `python3 ingest.py --help` - 显示帮助

显示完整的命令行界面和所有可用选项。

## 错误处理

### 1. 网络错误
- 重试 Gemini API 调用（最多 3 次，5 秒间隔）
- 如果 Gemini API 失败，使用 OpenRouter 后备
- 记录所有失败的尝试

### 2. 解析错误
- 如果 YAML 解析失败，跳过该文件
- 如果 Markdown 解析失败，使用纯文本分块
- 记录所有解析错误

### 3. 向量存储错误
- 如果 Qdrant 失败，自动切换到 SQLite 后备
- 重试 Qdrant 操作（最多 3 次）
- 如果所有方法都失败，抛出异常并停止处理

### 4. 文件系统错误
- 如果无法读取或写入文件，跳过该文件
- 使用备用路径（如 `/tmp`）进行临时存储
- 清理损坏的文件

## 调试和故障排除

### 1. 检查索引状态

```bash
# 检查 `.doc-kb/manifest.json`
cat .doc-kb/manifest.json

# 检查向量存储信息
python3 -c "
from qdrant_client import QdrantClient
client = QdrantClient(path='.doc-kb/qdrant')
print(f'Points: {client.get_collection(\"vectors\").points_count}')
"
```

### 2. 寻找失败的文件

```bash
# 查找最后 10 次构建中失败的文件
tail -n 10 .doc-kb/build_log.txt | grep -E "ERROR|FAILED"
```

### 3. 重建索引

```bash
make ingest INGEST_ARGS=--full
```

### 4. 验证嵌入维度

```bash
# 检查嵌入向量的维度
python3 -c "
from qdrant_client import QdrantClient
client = QdrantClient(path='.doc-kb/qdrant')
vector = client.retrieve(point_ids=['example-id'], collection_name='vectors')[0].vector
print(f'Embedding dimension: {len(vector)}')
"
```

### 5. 检查内存使用

```bash
# 检查进程内存使用
ps aux | grep ingest.py | grep -v grep
```

## 性能考虑

### 1. 内存使用
- 对于大规模存储库，可能需要调整 Python 堆大小
- 可以使用 `--chunk-size` 选项控制批处理大小

### 2. 速率限制
- 实现 Gemini API 的速率限制处理
- 批量处理嵌入向量请求
- 考虑使用异步 HTTP 客户端

### 3. 磁盘空间
- 向量存储（Qdrant/SQLite）需要额外的磁盘空间
- 定期清理旧的备份和日志文件

### 4. CPU 使用
- Tree-Sitter 解析是 CPU 密集型的
- 对于大量 TypeScript 文件，可能需要更多 CPU 核心

## 监控和日志

### 1. 日志级别

```bash
# 控制台输出
make ingest  # 默认 INFO 级别

# 详细日志
make ingest INGEST_ARGS=--debug
```

### 2. 日志格式

每个日志条目都包含以下字段：
- 时间戳
- 日志级别 (DEBUG/INFO/WARN/ERROR)
- 消息
- 可选的上下文数据

### 3. 指标

```bash
# 显示处理指标
python3 -c "
import json
with open('.doc-kb/manifest.json', 'r') as f:
    manifest = json.load(f)
    print(f'最后完整构建: {manifest.get(\"last_full_build\")}')
    print(f'最后增量构建: {manifest.get(\"last_incremental_build\")}')
    print(f'处理块数: {manifest.get(\"total_chunks\", 0)}')
    print(f'处理符号数: {manifest.get(\"total_symbols\", 0)}')
"
```

## 维护

### 1. 定期完整重建

建议每小时执行一次完整重建，以确保索引的一致性。可以通过 cron 作业安排：

```bash
0 * * * * cd /path/to/doc-kb && make ingest INGEST_ARGS=--full
```

### 2. 备份

- 定期备份 `.doc-kb/` 目录
- 备份向量存储（Qdrant/SQLite）
- 记录并备份 `manifest.json`

### 3. 升级

- 当有新版本时，升级 `qdrant-client` 依赖项
- 更新嵌入模型（Gemini/OpenRouter）
- 检查 Tree-Sitter 语言支持

## 安全考虑

### 1. API 密钥
- 保护 Gemini 和 OpenRouter API 密钥
- 不要将 API 密钥提交到 Git
- 使用环境变量或安全密钥管理

### 2. 文件权限
- 限制对 `.doc-kb/` 目录的访问权限
- 确保向量存储文件的安全权限

### 3. 数据隐私
- 在构建之前检查 Markdown 文件中是否有敏感信息
- 考虑使用 RAG 系统来隐藏私人信息

## 未来扩展

### 1. 多语言支持
- 扩展符号提取以支持更多语言
- 添加语言特定的 Markdown 解析

### 2. 高级索引结构
- 引入分层向量索引以提高搜索速度
- 实现搜索语法增强功能

### 3. 集成其他知识库
- 支持从 Confluence、GitLab 等导入
- 合并多个来源的向量索引

### 4. 机器学习模型
- 探索使用微调的语言模型进行更好的检索
- 实现语义搜索和 reranking

## 示例命令

```bash
# 增量构建
make ingest

# 完整重建
make ingest INGEST_ARGS=--full

# 查看帮助
make help

# 显示状态
python3 -c "
import json
with open('.doc-kb/manifest.json', 'r') as f:
    manifest = json.load(f)
    print(json.dumps(manifest, indent=2))
"
```

这些命令提供了对索引构建系统的完全控制，包括增量和完整重建、状态检查和故障排除。所有命令都旨在简单易用，同时提供强大的功能以处理各种场景。