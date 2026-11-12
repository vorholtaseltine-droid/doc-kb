# 0001. 使用 Qdrant 作为向量索引

## 状态

已通过

## 决策

使用 Qdrant 作为向量索引，通过 `qdrant-client` Python 库在本地持久化模式运行（数据存储在 `.doc-kb/qdrant`），当 Qdrant 不可用时，使用基于 SQLite 的向量存储作为后备。

## 上下文

Box 的资源限制如下：
- 4 vCPU
- 7.7 GB RAM
- 40 GB 磁盘空间
- 无 GPU
- 无 Docker

由于这些限制，Ollama（bge-m3）和 Qdrant 服务器容器不可行。因此，我们需要一个纯 Python 的本地向量解决方案。

## 决策理由

1. **资源效率**：Qdrant 客户端在本地运行，不需要额外资源消耗
2. **持久化**：数据存储在 `.doc-kb/qdrant` 目录中，可以恢复
3. **简单性**：纯 Python 解决方案，无需管理外部服务
4. **可扩展性**：Qdrant 提供良好的 API 兼容性和功能集

## 技术细节

- **库**：`qdrant-client >= 1.7.0`
- **模式**：local persistent（而不是远程服务器）
- **存储位置**：`.doc-kb/qdrant`（在 `.gitignore` 中忽略）
- **后备方案**：当 Qdrant 客户端无法连接或初始化时，使用 SQLite 向量存储

## 后果

- **Git 仍然是唯一来源**：索引可以从 Git 重新构建（`make ingest --full`），确保可追踪性
- **嵌入模型**：使用 Gemini Embedding API (`gemini-embedding-001`)，OpenRouter `text-embedding-3-small` 作为后备
- **代码代理**：MCP 服务器通过 Qdrant 提供搜索和检索功能给 OpenCode 等代理

## 实现

### 初始化 Qdrant 客户端

```python
from qdrant_client import QdrantClient

client = QdrantClient(
    path=".doc-kb/qdrant",  # 本地持久化路径
    # local=True  # 可选，默认为 local 模式
)
```

### SQLite 后备实现

```python
import sqlite3
import numpy as np

class SQLiteVectorStore:
    def __init__(self, db_path=".doc-kb/vector_index.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT,
                embedding BLOB,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def insert(self, id, payload, embedding, metadata=None):
        # 嵌入向量存储为 BLOB
        pass
```

### 容错机制

```python
def get_vector_client():
    try:
        return QdrantClient(path=".doc-kb/qdrant")
    except Exception:
        logger.warning("Qdrant 不可用，使用 SQLite 后备")
        return SQLiteVectorStore()
```

## 注意事项

- 确保 `.gitignore` 中包含 `.doc-kb/`，防止 accidentally 提交向量索引数据
- 定期重建索引（通过 `make ingest --full`）以保持最新状态
- 对于大规模文档集合，可能需要手动调整 Qdrant 索引的参数
- 嵌入向量的维度应该与使用的嵌入模型匹配

## 链接

- [`ingest.py`](../specs/ingest-pipeline.md) - 向量索引的构建过程
- [需求规格](../specs/overview.md) - 整体系统设计
- [`mcp_server.py`](../runbooks/query-mcp.md) - 代理查询向量索引的 API