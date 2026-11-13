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

## 8. 2026-11-12 - Gemini key replaced, embedder switched to Gemini (quota-blocked at wrap-up)
- GEMINI_API_KEY replaced in Simular Secrets on 2026-11-12 (Secrets UI: Replaced Nov 12, 2026, ends in Shrg). Terminal env var is a Simular stand-in (first 3 cbv, len 36, does not end Shrg), not the real key.
- Direct Gemini test: ?key= returns 400 API_KEY_INVALID; X-Goog-Api-Key header returns 200. embedder.py was changed to send the key via X-Goog-Api-Key header (no ?key=), so Simular swaps in the real key.
- Live Gemini API model list: only models/gemini-embedding-001, no text-embedding-004. Code already used gemini-embedding-001; its default dim is 3072, not 768.
- embedder.py fixes: extract result["embedding"]["values"] (was dim 1), 0.7 s pacing per embed (free tier 100/min), retry up to 5x on 429/500/502/503/504 with 10/20/30/40/50 s backoff.
- Full rebuild: make ingest INGEST_ARGS=--full gave processed 7, skipped 0, upserted 303, deleted 0, provider gemini, dim 3072, backend qdrant, chunks 300. Manifest now provider gemini, dim 3072. Plain make ingest (incremental) alone does NOT rebuild on provider change.
- make test: FAILED (errors=2), Ran 4 tests in 337.165 s. Passed: test_get_module_context, test_write_doc_suggestion. Errors: test_incremental_ingest_only_changed, test_search_auth_returns_doc_and_code - both from Gemini free-tier DAILY quota: Embed content requests per day limit exceeded, limit 1000, retry about 5h24m (reset about midnight PST 2026-11-13). Query fell back to OpenRouter (dim 1536) vs index 3072: embedding dimension mismatch.
- MCP search_docs auth query, top_k=5, via MCP server: FAILED with the same dimension mismatch error, no results, same quota reason.
- After quota resets at midnight PST, re-run make test and the MCP search; they should pass without rebuilding the index (already Gemini/3072). Do not rebuild again unless needed - a full rebuild costs about 300 Gemini requests, plus the test suite fixture ingest about 300 more.
- Box credits at wrap-up: 4,161 left (Box Free; 4,323 at start, 162 used). Box main left Running. embedder.py and HANDOVER.md are modified in git (uncommitted).

## 9. 2026-11-13 - Phase 4 (Agent.docx, this session, 02:45-03:15 UTC)

Credits: 4,161 at start, 4,078 at end (83 used this session). Box main left Running. No subscription, no payment method added, no second box, no residential IP.

### Step 1 - Credit + wake check: PASS
- Balance 4,161 at start, above the 500 stop threshold. main was Running, no wake needed.
- Usage Nov 1-13: 771 credits ($0.77), 4.3 h, 0 GB residential. Billing: Box Free, 5,000 free credits once, auto top-up Off.

### Step 2 - Embedding switch: FAILED (quota, not auth)
- Plain make ingest: processed 0, skipped 7, upserted 0, provider gemini, dim 3072, exit 0. It re-embedded nothing, so that line alone proves nothing.
- Full rebuild make ingest INGEST_ARGS=--full: Gemini API failed: Exception (http status None), then Using OpenRouter Embedding API; processed 7, skipped 0, upserted 303, deleted 0, provider openrouter, dim 1536, backend qdrant, chunks 300, exit 0.
- Direct probe Embedder()._test_gemini(): Gemini API returned 429: RESOURCE_EXHAUSTED, Embed content requests per day limit exceeded on Free Tier, quotaId EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier, quota 1000 per day, retryDelay 18247 s (about 5 h 4 m, reset about midnight PST Nov 13).
- The key is accepted (no 400 API_KEY_INVALID any more); the free-tier daily embedding quota is exhausted. Code uses gemini-embedding-001, not text-embedding-004 (no such model in the live list, see section 8).
- Correction to section 8: the full rebuild in this session reverted the index from Gemini/3072 back to OpenRouter/1536. After the quota resets, run make ingest INGEST_ARGS=--full once to restore Gemini/3072, then re-run make test and the MCP search.
- make test: PASS, Ran 4 tests in 7.251 s, OK, exit 0.
- Section 7.1 search search_docs(auth 模块怎么鉴权, top_k=5): PASS on the OpenRouter index. Rank 1 docs/index.md 0.7127, rank 2 docs/modules/auth/index.md 0.6726, rank 3 docs/modules/auth/index.md 0.6031, rank 4 docs/runbooks/query-mcp.md 0.5714, rank 5 src/auth/jwt.py verify_jwt 0.5411.

### Step 3 - OpenCode to MCP end-to-end: PASS (after a config fix)
- MCP server itself works over stdio: initialize + tools/list returns 5 tools (search_docs, get_doc, get_module_context, list_changed_since, write_doc_suggestion), exit 0.
- First two OpenCode runs (google/gemini-3.5-flash-lite) did NOT use MCP: the model tried list_mcp_resources (no such tool), then read mcp_server.py and ran python kb.search_docs directly. The second run also hit the Gemini chat per-minute quota (generate_content_free_tier_requests, limit 15 per minute, retry 29 s).
- Root cause: the MCP config lived only in .opencode.json, which OpenCode does not load. Copied it to opencode.json (the project config file OpenCode loads). Third run: the model called tools[doc-kb].search_docs({query: auth 模块怎么鉴权, top_k: 5}) through MCP and reported docs/index.md top, docs/modules/auth/index.md, and src/auth/jwt.py. Exit 0. The OpenRouter model route was not needed.
- Note: keep opencode.json (with the mcp section) as the loaded config; .opencode.json is the same content under the old name.

### Step 4 - GitHub backup: BLOCKED (no GitHub auth on Box)
- gh auth status: You are not logged into any GitHub hosts. gh repo create vorholtaseltine-droid/doc-kb --public failed with: To get started with GitHub CLI, please run: gh auth login. Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token. Exit code 4. No repo was created and no remote was added.
- No GH_TOKEN or GITHUB_TOKEN in the Box environment, no git credential helper, no ~/.config/gh, no ~/.gitconfig. Box Secrets holds only GEMINI_API_KEY and OPENROUTER_API_KEY, no GitHub token.
- Next step needs the user: run gh auth login on Box, or add a GitHub token, then run gh repo create vorholtaseltine-droid/doc-kb --public --source . --remote origin --push. Do not invent credentials.
- Toolshelf backup check: ~/toolshelf is not a git repo (no .git) and holds update.py, update.py.bak, data.json, index.html and .env (107 bytes; never push .env to a public repo). ~/toolshelf-public is not a git repo either (data.json, index.html). So toolshelf update.py + .env are NOT backed up in git anywhere on Box.
- OpenCode config backup check: .opencode.json IS tracked in git (git ls-files). opencode.json (new file this session) is untracked until the commit below; neither file is ignored.

### Step 5 - Close-out
- This section is the close-out. Credits remaining 4,078. Box main left Running.
- Commit below includes: embedder.py (header auth + retries, from section 8), HANDOVER.md (sections 8-9), opencode.json (MCP config in the loaded filename).
- Still open after this session: (1) Gemini embedding quota until about midnight PST Nov 13, then re-run the full Gemini ingest; (2) GitHub backup, needs GitHub auth from the user.

### Device-flow retry 2026-11-13 03:18-03:34 UTC (continuation)
- gh auth login --web gave device code D45D-BD76 (host github.com, HTTPS). Code entered at github.com/login/device as vorholtaseltine-droid.
- The Authorize github button on the confirmation page was disabled at first (two page loads, 60 s wait, expanding a scope did not enable it); it became enabled later and was clicked.
- GitHub then required sudo-mode re-authentication and sent an email verification code to v**************@gmail.com (19:22 PST). The code was requested from Muse, but Muse reported it had expired by 19:33 PST, so it was never entered. No new email was triggered and no code was guessed.
- Result: gh auth login did NOT complete. gh auth status still says: You are not logged into any GitHub hosts. No gh auth process is running. No repo was created, no remote was added, nothing was pushed. Local commit bb00f70 is intact.
- The toolshelf .env token was not used, as instructed (read-only token). No .env file exists in doc-kb and .env is ignored (.gitignore line 39).
- To retry later: run gh auth login --web again for a fresh device code, and complete the sudo-mode email step promptly (the emailed code is single-use and short-lived).
