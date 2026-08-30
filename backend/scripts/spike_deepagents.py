"""Task 1 spike：锁定 deepagents 0.7.11 的关键接口形状

注：brief 初稿用 async astream + PostgresSaver，实测 langgraph-checkpoint-postgres
3.1.2 的 PostgresSaver 为纯同步实现（aget_tuple 未实现，异步版 AsyncPostgresSaver
位于 langgraph.checkpoint.postgres.aio 且未从顶层模块导出）。EAP 生产环境为
Flask + gevent 同步 graph.stream()，故此处改用同步 stream 以对齐生产形状。
"""
import inspect
from dotenv import load_dotenv
load_dotenv("/home/wangyan/deploy/eap/backend/.env")

# 1. SandboxBackendProtocol 接口
from deepagents.backends.protocol import BackendProtocol, SandboxBackendProtocol
print("=== BackendProtocol methods ===")
for name in ["ls", "read", "write", "edit", "glob", "grep"]:
    m = getattr(BackendProtocol, name, None)
    if m: print(name, inspect.signature(m))
print("=== SandboxBackendProtocol methods ===")
for name in ["execute"]:
    m = getattr(SandboxBackendProtocol, name, None)
    if m: print(name, inspect.signature(m))

# 2. create_deep_agent 签名
from deepagents import create_deep_agent
print("=== create_deep_agent ===")
print(inspect.signature(create_deep_agent))

# 3. 最小图流式冒烟（DeepSeek 模型 + 双流模式，同步 stream 对齐生产）
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg_pool
import os

# DATABASE_URL 来自 .env（load_dotenv 已加载，真实密码不内联）
pool = psycopg_pool.ConnectionPool(
    os.getenv("DATABASE_URL", ""),
    min_size=1, max_size=2, open=True, timeout=10)
checkpointer = PostgresSaver(pool)
# 不调用 setup()：3.1.2 的迁移含 CREATE INDEX CONCURRENTLY，在池连接的事务模式
# 下会报 ActiveSqlTransaction；且生产库 checkpoint 表已存在（EAP 生产同样不调 setup）

llm = ChatOpenAI(model="deepseek-v4-pro", api_key=os.getenv("DEEPSEEK_API_KEY"),
                 base_url="https://api.deepseek.com/v1", max_tokens=256, stream_usage=True)
graph = create_deep_agent(model=llm, tools=[], checkpointer=checkpointer)

def main():
    config = {"configurable": {"thread_id": "spike:1:test"}}
    for item in graph.stream({"messages": [("user", "列出你的可用工具，不要调用")]},
                             config, stream_mode=["messages", "updates"]):
        mode, payload = item
        if mode == "messages":
            chunk, meta = payload
            if getattr(chunk, "content", None):
                print("MSG chunk:", repr(chunk.content)[:40])
        else:
            for node, out in payload.items():
                # 实测：updates 的 value 可能为 None（节点未产出状态更新）
                out = out or {}
                print("UPDATE node:", node, "| keys:", list(out.keys())[:6],
                      "| msgs:", [type(m).__name__ for m in out.get("messages", [])][:6])

main()
