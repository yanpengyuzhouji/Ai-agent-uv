# 张雪峰视角 AI 智能体 (ZhangXuefeng LLM Agent) V2.0

本项目是一个成熟的企业级 AI 智能体系统，通过搭载特制的系统提示词与思维框架（Skill），化身“张雪峰”为人解答报考、升学、职场及人生规划问题。

随着 V2.0 的发布，系统已从原本单纯的“问答机器人”跨世代跃升为了具备**工具链调用（Tool Calling）**与**全网自运转检索**的**高级智能体（Agent）**架构。

## ✨ 核心特性升级 / Features 2.0

- **🤖 ReAct Agent 架构**：彻底抛弃封闭的单纯 LLM 链式问答，底层升级为 LangChain Agent 原生架构，赋予大模型自主反思与调用工具链的逻辑决策能力。
- **🌐 实时网页数据检索引擎 (Tavily Search)**：
  - **动态真值核验**：每当面对像某年某高校分数线、实时录取政策、突发新闻等时效性问题时，AI 不再“瞎编”，而是主动执行搜索引擎指令。
  - **Tavily 专线护航**：通过企业级的 Tavily Search API，直接穿透反爬虫体系，一次调用即可在数秒内整理多个权威页面的净数据结果反哺给大模型。
  - **检索动效呈现**：完全打通的 Event-Stream，前端完美渲染类似人在操作电脑获取信息的实时动态 UI（`🔍 [老张正在全网检索...]`）。
- **👑 千亿级重装主力大模型**：主节点直接接管为阿里云百炼底座上的顶级大模型 `qwen3.5-397b-a17b`，确保在海量互联网嘈杂数据提取下具备恐怖的语义合成与逻辑抗压能力。
- **🚀 固态高可用容灾配置 (Fallback)**：
  - **常态化双保底机制**：为防止主大模型或网络连接闪断，底层框架设置了静态逃生口。只要遇到异常挂掉报错，请求将在一瞬间顺滑下放接管到备选云端模型（`qwen3.6-35b-a3b`）代为作答，用户全过程享受无感响应。
- **💾 实体级流式记忆网格 (SQLite Persistence)**：
  - 拥有极其丝滑的 Web 前端逻辑控制，彻底解决了浏览器刷新遗留缓存覆盖的问题。
  - 点击左侧多对话树干流通道热切换历史记录，随时接续长达一天的长途报考交谈。

---

## 🛠️ 技术栈核心 / Tech Stack

- **调度大脑**：LangChain Classic Agents (`create_tool_calling_agent`)
- **信息雷达**：Tavily Search 工具集
- **引擎核**：Qwen3.5-397b-a17b (Bailian 云端主线) / Qwen3.6-35b-a3b (备灾支线)
- **基建体系**：FastAPI 后端微服务框架、原生 HTML/JS 异步前端渲染、uv 包与依赖级管理。

---

## 🚀 部署指南 / Getting Started

### 1. 完善并挂载环境变量
利用 `uv` 进行零痛点自动拉取所需配置的模板系统：
```bash
cp .env.example .env
```
随后编辑你的 `.env`，确保以下两大关键齿轮正常嵌合运转：
- 填写阿里云百炼的：`DASHSCOPE_API_KEY=sk-xxxx`
- 填写前往 Tavily (每月提供 1000 次免费 Agent 查询额度) 拿到的：`TAVILY_API_KEY=tvly-xxxx`

### 2. 秒启动服务 API 接口
只需要一条带有魔法依赖隔离系统（uv）的命令：
```bash
uv run python zhangxuefeng_api.py
```
*(你将会看到 0 毫秒级的响应提示你：“已成功挂载 Tavily 强力搜索网关...”)*

> **入口矩阵**：
> 主工作站台：[http://localhost:8000/app](http://localhost:8000/app)
> OpenAPI 调试台：[http://localhost:8000/docs](http://localhost:8000/docs)
> 健康巡检心跳：[http://localhost:8000/health](http://localhost:8000/health)

---

## 📅 下游改进路线 (Roadmap v3.0)
- [ ] **Agentic RAG 私有知识库**：未来可以将张雪峰曾经写过的报考手册和独家视频文档（PDF/Markdown 等形式）切片为向量库，使其在通用检索之外增加“内部秘籍”查询技能项。
- [ ] **微信 / 飞书 宿主应用接入**：通过 FastApi 回调进行二次开发，将这个有独立记忆和反思搜索能力的 Agent 变成公众号后台客服机器人。
