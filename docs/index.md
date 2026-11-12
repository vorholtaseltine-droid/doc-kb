# 项目文档知识库

欢迎来到项目文档知识库！这是一个将 Git 驱动的文档与 AI 代理桥接起来的系统。

## 快速导航

### 📚 模块
- [认证模块 (auth)](../modules/auth/index.md) — 如何进行身份验证和权限校验

### 🏗️ 架构决策
- [0001. 使用 Qdrant 作为向量索引](adr/0001-use-qdrant.md)

### 📖 规范文档
- [系统概述](specs/overview.md)
- [ ingestion 流水线规范](specs/ingest-pipeline.md)

### 📋 运行手册
- [重建索引](runbooks/rebuild-index.md)
- [查询 MCP 服务器](runbooks/query-mcp.md)

## 关于此项目

本项目旨在创建一个自包含的知识库系统，包括：

1. **Git 驱动的内容**：所有文档都存储在 Git 中，作为唯一来源
2. **向量化索引**：使用 Qdrant 构建向量索引以实现快速搜索
3. **MCP 服务器**：提供 5 个工具让 AI 代理查询知识库
4. **静态站点**：使用 MkDocs 生成易于访问的文档网站
5. **代码代理桥接**：OpenCode 可以连接到 MCP 服务器获取上下文

## 主要技术决策

- **向量存储**：使用 Qdrant 客户端在本地持久化（没有 Docker/Qdrant 服务器），带 SQLite 后备
- **嵌入模型**：Gemini Embedding API，带有 OpenRouter 后备
- **环境**：Box 没有 GPU/Docker，所以我们使用了不同的方法

## 快速开始

1. `make ingest INGEST_ARGS=--full` - 完整构建向量索引
2. `make serve` - 本地预览文档网站
3. `make mcp` - 运行 MCP 服务器
4. `make test` - 运行单元测试

如果您需要了解更多关于任何特定部分的信息，请参阅相关的规范文档或运行手册。