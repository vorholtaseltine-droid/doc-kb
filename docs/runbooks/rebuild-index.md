# 重建索引

## 概述

重构完整的向量索引意味着重新处理所有 Markdown 文档，生成新的嵌入向量，并将它们存储到向量数据库中。需要时可以使用此操作，例如当文档结构发生重大变化时，或者当向量存储损坏时。

## 完整重建

### 命令

```bash
make ingest INGEST_ARGS=--full
```

或直接运行：

```bash
python3 ingest.py --full
```

### 行为

- 将处理存储库中的所有 Markdown 文件
- 清除现有向量索引（Qdrant/SQLite）
- 重新生成所有文档的嵌入向量
- 更新 `.doc-kb/manifest.json`
- 创建新的向量存储

### 何时使用

- 首次设置或初始部署
- 向量存储损坏或不一致
- 大量文档结构更改
- 需要清除所有缓存
- 测试或故障排除场景

## 增量构建

### 命令

```bash
make ingest
```

或直接运行：

```bash
python3 ingest.py --incremental
```

### 行为

- 只处理存储库中自上次构建以来的更改
- 保留现有向量
- 更新更改的文件
- 删除不再存在的文件
- 最小化处理时间和资源使用

### 何时使用

- 日常文档维护
- 小型更改
- 定期更新
- 持续集成管道

## Git 钩子

### 自动增量构建

post-commit Git 钩子自动触发增量构建：

1. 每次 Git 提交后运行
2. 只有在 `.git` 目录存在时启用
3. 失败时不影响提交
4. 显示详细的日志信息

### 手动触发

```bash
# 执行当前提交的增量构建
cd .git/hooks/post-commit && bash
```

## 疑难解答

### 1. 索引丢失或损坏

**症状：**
- 搜索返回空结果
- 向量存储文件丢失
- 数据库连接错误

**解决方案：**

```bash
# 删除现有向量存储
rm -rf .doc-kb/qdrant
rm -f .doc-kb/vector_index.db

# 执行完整重建
make ingest INGEST_ARGS=--full
```

### 2. 嵌入向量维度不匹配

**症状：**
- 嵌入向量大小不一致
- 搜索结果不相关
- 矢量存储错误

**解决方案：**

```bash
# 删除所有向量存储
rm -rf .doc-kb

# 执行完整重建
make ingest INGEST_ARGS=--full
```

### 3. 构建速度慢

**症状：**
- 构建时间过长
- 资源使用率高
- 超时或失败

**解决方案：**

```bash
# 检查系统资源
free -h
df -h

# 增加 CPU 核数（如果需要）
# 或者使用更强大的硬件

# 考虑分批处理
# 编写自定义脚本来处理特定目录
```

### 4. 内存不足

**症状：**
- 构建失败
- OOM 错误
- 系统变慢

**解决方案：**

```bash
# 增加可用内存
# 或者处理较少的文件批次
# 检查是否有其他进程正在使用内存

# 监控进程内存使用
ps aux | grep ingest.py
```

### 5. 认证或授权问题

**症状：**
- 无法访问文档
- 权限错误
- 身份验证失败

**解决方案：**

```bash
# 检查访问权限
ls -la .doc-kb

# 检查配置文件
ls -la .env
```

### 6. Git 钩子问题

**症状：**
- 增量构建不运行
- 钩子失败
- 日志显示错误

**解决方案：**

```bash
# 检查钩子状态
ls -la .git/hooks/post-commit

# 测试钩子
cd .git/hooks/post-commit && bash

# 重新安装钩子
make hooks
```

### 7. 向量存储配置问题

**症状：**
- 无法连接 Qdrant
- SQLite 数据库错误
- 向量存储不可用

**解决方案：**

```bash
# 检查配置文件
# 验证向量存储路径和权限
# 测试 Qdrant 客户端连接
python3 -c "
from qdrant_client import QdrantClient
try:
    client = QdrantClient(path='.doc-kb/qdrant')
    print('Qdrant 连接成功')
except Exception as e:
    print(f'Qdrant 连接失败: {e}')
"
```

### 8. Markdown 文件问题

**症状：**
- 无法解析某些文件
- 分块失败
- 内容丢失

**解决方案：**

```bash
# 检查特定文件的语法
# 验证 Markdown 格式
# 确保没有编码问题
```

## 性能优化

### 1. 系统资源优化

```bash
# 检查系统资源使用
free -h
df -h
ps aux | grep python

# 释放内存
# 停止不必要的后台进程
# 考虑使用更强大的硬件
```

### 2. 构建优化

```bash
# 使用增量构建而非完整重建
# 清除不必要的缓存
# 优化向量存储配置
```

### 3. 硬件优化

```bash
# 增加可用内存
# 使用 SSD 进行更快的 I/O
# 考虑使用分布式 Qdrant
```

## 监控和日志

### 1. 检查构建状态

```bash
# 查看构建日志
tail -f .doc-kb/ingest.log

# 检查构建状态
cat .doc-kb/manifest.json
```

### 2. 监控资源使用

```bash
# 检查内存使用
free -h

# 检查 CPU 使用
ps aux | grep ingest.py | grep -v grep

# 检查磁盘使用
df -h
```

### 3. 测试构建

```bash
# 执行快速测试构建
python3 -c "
import sys
sys.path.insert(0, '.')
from ingest import ingest_documents

try:
    ingest_documents(['--test'])
    print('Test build completed successfully')
except Exception as e:
    print(f'Test build failed: {e}')
"
```

## 脚本集成

### 1. CI/CD 集成

```yaml
# GitHub Actions 示例
- name: Rebuild Index
  run: |
    make deps
    make ingest INGEST_ARGS=--full
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
    OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

### 2. 监控集成

```bash
#!/bin/bash

# 监控构建状态
monitor_build() {
    if [ -f ".doc-kb/manifest.json" ]; then
        echo "构建状态:"
        cat .doc-kb/manifest.json | jq '.last_full_build, .last_incremental_build, .total_chunks'
    else
        echo "没有构建状态"
    fi
}

# 每分钟运行一次
while true; do
    monitor_build
    sleep 60
    break
    # 移除 break 以持续运行
    # break
    # 使用无限循环
    # while true; do
    #   monitor_build
    #   sleep 60
    # done
 done
```

### 3. 警报集成

```bash
#!/bin/bash

# 检查构建是否失败
check_build_status() {
    if [ ! -f ".doc-kb/manifest.json" ]; then
        echo "ERROR: 没有构建状态文件"
        # 发送警报
        return 1
    fi
    
    echo "构建状态正常"
    return 0
}

# 每小时运行一次
check_build_status
```

## 未来扩展

### 1. 并行构建

```bash
# 实现并行文档处理
# 使用多进程进行批次处理
# 并行生成嵌入向量
```

### 2. 分布式构建

```bash
# 使用分布式系统进行大规模构建
# 实现负载均衡
# 处理节点故障
```

### 3. 自动优化

```bash
# 自动调整构建参数
# 基于资源使用情况动态调整批次大小
# 实现智能缓存管理
```

## 总结

重建索引是确保向量索引一致性和准确性的重要操作。通过了解完整重建和增量构建之间的区别，以及何时使用每种方法，可以有效地管理文档知识库。定期维护、适当的故障排除和性能优化可以确保构建过程保持高效和可靠。

关键点：

1. 了解完整重建和增量构建之间的区别
2. 识别重建索引的场景
3. 掌握故障排除技术
4. 监控构建状态和性能
5. 优化系统资源使用

通过遵循本指南，可以有效地管理和维护文档知识库，确保 AI 代理和代码代理能够访问最新和准确的内容。