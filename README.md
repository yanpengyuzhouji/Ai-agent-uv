# 张雪峰视角 AI 智能体 (ZhangXuefeng LLM Agent)

本项目是一个成熟的企业级 AI 智能体系统，通过搭载特制的系统提示词与思维框架（Skill），化身“张雪峰”为人解答报考、升学、职场及人生规划问题。

本项目兼具优雅的现代前端界面与稳定高可用的后端架构，支持跨设备访问与平滑的流式输出，并且针对本地与云端模型实现了无缝容灾切换。

## ✨ 核心特性 / Features

- **🎓 特调人格引擎**：深度集成《张雪峰视角》思维模板（SKILL.md），不提供“政治正确”的废话，只提供“毒舌但极其现实考量”的分析机制。
- **🚀 高可用容灾双活部署 (Fallback)**：
  - 支持 **Ollama** 本地开源模型与 **阿里云百炼** (Bailian) 等云端闭源模型双后端。
  - **无缝灾备熔断**：配置主引擎后，若突发主引擎崩溃断网或显存不足，LangChain 驱动层会在极短时间内静默降级切换至备用引擎，确保前端用户连贯无感应继续对话。
- **💾 实体级流式记忆网格 (SQLite Persistence)**：
  - 弃用传统的局限性内存对话状态，实现了本地轻量化 SQLite 持久存储。
  - Web 客户端不论如何刷新（F5），甚至遭遇服务器发版重启及闪退，所有历史多路并发对话上下文均100%瞬间复活重载保障。
- **⚡ 丝滑极简响应式 Web 界面**：
  - 不依赖庞大的 Node.js React/Vue，开箱即用的原生 JS 轻量化深色主题卡片式 UI 界面。
  - 实现 Server-Sent Events (SSE) 协议交互原生流式打字机效果。
- **🛡️ 企业级 API 与日志**：
  - **API 限流与鉴权锁**：具备完整的 .env 隔离机制以及 `API_SECRET_KEY` 接口防护层。
  - **诊断级本地溯源**：配备带有 Request 健康探针与本地文件化落盘系统（`/data/app.log`），方便监控平台（如 Prometheus/Grafana）接入追踪错误路由。
- **💻 极致体验兼容**：已通过底层 Windows 系统 GBK / 宽字节乱码的适配清理层，避免任何解码奔溃。

---

## 🛠️ 技术栈 / Tech Stack

- **后端架构**： FastAPI, Uvicorn, LangChain (`langchain-ollama`, `langchain-openai`), Pydantic
- **存储方案**： 内置 Sqlite3
- **环境隔离**： python-dotenv (`.env`)
- **包管理器**： 超快 `uv` 生态
- **大模引擎**： Qwen3:8b (本地) / Qwen-turbo (云端百炼)

---

## 🗂 代码目录结构
```text
.
├── .agents/skills/      # 核心人格 prompt 定义系统文件
├── data/                # [运行时目录] 系统 SQLite 存储数据与 Logs 日志 
├── frontend/            # 前端 HTML/CSS/JS 完全独立部署层
│   ├── index.html       # 核心对话页
│   ├── app.js           # 处理流式、上下文及 localStorage
│   └── style.css        # 全局响应式样式表
├── .env.example         # 关键环境变量复制模板文件
├── pyproject.toml / uv.lock # 安装依赖锁配置
├── zhangxuefeng_api.py  # 企业级全异步微型后端网关主程序
└── zhangxuefeng_agent.py# (备用) 终端黑框版本启动脚本
```

---

## 🚀 部署指南 / Getting Started

### 1. 配置项目环境
首先需要利用 `uv.lock` 进行依赖的同步更新并新建虚拟配置模板：
```bash
cp .env.example .env
```
随后编辑 `.env` 设置你的配置参数：
- 设置 `BACKEND` 调整是使用本地还是百炼云端。
- 保证填写由百炼申请到的 `DASHSCOPE_API_KEY` 以开启你的高可用灾备底座。
- 如果暴露在外网，请务必设置包含加密字符串的 `API_SECRET_KEY`。

### 2. 启动企业后端 API 与托管站点
只需要一条底层命令：
```bash
uv run python zhangxuefeng_api.py
```
> **访问信息**：
> 默认前端页面：[http://localhost:8000/app](http://localhost:8000/app)
> API 开发者文档：[http://localhost:8000/docs](http://localhost:8000/docs)
> Kubernetes 探活接口：[http://localhost:8000/health](http://localhost:8000/health)

---

## 📅 下游改进路线 (Roadmap v2.0)
- [ ] **接入网页实时检索引擎 (WebSearch Agent)**：未来计划通过 Tavily / DuckDuckGo 将纯对话系统拔升到真正的智能体维度，使大模型拥有获取全网近三天内最新分数线、最新资讯进行深度规划的能力。
