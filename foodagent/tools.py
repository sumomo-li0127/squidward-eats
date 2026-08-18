"""工具层:Agent 可调用的函数 + 推荐逻辑(LLM 语义 + 硬规则混合)。

推荐核心是规则打分(可离线运行、可解释),LLM 只负责把结果说得自然。
"""

from datetime import datetime

from . import db


# ---------------------------------------------------------------------------
# 推荐:规则打分
# ---------------------------------------------------------------------------
def recommend(budget=None):
    """基于历史给出一个推荐,返回结构化结果(含理由)。

    评分 = 平均评分 - 最近吃过的惩罚;可选按预算过滤。
    """
    prefs = db.summarize_prefs()
    if not prefs:
        return {
            "ok": False,
            "reason": "还没有历史订单,先记录几单我才能推荐~",
            "candidate": None,
        }

    recent = {r["item"] for r in db.get_recent_items(days=3)}

    scored = []
    for p in prefs:
        avg_rating = p["avg_rating"] or 3.0
        score = avg_rating
        score += 0.5 * (p.get("good_count") or 0)  # 好评/常点 加权
        penalty = 2.0 if p["item"] in recent else 0.0  # 最近 3 天吃过 → 降权
        score -= penalty
        if budget is not None and p["avg_price"] and p["avg_price"] > budget:
            continue  # 超预算跳过
        scored.append((score, penalty, p))

    if not scored:
        return {"ok": False, "reason": "符合预算的历史项太少,放宽预算试试?", "candidate": None}

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, penalty, best = scored[0]

    # 组织可解释理由
    bits = []
    if best["avg_rating"]:
        bits.append(f"你给它平均 {best['avg_rating']:.1f} 分")
    if best["times"]:
        bits.append(f"点过 {best['times']} 次")
    if best["item"] not in recent:
        bits.append("最近没吃、换换口味")
    reason = "推荐「{}」{}——{}。".format(
        best["item"],
        f"({best['category']})" if best["category"] else "",
        "、".join(bits) if bits else "综合评分最高",
    )

    return {
        "ok": True,
        "candidate": best["item"],
        "category": best["category"],
        "avg_price": best["avg_price"],
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Agent 可调用的工具实现(名字 -> 函数)
# ---------------------------------------------------------------------------
def tool_log_order(item, restaurant=None, price=None, rating=None, review_tag=None,
                   category=None, notes=None):
    oid = db.add_order(item, restaurant, price, rating, review_tag, category, notes)
    return {"ok": True, "order_id": oid, "message": f"已记录:{item}"}


def tool_get_history(limit=10):
    return {"orders": db.get_history(limit=limit)}


def tool_recommend(budget=None):
    return recommend(budget=budget)


def tool_summary(days=7):
    return db.summarize_spend(days=days)


DISPATCH = {
    "log_order": tool_log_order,
    "get_history": tool_get_history,
    "recommend": tool_recommend,
    "summary": tool_summary,
}


# ---------------------------------------------------------------------------
# 工具 schema(中立格式,llm.py 会转成各家 API 需要的格式)
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "log_order",
        "description": "记录一次外卖订单。当用户说'今天吃了X''点了X花了Y'等时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "吃了什么菜/套餐"},
                "restaurant": {"type": "string", "description": "店铺名(可选)"},
                "price": {"type": "number", "description": "花费金额(可选)"},
                "rating": {"type": "integer", "description": "1-5 评分(可选)"},
                "review_tag": {
                    "type": "string",
                    "description": "评价标签,从用户口吻归纳:好评/常点/一般/差评(可选)",
                    "enum": ["好评", "常点", "一般", "差评"],
                },
                "category": {"type": "string", "description": "品类,如 川菜/日料/快餐(可选)"},
                "notes": {"type": "string", "description": "原话评价/备注,如'有点噎人'(可选)"},
            },
            "required": ["item"],
        },
    },
    {
        "name": "get_history",
        "description": "查询最近的外卖历史订单。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "返回条数,默认 10"},
            },
        },
    },
    {
        "name": "recommend",
        "description": "基于历史给用户推荐今天点什么外卖。用户问'吃什么''推荐一个'时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "budget": {"type": "number", "description": "预算上限(可选)"},
            },
        },
    },
    {
        "name": "summary",
        "description": "汇总最近一段时间的外卖账本:餐次数、合计花费、均价、评价分布。用户问'这周花了多少''账本'时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "统计最近多少天,默认 7"},
            },
        },
    },
]
