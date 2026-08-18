"""LLM Agent 循环:接收用户消息 → LLM 决定调哪个工具 → 执行 → 再让 LLM 总结回复。

支持 OpenAI 与 Anthropic(Claude),通过 PROVIDER 环境变量切换。
工具 schema 用中立格式(tools.TOOLS),此处转换成各家 API 需要的格式。
"""

import json
import os

from .tools import DISPATCH, TOOLS

PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()  # "openai" | "anthropic"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

SYSTEM_PROMPT = (
    "你是「章鱼哥」(Squidward),一个被迫兼职外卖助手的、毒舌又厌世的 AI。\n"
    "【人设 · 语言风格】\n"
    "- 语气冷淡、毒舌、爱吐槽,像被生活折磨、只想吹单簧管的中年上班族。\n"
    "- 嫌麻烦、瞧不上一切,催人点外卖时不耐烦(如'别等我催第二遍''现在说,我不想一个个去问')。\n"
    "- 但毒舌只是表面:该办的事一定办好,绝不真坑用户。\n"
    "- 回复简短,一两句到位,别啰嗦。用中文。\n"
    "【职责 · 不受人设影响,必须做对】\n"
    "- 用户描述吃了什么 → 调 log_order 准确记录(店名、金额、评价都要抓对)。\n"
    "- 用户问吃什么/要推荐 → 调 recommend,再用毒舌口吻把推荐和理由说出来。\n"
    "- 用户要账本/问花了多少 → 调 summary(需要逐单明细才用 get_history)。\n"
    "- 数据必须真实准确,绝不能为了搞笑编造金额或推荐。毒舌归毒舌,靠谱是底线。"
)


def _dispatch(name, args):
    fn = DISPATCH.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**(args or {}))
    except Exception as e:  # noqa: BLE001 - 工具错误回传给模型即可
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# OpenAI 路径
# ---------------------------------------------------------------------------
def _run_openai(user_text):
    from openai import OpenAI

    client = OpenAI()
    tools = [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
        for t in TOOLS
    ]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    for _ in range(6):  # 最多 6 轮工具调用,防死循环
        resp = client.chat.completions.create(model=OPENAI_MODEL, messages=messages, tools=tools)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content
        messages.append(msg)
        for tc in msg.tool_calls:
            result = _dispatch(tc.function.name, json.loads(tc.function.arguments or "{}"))
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, ensure_ascii=False)}
            )
    return "(达到最大工具调用轮数,请重试)"


# ---------------------------------------------------------------------------
# Anthropic 路径
# ---------------------------------------------------------------------------
def _run_anthropic(user_text):
    import anthropic

    client = anthropic.Anthropic()
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
        for t in TOOLS
    ]
    messages = [{"role": "user", "content": user_text}]

    for _ in range(6):
        resp = client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=1024, system=SYSTEM_PROMPT, tools=tools, messages=messages
        )
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                result = _dispatch(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, ensure_ascii=False)}
                )
        messages.append({"role": "user", "content": tool_results})
    return "(达到最大工具调用轮数,请重试)"


def run_agent(user_text):
    """对外统一入口:输入用户文本,返回助手回复文本。"""
    if PROVIDER == "anthropic":
        return _run_anthropic(user_text)
    return _run_openai(user_text)
