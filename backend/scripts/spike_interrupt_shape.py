"""Task 5 spike：实测 deepagents 0.7.11 interrupt 机制的真实字段形状

目标（以实测为准，供 orchestrator 解析代码落地）：
  1. 流结束后 graph.get_state(config).interrupts 的元素形状
  2. resume 值协议（approve / reject / edit 三种决策的真实形状）
  3. reject 后工具是否真的不执行、模型收到什么说明
  4. edit 决策是否生效

checkpointer 用 SQLite（不碰生产 PG）。
"""
import json
import os
from dotenv import load_dotenv
load_dotenv("/home/wangyan/deploy/eap/backend/.env")

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg_pool
from langgraph.types import Command
from deepagents import create_deep_agent

# 与生产一致：PostgresSaver（sqlite saver 2.0.10 与 langgraph 1.2.11 的
# JsonPlusSerializer 接口不兼容，实测 AttributeError: no attribute dumps）
pool = psycopg_pool.ConnectionPool(
    os.getenv("DATABASE_URL", ""), min_size=1, max_size=2, open=True, timeout=10)
checkpointer = PostgresSaver(pool)

llm = ChatOpenAI(model="deepseek-v4-pro", api_key=os.getenv("DEEPSEEK_API_KEY"),
                 base_url="https://api.deepseek.com/v1", max_tokens=2048,
                 temperature=0.3, stream_usage=True)

SYSTEM = (
    "你是一个测试助手。当用户要求写文件时，使用 write_file 工具把内容写入指定文件；"
    "写完后用一句话确认已写入的文件名。"
)

graph = create_deep_agent(
    model=llm,
    tools=[],
    system_prompt=SYSTEM,
    interrupt_on={"write_file": True},   # dict: True = 全部决策允许
    checkpointer=checkpointer,
)

STREAM_MODE = ["messages", "updates"]


def fmt(m, depth=0):
    t = type(m).__name__
    try:
        if t == "ToolMessage":
            return f"ToolMessage(status={m.status}, name={m.name}, id={m.tool_call_id[:8]}, content={str(m.content)[:60]!r})"
        if t == "AIMessage":
            tcs = [(tc["name"], tc["id"][:8], str(tc["args"])[:40]) for tc in (m.tool_calls or [])]
            return f"AIMessage(tool_calls={tcs}, content={str(m.content)[:40]!r})"
        return f"{t}(content={str(getattr(m, 'content', ''))[:40]!r})"
    except Exception as e:
        return f"{t}(repr-err {e})"


def run_stream(config, inp=None, resume=None):
    events = {"raw": [], "tool_msgs": []}
    if resume is not None:
        iterator = graph.stream(Command(resume=resume), config, stream_mode=STREAM_MODE)
    else:
        iterator = graph.stream({"messages": [("user", inp)]}, config,
                                stream_mode=STREAM_MODE)
    for item in iterator:
        mode, payload = item
        if mode == "messages":
            chunk, meta = payload
            events["raw"].append(("MSG", repr(getattr(chunk, "content", None))[:60]))
            continue
        events["raw"].append(("UPD", type(payload).__name__, list(payload.keys()) if isinstance(payload, dict) else "n/a"))
        if not isinstance(payload, dict):
            events["raw"].append(("UPD-RAW", repr(payload)[:200]))
            continue
        for node, out in payload.items():
            events["raw"].append(("NODE", node, type(out).__name__, repr(out)[:150]))
            if out is None:
                continue
            # out 可能是 dict、list[dict]（同通道多次写入）或 tuple
            if isinstance(out, dict):
                for m in out.get("messages", []) or []:
                    events["tool_msgs"].append(fmt(m))
            elif isinstance(out, list):
                for sub in out:
                    if isinstance(sub, dict):
                        for m in sub.get("messages", []) or []:
                            events["tool_msgs"].append(fmt(m))
            elif isinstance(out, tuple):
                events["tool_msgs"].append(f"TUPLE-OUT: {repr(out)[:200]}")
    return events


def dump_interrupts(config, label):
    state = graph.get_state(config)
    print(f"\n===== [{label}] get_state().interrupts =====")
    intr = state.interrupts if state else None
    print("interrupts 类型:", type(intr).__name__, "长度:", len(intr or []))
    for i, item in enumerate(intr or []):
        print(f"--- interrupt[{i}] 类型: {type(item).__name__} ---")
        try:
            print("attrs:", [a for a in dir(item) if not a.startswith("_")])
        except Exception as e:
            print("attrs err:", e)
        try:
            v = item.value
            print("value 类型:", type(v).__name__)
            if isinstance(v, dict):
                print("value keys:", list(v.keys()))
                print("value JSON:", json.dumps(v, ensure_ascii=False, indent=2, default=str))
            else:
                print("value repr:", repr(v)[:500])
        except Exception as e:
            print("value err:", type(e).__name__, str(e)[:200])
        try:
            print("when:", repr(getattr(item, "when", None))[:100])
        except Exception as e:
            print("when err:", e)
    return intr


# ============ 场景 1：触发中断 → 抄录 payload ============
print("########## 场景 1: write_file 触发中断 ##########")
cfg1 = {"configurable": {"thread_id": "spike:1:t5a"}}
ev = run_stream(cfg1, "请把文件 'report.txt' 的内容写为 'hello hitl approve'，然后确认")
print("首轮流原始事件:")
for r in ev["raw"]:
    print("  ", r)
print("首轮流 tool_msgs:", ev["tool_msgs"])

intr = dump_interrupts(cfg1, "场景1 approve 前")
print("value keys:", list(intr[0].value.keys()) if intr and isinstance(intr[0].value, dict) else "n/a")

# ============ 场景 2：approve 恢复 ============
print("\n########## 场景 2: resume approve ##########")
ev = run_stream(cfg1, resume={"decisions": [{"type": "approve"}]})
print("approve 后事件:")
for r in ev["raw"]:
    print("  ", r)
print("approve 后 tool_msgs:", ev["tool_msgs"])
st = graph.get_state(cfg1)
print("approve 后 interrupts 是否清空:", not (st and st.interrupts))

# ============ 场景 3：reject 恢复（新线程） ============
print("\n########## 场景 3: resume reject ##########")
cfg3 = {"configurable": {"thread_id": "spike:1:t5c"}}
run_stream(cfg3, "请把文件 'secret.txt' 的内容写为 'top secret'，然后确认")
intr3 = dump_interrupts(cfg3, "场景3 reject 前")
ev = run_stream(cfg3, resume={"decisions": [{"type": "reject"}]})
print("reject 后事件:")
for r in ev["raw"]:
    print("  ", r)
print("reject 后 tool_msgs:", ev["tool_msgs"])
st = graph.get_state(cfg3)
msgs = (st.values or {}).get("messages", [])
print("--- reject 后全部消息序列 ---")
for m in msgs:
    print("  ", fmt(m))
ids = [m.tool_call_id for m in msgs if type(m).__name__ == "ToolMessage"]
print("同 id ToolMessage 计数:", {i: ids.count(i) for i in set(ids)})

# ============ 场景 4：edit 恢复（新线程） ============
print("\n########## 场景 4: resume edit（改 args 后执行） ##########")
cfg4 = {"configurable": {"thread_id": "spike:1:t5d"}}
run_stream(cfg4, "请把文件 'draft.txt' 的内容写为 'original'，然后确认")
intr4 = dump_interrupts(cfg4, "场景4 edit 前")
payload = intr4[0].value
act = payload["action_requests"][0]
print("原 action:", act["name"], act["args"])
edited = {"type": "edit",
          "edited_action": {"name": act["name"],
                            "args": {**act["args"], "content": "edited-by-human"}}}
ev = run_stream(cfg4, resume={"decisions": [edited]})
print("edit 后事件:")
for r in ev["raw"]:
    print("  ", r)
print("edit 后 tool_msgs:", ev["tool_msgs"])

# ============ 场景 5: 错误决策形状（对照组） ============
print("\n########## 场景 5: 错误决策形状（对照组，应抛错） ##########")
cfg5 = {"configurable": {"thread_id": "spike:1:t5e"}}
run_stream(cfg5, "请把文件 'x.txt' 写为 'x'")
try:
    run_stream(cfg5, resume={"action": "approve"})  # brief 旧协议形状
    print("旧协议形状未报错（意外）")
except Exception as e:
    print("旧协议形状 {action: approve} 实测结果:", type(e).__name__, str(e)[:200])

print("\nSPIKE DONE")
