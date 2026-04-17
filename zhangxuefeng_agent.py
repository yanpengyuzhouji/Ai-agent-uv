"""
张雪峰视角智能体 - 基于 SKILL.md 构建
========================================
将 .agents/skills/zhangxuefeng-perspective/SKILL.md 中的角色设定
提取为 System Prompt，注入到你自己部署的模型中。

支持两种后端：
  1. 本地 Ollama 模型（如 qwen3:8b）
  2. 阿里云百炼 API（如 qwen3.5-397b-a17b）

用法：
  python zhangxuefeng_agent.py                # 默认使用 Ollama
  python zhangxuefeng_agent.py --backend bailian  # 使用百炼
"""

import os
import sys
import io
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # 加载 .env 环境变量

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage


# ============================================================
# 1. 从 SKILL.md 提取 System Prompt
# ============================================================

def load_skill_as_system_prompt(skill_path: str = None) -> str:
    """
    读取 SKILL.md，去掉 YAML frontmatter，将正文作为 system prompt。
    """
    if skill_path is None:
        # 自动定位 SKILL.md（相对于本项目根目录）
        project_root = Path(__file__).parent
        skill_path = project_root / ".agents" / "skills" / "zhangxuefeng-perspective" / "SKILL.md"

    skill_path = Path(skill_path)
    if not skill_path.exists():
        raise FileNotFoundError(
            f"找不到 SKILL.md: {skill_path}\n"
            "请确认已通过 `npx skills add alchaincyf/zhangxuefeng-skill` 安装"
        )

    # 读取原始字节，避免 Windows 下 read_text() 引入 surrogate 字符
    import re
    raw_bytes = skill_path.read_bytes()

    # 去掉 BOM 头（如果有）
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        raw_bytes = raw_bytes[3:]

    # 解码，用 replace 处理任何无效字节
    content = raw_bytes.decode("utf-8", errors="replace")

    # 移除所有 Unicode 代理字符（U+D800 ~ U+DFFF），防止 JSON 序列化报错
    content = re.sub(r'[\ud800-\udfff]', '', content)

    # 移除 \r，统一换行符
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # 去掉 YAML frontmatter（--- ... --- 之间的内容）
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    return content


# ============================================================
# 2. 构建 LLM 实例
# ============================================================

def create_ollama_llm(model: str = "qwen3:8b"):
    """使用本地 Ollama 模型"""
    from langchain_ollama.chat_models import ChatOllama
    return ChatOllama(
        model=model,
        temperature=0.7,
        num_ctx=8192,   # 上下文窗口，skill 内容较长需要足够的空间
    )


def create_bailian_llm(model: str = "qwen3.5-397b-a17b"):
    """使用阿里云百炼 API"""
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError(
            "请设置环境变量 DASHSCOPE_API_KEY\n"
            "例如: set DASHSCOPE_API_KEY=sk-xxxx  (Windows)\n"
            "  或: export DASHSCOPE_API_KEY=sk-xxxx  (Linux/Mac)"
        )

    return ChatOpenAI(
        model=model,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=SecretStr(api_key),
        temperature=0.7,
    )


# ============================================================
# 3. 构建对话链（带多轮记忆）
# ============================================================

def build_chain(llm, system_prompt: str):
    """
    构建一个带 system prompt 和多轮对话历史的 Chain。

    结构：
      - system: SKILL.md 的全部内容（角色设定 + 心智模型 + 表达DNA）
      - history: 多轮对话历史（MessagesPlaceholder）
      - user: 当前用户输入
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="history"),
        ("user", "{input}"),
    ])

    chain = prompt | llm
    return chain


# ============================================================
# 4. 交互式对话循环
# ============================================================

def chat_loop(chain):
    """多轮交互式对话"""
    history = []  # 对话历史

    print("=" * 60)
    print("  张雪峰视角智能体")
    print("  输入你的问题，输入 'quit' 或 'exit' 退出")
    print("  输入 '退出角色' 恢复正常模式")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！记住——选择比努力更重要。")
            break

        # 调用模型（流式输出）
        print("\n张雪峰: ", end="", flush=True)

        full_response = ""
        try:
            for chunk in chain.stream({
                "input": user_input,
                "history": history,
            }):
                # 兼容不同模型返回格式
                text = chunk.content if hasattr(chunk, "content") else str(chunk)
                print(text, end="", flush=True)
                full_response += text
        except Exception as e:
            print(f"\n\n[错误] 模型调用失败: {e}")
            continue

        print("\n")

        # 记录对话历史
        history.append(HumanMessage(content=user_input))
        history.append(AIMessage(content=full_response))

        # 限制历史长度，避免超出上下文窗口
        # 保留最近10轮对话（20条消息）
        if len(history) > 20:
            history = history[-20:]


# ============================================================
# 5. 主入口
# ============================================================

def main():
    # 修复 Windows 终端编码：stdin/stdout/stderr 默认使用 GBK + surrogateescape
    # 这会导致中文输入变成代理字符(surrogate)，后续 JSON 序列化会报错
    if sys.platform == "win32":
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        os.system("chcp 65001 >nul 2>&1")

    parser = argparse.ArgumentParser(description="张雪峰视角智能体")
    parser.add_argument(
        "--backend", choices=["ollama", "bailian"], default="ollama",
        help="选择模型后端: ollama(本地) 或 bailian(百炼云端)"
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="指定模型名称 (默认: ollama=qwen3:8b, bailian=qwen3.5-397b-a17b)"
    )
    parser.add_argument(
        "--skill-path", type=str, default=None,
        help="SKILL.md 文件路径 (默认自动查找)"
    )
    args = parser.parse_args()

    # 1. 加载 SKILL.md 作为 system prompt
    print("[*] 加载 SKILL.md ...")
    system_prompt = load_skill_as_system_prompt(args.skill_path)
    print(f"[*] System prompt 已加载 ({len(system_prompt)} 字符)")

    # 2. 创建 LLM
    if args.backend == "ollama":
        model_name = args.model or "qwen3:8b"
        print(f"[*] 使用 Ollama 本地模型: {model_name}")
        llm = create_ollama_llm(model_name)
    else:
        model_name = args.model or "qwen3.5-397b-a17b"
        print(f"[*] 使用百炼云端模型: {model_name}")
        llm = create_bailian_llm(model_name)

    # 3. 构建对话链
    chain = build_chain(llm, system_prompt)

    # 4. 启动对话
    chat_loop(chain)


if __name__ == "__main__":
    main()
