# 项目文档知识库 & 开发者 Agent 桥接 — 交接文档

- 日期：2026-11-12（UTC+8 11 月 12 日晚 / 太平洋时间上午）
- 机器：Simular Box "main"（https://box.simular.ai/box/cb-3d50cd9533ed），4 vCPU / 7.7 GB 内存 / 40 GB 磁盘，Python 3.12.3，git 2.43.0，opencode v2.2.7
- 项目目录：`/home/user/doc-kb/`（Git 仓库，4 次提交，HEAD `58e0fa5`）
- 状态：阶段 1–3 已完成并验证；阶段 4（OpenCode + MCP 联调）未完成，见第 4 节

## 1. 建了什么

演示项目仓库（`docs/` + `src/` + 索引/MCP 服务）：

| 文件 | 说明 |
| --- | --- |
| `docs/adr/0001-use-qdrant.md` | ADR：向量库选型（Qdrant 优先，SQLite 兜底） |
| `docs/specs/overview.md`、`docs/specs/ingest-pipeline.md` | 规格：系统总览、索引流水线 |
| `docs/runbooks/rebuild-index.md`、`docs/runbooks/query-mcp.md` | 操作手册：重建索引、MCP 查询（含环境变量说明） |
| `docs/modules/auth/index.md` + `meta.yaml` | auth 模块文档（含中文「auth 模块怎么鉴权」章节）+ 元数据（owner team-platform，status stable，related_code `src/auth/**` 与 `src/middleware/session.ts`，tags security/session/jwt） |
| `src/auth/__init__.py`、`jwt.py`（create_jwt / verify_jwt）、`session.py`（create_session / validate_session / revoke_session）、`src/middleware/session.ts`（verifyJwt / sessionMiddleware） | 示例代码 |
| `ingest.py` | 标题级 Markdown 切块（H1–H3，heading_path）、meta.yaml 解析、tree-sitter（装得上）或正则提取函数/类、git-diff + 内容哈希增量重建 |
| `embedder.py` | 向量模型：Gemini → OpenRouter → 本地 TF-IDF 兜底 |
| `vector_store.py` | Qdrant（本地持久化）或 SQLite（`DOC_KB_BACKEND=sqlite`） |
| `kb.py` | 检索逻辑：search_docs / get_doc / get_module_context / list_changed_since / write_doc_suggestion |
| `mcp_server.py` | MCP 服务器（mcp 2.x，stdio），正好 5 个工具 |
| `tests/test_doc_kb.py` | 4 个测试 |
| `Makefile` | `make ingest` / `make serve` / `make mcp` / `make test` / `make build` / `make hooks` |
| `mkdocs.yml` | MkDocs Material 配置 |
| `docker-compose.yml` | 仅作参考（本地 PC 用），**不要在 Box 上跑 Docker** |
| `.opencode.json` | OpenCode 的 MCP 配置（stdio 启动 `python3 mcp_server.py`，含环境变量透传） |
| `.githooks/post-commit` | 提交后自动跑增量索引（已修复，见第 3 节） |

索引当前状态：7 个文档、300 个 chunk、provider `openrouter`、维度 1536、backend `qdrant`，索引数据在 `.doc-kb/qdrant/`。

## 2. 验证结果（都真实跑过）

### 测试：4/4 通过（`make test`，exit 0，7.964 秒，2026-11-12 11:14 PST）

1. 搜索 “auth 模块怎么鉴权”：auth 文档进前 3，代码路径进前 8。
2. `get_module_context("auth")` 返回完整元数据 + 代码符号。
3. 增量索引：全量后第二遍 0 个文件，改 1 个文件后只处理 1 个文件。
4. `write_doc_suggestion` 只写 `drafts/`，不碰 `docs/`。

### 查询示例 1：`search_docs("auth 模块怎么鉴权", top_k=5)`（MCP 实测）

| 排名 | 分数 | 路径 | 标题 |
| --- | --- | --- | --- |
| 1 | 0.7137 | docs/index.md | 项目文档知识库 > 快速导航 > 模块 |
| 2 | 0.6726 | docs/modules/auth/index.md | Auth Module Documentation > auth 模块怎么鉴权 |
| 3 | 0.6031 | docs/modules/auth/index.md | Auth Module Documentation > How Auth Module Authenticates |
| 4 | 0.5713 | docs/runbooks/query-mcp.md | 检查向量索引状态 |
| 5 | 0.5412 | src/auth/jwt.py | verify_jwt |

注意：首页导航 chunk 很短、关键词很密，所以排第 1；auth 文档本身排第 2，代码路径第 5。测试因此断言「文档进前 3、代码进前 8」，而不是第 1。

### 查询示例 2：`get_module_context("auth")`（MCP 实测）

- meta：`module: auth, owner: team-platform, status: stable, related_code: [src/auth/**, src/middleware/session.ts], related_docs: [adr/0001-use-qdrant.md], tags: [security, session, jwt]`
- 代码符号：`src/auth/jwt.py`（_b64url_encode, _b64url_decode, create_jwt, verify_jwt）、`src/auth/session.py`（create_session, validate_session, revoke_session, _cleanup_expired_sessions, get_session_info, get_all_sessions）、`src/middleware/session.ts`（verifyJwt, sessionMiddleware）。
- `get_doc(docs/modules/auth/index.md)` 返回 9,016 字符。
- `list_changed_since("069c459")` 返回 13 个改动文件和 3 次提交（33b2d15 / bbe354d / 58e0fa5）。

### 其他验证

- `mkdocs build` 干净通过（0.4 秒，无警告）；`mkdocs serve` 首页 200、auth 页 200，页面含「auth 模块怎么鉴权」3 次。
- MCP 5 个工具全部经 stdio 实测通过（`ALL_MCP_TOOLS_OK`）。
- SQLite 后端与离线 TF-IDF 后端都在临时副本上端到端跑通过（见第 4 节的排名限制）。
- post-commit hook 实测：提交后自动跑增量索引，0 改动时 `{"processed": 0, "skipped": 7, "chunks": 300}`。

## 3. 与原方案相比改了什么（以及为什么）

**立项时已定的改动：**

1. **不用 Ollama / 不用 Docker**：Box 只有 4 核 7.7 GB、无 GPU，Ollama bge-m3 和 Docker 容器跑不起来。向量库改用 Qdrant 的轻量 pip 安装（本地持久化模式，不用服务器）；SQLite 后端已实现并验证，可作兜底。Git 仍是唯一事实来源，索引可重建。
2. **v1 不用 n8n / RAGFlow / AnythingLLM**：太重。改用 git hook + 小的 ingest 脚本做增量同步。
3. **不用任何图像模型**：超出范围。
4. **编码 Agent 用 Box 上的 OpenCode v2.2.7**：默认模型 google/gemini-3.5-flash-lite（11 月 12 日上午实测可用）；gemini-3.8-flash 仍 503 过载，不要用；OpenRouter cohere/north-mini-code:free 是备用；OpenCode 内置免费模型已达限额，不要用。
5. **额度保护**：Box 是一次性 5,000 额度（90 天有效，无每日重置），本阶段结束时剩 4,779；低于 500 立即停工先写交接。

**实施中发现、不得不改的：**

6. **Embedding 实际走 OpenRouter，不是 Gemini 直连**：Box Secrets 里存的 `GEMINI_API_KEY` 是 36 字符 `cbv_` 前缀，不是 Google AI Studio 的 `AIza…` 密钥，Gemini API 返回 400 `API_KEY_INVALID`。OpenRouter 的 key 可用，`openai/text-embedding-3-small`（1536 维）实测 200。embedder 的顺序是 Gemini → OpenRouter → 本地 TF-IDF，所以在 Box Secrets 里把 Gemini key 换成正确的之后会自动切回 Gemini。
7. **OpenCode 必须显式传 `--model openrouter/cohere/north-mini-code:free`**：不传会默认用内置免费模型 `baidu/ernie-light-dt-1.0-intl`，报 OpenRouter 额度错误。全局配置里只有两个 provider、没有顶层默认模型。
8. **OpenCode 的免费模型当日额度在 Task B 做到一半时耗尽**（"free-models-per-day"），所以 ingest.py / kb.py / mcp_server.py / 测试是手工写的，Task B 只产出了 embedder.py、vector_store.py 和 tests/__init__.py。**在次日额度重置（或 Ethan 加额度）之前不要再跑 OpenCode。**
9. **MCP 服务器用 mcp 2.x 的 `MCPServer`，不是 `FastMCP`**：mcp 2.3.0 里 `from mcp.server.fastmcp import FastMCP` 不存在。工具函数必须写返回类型注解（`-> list` / `-> dict`），否则结果会被二次编码；客户端取字段用 snake_case（`is_error`、`structured_content`）。
10. **embedder 的日志全部改到 stderr**：任何 stdout 输出都会破坏 MCP 的 JSON-RPC 流；错误日志只记异常类型和 HTTP 状态，不记原始异常文本。
11. **MCP 子进程必须显式传环境变量**：mcp 2.x 的 stdio 客户端只继承白名单变量。Box 的出口走本地代理 `http://127.0.0.1:3128`，TLS 证书由 `/etc/ssl/certs/ca-certificates.crt` 提供，所以服务器进程需要 API key + 代理变量 + 证书变量（共 11 个，见 `docs/runbooks/query-mcp.md` 的「环境变量」一节和 `.opencode.json`）。缺了会依次出现 "key 未设置"、ConnectionError、SSLError。
12. **Makefile 重写**：原版多行内联 Python 缺少 tab，`make` 报 `missing separator`；新版用 `.RECIPEPREFIX = >`，目标为 ingest / serve / mcp / test / build / hooks / help。
13. **mkdocs.yml 重写**：删掉了无效配置（emoji 的 `!!python/name` 引用、admonition 的 `title`、`custom_languages`、`static_templates` 等）；`site_url` 去掉 `/doc-kb` 路径，否则 `mkdocs serve` 会挂在 `/doc-kb/` 下、首页 302。
14. **post-commit hook 修了两次**：第一次它用 `dirname $BASH_SOURCE` 找仓库根目录，装到 `.git/hooks/` 后指向了 `.git/hooks`，找不到 ingest.py；第二次它引用的 `try_incremental` 函数在 `timeout bash -c` 的子 shell 里不存在。现在是简化版（`git rev-parse --show-toplevel` + 直接跑 `python3 ingest.py --incremental`），已实测通过。
15. **TF-IDF 分词器改成逐字切 CJK**：原来的 `\w+` 会把整段中文当一个 token，永远匹配不到「鉴权」这类词。

## 4. 已知问题 / 缺口

- **离线 TF-IDF 兜底的中文排名很弱**：查询「auth 模块怎么鉴权」时，auth 文档进不了前 10（前 10 全是短代码 chunk 和首页导航）。机制上能跑（可离线索引和查询），但中文检索质量差。下一步建议加中文分词（jieba）或用小型 embedding 模型；主路径（OpenRouter）不受影响。
- **跨语言检索**：语料是英文文档 + 中文查询，短 chunk（导航、代码符号）容易排过权威文档。
- **OpenCode + MCP 的联调还没跑**：`.opencode.json` 已写好但未用真实 Agent 调用验证（额度耗尽，见第 3.6/3.8 条）。
- **`GEMINI_API_KEY` 无效**：见第 3.6 条。需要 Ethan 在 Box Secrets 界面里换成正确的 Google AI Studio key（**不要在聊天里贴 key**）。另外，11 月 12 日上午一次短暂 DNS 故障期间，embedder 的错误日志里曾出现过 key 值（终端回滚和两个 /tmp 日志文件），日志已删除、脚本已清理，仍建议在 Box Secrets 里轮换一次该密钥。
- **Box 网络偶有抖动**：上午出现过几次 DNS/连接错误和终端断线（3 次），Box 本身一直 Running，磁盘状态未丢。
- MkDocs 1.6.1 在 Python 3.12 上会打印「最后一个支持 Python 3.12 的版本」提示，不影响构建。

## 5. 运行方式

```bash
cd /home/user/doc-kb
 export PATH=$HOME/.local/bin:$PATH   # 新开的 shell 需要这一行
make ingest     # 增量索引（git 状态变化时自动只处理改动文件）
make ingest INGEST_ARGS=--full   # 全量重建索引
make serve      # MkDocs 本地服务，http://127.0.0.1:8000/
make build      # 生成静态站（site/，已 gitignore）
make mcp        # 启动 MCP 服务器（stdio；被客户端启动时需传第 3.11 条的环境变量）
make test       # 4 个测试
make hooks      # 安装 post-commit hook
```

SQLite 后端：`DOC_KB_BACKEND=sqlite make ingest`。依赖见 `requirements.txt`（`python3 -m pip install --user --break-system-packages -r requirements.txt`）。

## 6. 额度（交接时）

仪表盘显示 **4,779 credits left**（Box Free，一次性 5,000，90 天有效，无每日重置；本阶段开始时也是 4,779，仪表盘数字似乎是缓存/取整的）。低于 500 时立即停工，先写交接。不要让 Box 空闲跑着。

## 7. 下一步

1. 在 Box Secrets 里修正 `GEMINI_API_KEY`（换成有效的 Google AI Studio key）并轮换一次；embedder 会自动切回 Gemini。
2. 等 OpenRouter 免费模型额度重置后，用 OpenCode + `.opencode.json` 的 MCP 配置跑一次真实的 Agent 调用，验证「开发者 Agent 桥接」端到端。
3. 给 TF-IDF 兜底加中文分词（jieba），或在离线路径上加文档类型加权，改善中文排名。
4. 评估是否把索引后端换成真正的 Qdrant Server（本地 PC 或有 Docker 的环境），以及是否引入 n8n / RAGFlow（v2）。
5. 继续加模块（按 `docs/modules/<name>/index.md` + `meta.yaml` 的模式）和 runbook。
