# main.py — Gemini + FastAPI + S2 工具集成（已按“迁移到 Google GenAI SDK”指南改造）
import os
import time
from pathlib import Path

import jwt
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ✅ 新版 SDK：统一的 Client 入口
from google import genai
from google.genai import types

# ---------- 基础设置 ----------
BASE_DIR = Path(__file__).parent
app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# 环境变量
JWT_SECRET = os.getenv("JWT_SECRET")
S2_BASE_URL = os.getenv("S2_BASE_URL")
# 新版 SDK 会自动从 GEMINI_API_KEY 或 GOOGLE_API_KEY 读取密钥
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY environment variable is not set.")

# ✅ 新 SDK 初始化（Client 统一入口；不再使用 genai.configure / GenerativeModel）
client = genai.Client(api_key=GEMINI_API_KEY)

# ---------- 数据模型 ----------
class UserRequest(BaseModel):
    user_prompt: str

# ---------- JWT ----------
def create_short_lived_jwt(session_id: str) -> str:
    """生成有效期 60 秒的 JWT。"""
    if not JWT_SECRET:
        raise Exception("JWT_SECRET is not configured.")
    now = int(time.time())
    payload = {"session_id": session_id, "exp": now + 60, "iat": now}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token.decode("utf-8") if isinstance(token, bytes) else token

# ---------- 工具定义 ----------
# 新 SDK 推荐：通过 Tool(function_declarations=[...]) 提供函数声明（OpenAPI 子集）
FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_google_calendar_events",
        description="查询 Google Calendar 以获取特定日期（例如今天或明天）的用户会议和日程安排。",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "date": types.Schema(
                    type=types.Type.STRING,
                    description='要查询的日期，格式 YYYY-MM-DD 或 "today", "tomorrow"',
                )
            },
            required=["date"],
        ),
    ),
    types.FunctionDeclaration(
        name="search_the_web",
        description="使用 Brave Search（或任何通用搜索引擎）查询最新的公开信息。",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="要搜索的查询字符串",
                )
            },
            required=["query"],
        ),
    ),
]

TOOLS = [types.Tool(function_declarations=FUNCTION_DECLARATIONS)]

# ---------- 主处理逻辑 ----------
@app.post("/api/process")
async def process_request(request: UserRequest):
    if not S2_BASE_URL:
        raise HTTPException(
            status_code=500, detail="Server configuration is incomplete (S2_BASE_URL)."
        )

    session_id = f"session-{int(time.time())}"

    try:
        # 🧠 第一次调用：让 Gemini 决定要不要调用工具（新 SDK：通过 client.models.generate_content）
        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents=request.user_prompt,
            # 在新 SDK 中，工具通过 GenerateContentConfig 传入；也可直接传 tools=...（等价）
            config=types.GenerateContentConfig(tools=TOOLS),
        )

        # 查看 Gemini 是否想调用函数（新 SDK 提供 response.function_calls）
        if getattr(resp, "function_calls", None):
            fc = resp.function_calls[0]
            func_name = fc.name
            # fc.args 是 Mapping[str, Any]，转成普通 dict 便于序列化
            func_args = dict(fc.args)

            print(f"🔧 Gemini decided to call tool: {func_name}({func_args})")

            # 生成 JWT 并调用 S2
            jwt_token = create_short_lived_jwt(session_id)
            s2_endpoint = f"{S2_BASE_URL}/api/tool-execute"
            s2_response = requests.post(
                s2_endpoint,
                headers={"Authorization": f"Bearer {jwt_token}"},
                json={"tool_name": func_name, "arguments": func_args},
                timeout=30,
            )
            s2_response.raise_for_status()
            tool_result = s2_response.json().get("result")

            # 🧠 第二次调用：把 S2 的结果再喂给 Gemini 生成最终回答
            # 注意：from_text 必须使用命名参数 text=...
            followup_contents = [
                # 用户原始问题（命名参数）
                types.Content(role="user", parts=[types.Part.from_text(text=request.user_prompt)]),
                # 模型的上一轮响应（保持原样，以保留 thought signatures）
                resp.candidates[0].content,
                # 工具执行结果作为 function_response 传回模型
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=func_name, response={"result": tool_result}
                        )
                    ],
                ),
            ]

            resp2 = client.models.generate_content(
                model=MODEL_NAME,
                contents=followup_contents,
            )

            return {
                "message": "Tool executed via S2, final answer generated by LLM.",
                "action": f"Called S2 for tool: {func_name}",
                "tool_result": tool_result,
                "llm_result": getattr(resp2, "text", None),
            }

        # 否则，Gemini 直接回答
        return {
            "message": "Answer provided directly by LLM.",
            "action": "Direct LLM Response",
            "llm_result": getattr(resp, "text", None),
        }

    except requests.HTTPError as e:
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Error communicating with MCP server (S2): {detail}",
        )
    except Exception as e:
        print(f"Internal Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# ---------- 静态首页 ----------
@app.get("/")
def index():
    index_file = BASE_DIR / "static" / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_file)

# ---------- 本地调试 ----------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
