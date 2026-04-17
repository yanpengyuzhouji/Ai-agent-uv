"""
张雪峰视角智能体 API (生产级版本)
========================================
功能：REST API + SSE 流式输出，支持 SQLite 记忆持久化、异步请求、API 防护。
"""

import os
import sys
import io
import re
import uuid
import json
import sqlite3
import argparse
import logging
import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security, Request, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, messages_to_dict, messages_from_dict


# ============================================================
# 初始化配置与日志
# ============================================================
load_dotenv()

Path("./data").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./data/app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ZhangXuefengAPI")

# ============================================================
# 持久化会话管理 (SQLite)
# ============================================================
class SessionManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    messages TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def get_session(self, session_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT messages FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    msgs_dict = json.loads(row[0])
                    return messages_from_dict(msgs_dict)
                except Exception as e:
                    logger.error(f"解析会话 {session_id} 历史失败: {e}")
            return []

    def save_session(self, session_id: str, history: list):
        # 限制历史长度
        if len(history) > 20:
            history = history[-20:]
        try:
            msgs_dict = messages_to_dict(history)
            msgs_json = json.dumps(msgs_dict, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO sessions (session_id, messages, updated_at) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id) DO UPDATE SET 
                        messages=excluded.messages,
                        updated_at=CURRENT_TIMESTAMP
                ''', (session_id, msgs_json))
                conn.commit()
        except Exception as e:
            logger.error(f"保存会话 {session_id} 失败: {e}")

    def get_all_sessions(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT session_id, messages FROM sessions ORDER BY updated_at DESC")
            return cursor.fetchall()

    def delete_session(self, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def clear_all(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions")
            conn.commit()


# ============================================================
# 全局状态
# ============================================================
_chain = None
_info: dict = {}
_session_manager: SessionManager = None


# ============================================================
# 安全机制：API 鉴权
# ============================================================
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "").strip()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)

async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(http_bearer)
):
    if not API_SECRET_KEY:  # 如果没设置，则放行
        return True
    
    token = api_key or (bearer.credentials if bearer else None)
    if not token or token != API_SECRET_KEY:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. 请提供正确的 X-API-Key 头部或 Bearer Token",
        )
    return True


# ============================================================
# 1. SKILL.md 加载
# ============================================================
def load_skill_as_system_prompt(skill_path: str = None) -> str:
    if skill_path is None:
        project_root = Path(__file__).parent
        skill_path = project_root / ".agents" / "skills" / "zhangxuefeng-perspective" / "SKILL.md"

    skill_path = Path(skill_path)
    if not skill_path.exists():
        raise FileNotFoundError(f"找不到 SKILL.md: {skill_path}")

    raw_bytes = skill_path.read_bytes()
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        raw_bytes = raw_bytes[3:]

    content = raw_bytes.decode("utf-8", errors="replace")
    content = re.sub(r'[\ud800-\udfff]', '', content)
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    return content


# ============================================================
# 2. LLM 工厂
# ============================================================
def create_llm(backend: str = "ollama", model: str = None):
    if backend == "ollama":
        from langchain_ollama.chat_models import ChatOllama
        return ChatOllama(
            model=model or "qwen3:8b",
            temperature=0.7,
            num_ctx=8192,
        )
    elif backend == "bailian":
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("请设置环境变量 DASHSCOPE_API_KEY")

        return ChatOpenAI(
            model=model or "qwen3.5-397b-a17b",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=SecretStr(api_key),
            temperature=0.7,
        )
    else:
        raise ValueError(f"不支持的 backend: {backend}")


def build_chain(llm, system_prompt: str):
    from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
    from langchain_community.tools.tavily_search import TavilySearchResults

    tools = []
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    
    if tavily_api_key:
        # 添加全网搜索实时验证武器
        tools.append(TavilySearchResults(max_results=3, tavily_api_key=tavily_api_key))
        logger.info("✅ 已挂载 Tavily 强力搜索网关，大模型现已具备全网实时获取最新分数线/招生资讯的能力！")
        
        system_prompt += (
            "\n\n【极其重要的指令】：\n"
            "当你遇到需要最新数据（如具体某年大学的分数线、招生变动、新录取规定、实时国家政策）时，"
            "**绝对不准**使用你记忆里可能过时的数据去瞎编或者估算！\n"
            "你必须立即调用搜索工具 `tavily_search_results_json` 在全网查询最新权威结果！"
            "\n如果未提供工具，则尽力依靠常识作答。"
        )

    # 添加现实世界绝对时间参考
    time_anchor = "\n\n【现实世界锚点】：当前系统真实北京时间是 {current_time}。如果用户问现在的时间或日期，或者推断年份，以此为绝对物理准绳，不要有任何怀疑和幻觉！"
    
    # Agent 需要特定的 Scratchpad 以存放中间步骤
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt + time_anchor),
        MessagesPlaceholder(variable_name="history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    if tools:
        # 当具备工具时，将其包装为智能体执行器
        try:
            agent = create_tool_calling_agent(llm, tools, prompt)
            return AgentExecutor(agent=agent, tools=tools, verbose=True)
        except Exception as e:
            logger.error(f"代理挂载失败，降级为普通链式模式: {e}")
            
    # 如果没配置 Tavily 密钥或者失败，这只是一个普通链
    # 但如果是普通链，我们需要去掉 agent_scratchpad 参数才能正常跑
    prompt_safe = ChatPromptTemplate.from_messages([
        ("system", system_prompt + time_anchor),
        MessagesPlaceholder(variable_name="history"),
        ("user", "{input}"),
    ])
    return prompt_safe | llm


# ============================================================
# 3. 请求/响应模型 (加强验证)
# ============================================================
class ChatRequest(BaseModel):
    message: str = Field(..., max_length=150000, description="用户消息（包含附件）")
    session_id: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9_-]{1,50}$", description="会话ID，限50个字母数字或横线")
    stream: bool = Field(False, description="是否使用流式输出(SSE)")


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    last_message: Optional[str] = None


class MessageInfo(BaseModel):
    role: str
    content: str


class SessionDetail(BaseModel):
    session_id: str
    messages: list[MessageInfo]


class ServerInfo(BaseModel):
    name: str = "张雪峰视角智能体 API (生产级)"
    version: str = "1.1.0"
    backend: str
    model: str
    system_prompt_length: int
    status: str = "ok"


# ============================================================
# 4. FastAPI 应用构建
# ============================================================
def create_app(backend: str = "ollama", model: str = None, skill_path: str = None) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _chain, _info, _session_manager

        # 初始化会话管理类，若未配置环境变量使用默认路径 ./data/sessions.db
        db_path = os.getenv("SESSION_DB_PATH", "./data/sessions.db")
        _session_manager = SessionManager(db_path)
        logger.info(f"会话持久化存储已连接: {db_path}")

        # 使用配置文件读取，如果命令行没传，使用 .env 的值
        actual_backend = backend or os.getenv("BACKEND", "ollama")
        actual_model = model or os.getenv("MODEL_NAME")

        system_prompt = load_skill_as_system_prompt(skill_path)
        
        default_model = "qwen3:8b" if actual_backend == "ollama" else "qwen3.5-397b-a17b"
        model_name = actual_model or default_model
        
        llm = create_llm(actual_backend, model_name)
        
        # 添加高可用回退机制：如果主模型挂掉，自动无缝切换到备用模型
        fallback_backend = "bailian"
        fallback_model = "qwen3.6-35b-a3b"
        try:
            fallback_llm = create_llm(fallback_backend, fallback_model)
            llm = llm.with_fallbacks([fallback_llm])
            logger.info(f"开启高可用回退机制 (Fallback): {fallback_backend} / {fallback_model}")
        except Exception as e:
            logger.warning(f"未能配置模型回退容灾机制 (若需要请确保另一个后端的变量正确): {e}")

        _chain = build_chain(llm, system_prompt)

        _info.update({
            "backend": actual_backend,
            "model": model_name,
            "system_prompt_length": len(system_prompt),
        })

        logger.info(f"SKILL.md 已加载 ({len(system_prompt)} 字符)")
        logger.info(f"模型后端连接成功: {actual_backend} / {model_name}")
        if API_SECRET_KEY:
            logger.info("API 鉴权已开启")
        else:
            logger.warning("API 鉴权未开启！生产环境请配置 API_SECRET_KEY")

        yield

        logger.info("API 服务已清理关闭")

    app = FastAPI(
        title="张雪峰视角智能体 API",
        description="企业级 AI 对话服务接口",
        version="1.1.0",
        lifespan=lifespan,
    )

    # 严格读取 CORS_ORIGINS
    cors_str = os.getenv("CORS_ORIGINS", "*")
    origins = [o.strip() for o in cors_str.split(",")] if cors_str else []

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True if "*" not in origins else False, # 开启凭据不允许出现通配符 *
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    return app

app = FastAPI(title="placeholder")


# ============================================================
# 5. API 路由
# ============================================================
def register_routes(app: FastAPI):
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error(f"422 参数校验拦截 | 请求体不合法: {exc.errors()} | Body: {exc.body}")
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "body": str(exc.body)},
        )

    @app.get("/health", response_model=ServerInfo, tags=["系统"])
    async def health_check():
        """健康检查，K8s 探针适用"""
        return ServerInfo(
            backend=_info.get("backend", "unknown"),
            model=_info.get("model", "unknown"),
            system_prompt_length=_info.get("system_prompt_length", 0),
            status="ok"
        )

    @app.get("/", response_model=ServerInfo, tags=["系统"])
    async def get_info(authorized: bool = Depends(verify_api_key)):
        """获取服务器信息"""
        return await health_check()

    @app.post("/chat", response_model=ChatResponse, tags=["对话"])
    async def chat(req: ChatRequest, authorized: bool = Depends(verify_api_key)):
        if _chain is None:
            raise HTTPException(status_code=503, detail="模型尚未初始化")

        session_id = req.session_id or str(uuid.uuid4())[:8]
        history = _session_manager.get_session(session_id)

        if req.stream:
            return StreamingResponse(
                _stream_response(req.message, session_id, history),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Session-Id": session_id,
                },
            )

        try:
            # 异步非阻塞调用 (ainvoke)
            result = await _chain.ainvoke({
                "input": req.message,
                "history": history,
                "current_time": datetime.datetime.now().strftime("%Y年%m月%d日 %A"),
            })
            
            # Agent返回的是dict带output，普通链返回的是AIMessage
            if isinstance(result, dict) and "output" in result:
                reply = result["output"]
            elif hasattr(result, "content"):
                reply = result.content
            else:
                reply = str(result)
        except Exception as e:
            logger.error(f"模型调用异常 (ainvoke): {str(e)}")
            raise HTTPException(status_code=500, detail=f"模型调用失败: {str(e)}")

        history.append(HumanMessage(content=req.message))
        history.append(AIMessage(content=reply))
        
        # 保存持久化历史记录
        _session_manager.save_session(session_id, history)

        return ChatResponse(reply=reply, session_id=session_id)

    @app.get("/sessions", response_model=list[SessionInfo], tags=["会话管理"])
    async def list_sessions(authorized: bool = Depends(verify_api_key)):
        result = []
        rows = _session_manager.get_all_sessions()
        for sid, msgs_json in rows:
            last_msg = None
            try:
                msgs = messages_from_dict(json.loads(msgs_json))
                for m in reversed(msgs):
                    if isinstance(m, HumanMessage):
                        last_msg = m.content[:50]
                        break
                result.append(SessionInfo(
                    session_id=sid,
                    message_count=len(msgs),
                    last_message=last_msg,
                ))
            except Exception:
                pass
        return result

    @app.get("/sessions/{session_id}", response_model=SessionDetail, tags=["会话管理"])
    async def get_session_detail(session_id: str, authorized: bool = Depends(verify_api_key)):
        history = _session_manager.get_session(session_id)
        if not history:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        out_msgs = []
        for msg in history:
            role = "user" if isinstance(msg, HumanMessage) else "ai"
            out_msgs.append(MessageInfo(role=role, content=msg.content))
            
        return SessionDetail(session_id=session_id, messages=out_msgs)

    @app.delete("/sessions/{session_id}", tags=["会话管理"])
    async def delete_session(session_id: str, authorized: bool = Depends(verify_api_key)):
        _session_manager.delete_session(session_id)
        return {"message": f"会话 {session_id} 已删除"}

    @app.delete("/sessions", tags=["会话管理"])
    async def clear_sessions(authorized: bool = Depends(verify_api_key)):
        _session_manager.clear_all()
        return {"message": "已清空所有会话"}

    @app.post("/upload", tags=["文件处理"])
    async def upload_file(file: UploadFile = File(...), authorized: bool = Depends(verify_api_key)):
        """万能文档解析，基于微软 MarkitDown。持久化存储原始文件供前端回看。"""
        from markitdown import MarkItDown
        from openai import OpenAI
        import tempfile
        try:
            suffix = Path(file.filename).suffix
            is_image = suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
            
            # 持久化保存原始文件到 data/uploads/
            uploads_dir = Path("./data/uploads")
            uploads_dir.mkdir(parents=True, exist_ok=True)
            file_id = f"{uuid.uuid4().hex[:12]}{suffix}"
            saved_path = uploads_dir / file_id
            content = await file.read()
            saved_path.write_bytes(content)
            
            # 同时写临时文件供 MarkItDown 解析
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            # 如果是图片格式，借助 OpenAI 客户端外壳路由到百炼视觉大模型
            if is_image:
                client = OpenAI(
                    api_key=os.getenv("DASHSCOPE_API_KEY"),
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
                )
                md = MarkItDown(llm_client=client, llm_model="qwen3-vl-flash-2026-01-22")
            else:
                md = MarkItDown()

            result = md.convert(tmp_path)
            os.remove(tmp_path)
            
            text_context = result.text_content
            if len(text_context) > 10000:
                text_context = text_context[:10000] + "\n\n...(由于内容过大，已自动截断尾部)"

            file_url = f"/uploads/{file_id}"
            return {"filename": file.filename, "markdown": text_context, "file_url": file_url}
        except Exception as e:
            logger.error(f"文件解析失败: {e}")
            raise HTTPException(status_code=500, detail=f"无法解析文件内容: {str(e)}")

    @app.get("/uploads/{file_id}", tags=["文件处理"])
    async def download_file(file_id: str):
        """提供已上传文件的下载/预览"""
        file_path = Path("./data/uploads") / file_id
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(file_path, filename=file_id)


async def _stream_response(message: str, session_id: str, history: list):
    full_response = ""
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    try:
        # 使用异步事件流 astream_events，以支持 Agent 工具调用可视化输出
        async for event in _chain.astream_events({
                "input": message, 
                "history": history,
                "current_time": datetime.datetime.now().strftime("%Y年%m月%d日 %A")
            },
            version="v2"
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, "content") and chunk.content:
                    text = chunk.content
                    # 避免流出思考符号（如果带有）
                    if isinstance(text, str):
                        full_response += text
                        yield f"data: {json.dumps({'type': 'content', 'text': text}, ensure_ascii=False)}\n\n"
            elif kind == "on_tool_start":
                tool_name = event['name']
                query_dict = event['data'].get('input', {})
                query_str = query_dict.get('query', str(query_dict)) if isinstance(query_dict, dict) else str(query_dict)
                msg = f"\n> 🔍 [老张正在全网检索: {tool_name}] 分析关键词：{query_str}...\n\n"
                full_response += msg
                yield f"data: {json.dumps({'type': 'content', 'text': msg}, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.error(f"模型流式输出异常: {str(e)}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        return

    history.append(HumanMessage(content=message))
    history.append(AIMessage(content=full_response))
    _session_manager.save_session(session_id, history)
    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"


# ============================================================
# 6. 主入口
# ============================================================
def main():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="张雪峰视角智能体 API (生产级版本)")
    parser.add_argument("--backend", choices=["ollama", "bailian"], default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--skill-path", type=str, default=None)
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    host = args.host or os.getenv("API_HOST", "0.0.0.0")
    port = args.port or int(os.getenv("API_PORT", "8000"))

    real_app = create_app(
        backend=args.backend,
        model=args.model,
        skill_path=args.skill_path,
    )
    register_routes(real_app)

    frontend_dir = Path(__file__).parent / "frontend"
    if frontend_dir.exists():
        @real_app.get("/app", include_in_schema=False)
        async def serve_frontend():
            return FileResponse(frontend_dir / "index.html")

        real_app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="frontend")

    import uvicorn
    print("\n" + "=" * 60)
    print("  张雪峰视角智能体 API (生产级开启)")
    print(f"  地址: http://{host}:{port}")
    print(f"  前端页面: http://localhost:{port}/app")
    print(f"  健康检查: http://localhost:{port}/health")
    print("=" * 60 + "\n")

    uvicorn.run(real_app, host=host, port=port)


if __name__ == "__main__":
    main()
