# 张雪峰视角 AI 智能体 (ZhangXuefeng LLM Agent) V2.1

本项目是一个成熟的企业级 AI 智能体系统，通过搭载特制的系统提示词与思维框架（Skill），化身"张雪峰"为人解答报考、升学、职场及人生规划问题。

V2.1 版本在 Agent 架构之上，进一步引入了**万能文档解析引擎**与**多模态视觉理解能力**，支持用户直接上传 PDF/Word/Excel/图片等资料，让老张"看着"你的成绩单和招生简章帮你做分析。

## ✨ 核心特性 / Features

- **🤖 ReAct Agent 架构**：底层基于 LangChain Agent 原生架构，赋予大模型自主反思与调用工具链的逻辑决策能力。
- **🌐 实时网页数据检索引擎 (Tavily Search)**：
  - 面对时效性问题（分数线、政策、新闻）时，AI 主动执行搜索引擎指令获取最新权威数据。
  - 前端实时渲染 `🔍 [老张正在全网检索...]` 的动态效果。
- **📎 万能文档解析 (MarkItDown + Qwen3-VL)**：
  - 支持 **PDF、Word、Excel、PPT、CSV** 等文档格式一键解析为结构化文本。
  - 支持 **JPG、PNG、WebP** 等图片格式，调用阿里云百炼 `qwen3-vl-flash` 视觉模型自动 OCR 提取文字与表格。
  - 上传文件后前端展示可点击的 `📎 文件名` 链接，点击即可在浏览器新标签页预览原始文件。
  - 原始文件持久化存储在服务端 `data/uploads/`，支持随时回看。
- **👑 千亿级主力大模型**：主节点使用阿里云百炼 `qwen3.5-397b-a17b`，确保恐怖的语义合成与逻辑抗压能力。
- **🚀 固态高可用容灾 (Fallback)**：主模型异常时自动无感切换至备用模型 `qwen3.6-35b-a3b`。
- **🕐 时间锚点注入**：每次请求动态注入当前北京时间，彻底消灭大模型的日期幻觉。
- **💾 SQLite 会话持久化**：多对话树切换、浏览器刷新不丢失历史记录。
- **🛡️ 全链路日志监控**：包含 422 参数校验拦截在内的所有异常均写入 `data/app.log`。

---

## 🛠️ 技术栈 / Tech Stack

| 层级 | 技术 |
|------|------|
| 调度大脑 | LangChain Classic Agents (`create_tool_calling_agent`) |
| 信息雷达 | Tavily Search 工具集 |
| 文档解析 | 微软 MarkItDown (`markitdown[all]`) |
| 视觉识别 | 阿里云百炼 Qwen3-VL-Flash（图片 OCR） |
| 主力模型 | Qwen3.5-397b-a17b (Bailian) |
| 容灾模型 | Qwen3.6-35b-a3b (Bailian) |
| 后端框架 | FastAPI + SSE 流式输出 |
| 前端渲染 | 原生 HTML/JS 异步渲染 |
| 包管理 | uv 依赖级管理 |

---

## 🚀 部署指南 / Getting Started

### 1. 配置环境变量
```bash
cp .env.example .env
```
编辑 `.env`，填写：
- `DASHSCOPE_API_KEY=sk-xxxx`（阿里云百炼密钥）
- `TAVILY_API_KEY=tvly-xxxx`（Tavily 搜索密钥，每月 1000 次免费额度）

### 2. 启动服务
```bash
uv run python zhangxuefeng_api.py
```

> **入口矩阵**：
> - 主工作站台：[http://localhost:8000/app](http://localhost:8000/app)
> - OpenAPI 调试台：[http://localhost:8000/docs](http://localhost:8000/docs)
> - 健康巡检心跳：[http://localhost:8000/health](http://localhost:8000/health)

---

## 📅 Roadmap v3.0
- [ ] Agentic RAG 私有知识库（PDF/Markdown 切片向量库）
- [ ] 微信 / 飞书宿主应用接入
- [ ] Python 代码执行器（Code Interpreter），支持数据分析与可视化
