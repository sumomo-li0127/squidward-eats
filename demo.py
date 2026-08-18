"""离线自测:不需要任何 API Key / Slack,验证 DB + 推荐逻辑跑通。

    python demo.py
"""

import os
import sys
import tempfile

# Windows 控制台默认 GBK,强制 UTF-8 以正常打印 ¥ / ★ 等字符
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 用临时库,避免污染真实 food.db
os.environ["FOODAGENT_DB"] = os.path.join(tempfile.gettempdir(), "foodagent_demo.db")

from foodagent import db, tools  # noqa: E402


def main():
    # 每次跑重建干净的库
    if os.path.exists(os.environ["FOODAGENT_DB"]):
        os.remove(os.environ["FOODAGENT_DB"])
    db.init_db()

    # 造一些历史订单(item, 店, 价, 评分, 标签, 品类, 自由文本)
    seed = [
        ("喜三鲜饺子", "喜家德", 31.5, 5, "好评", "快餐", "老口味"),
        ("泡菜肉末水晶粉", "兰湘子", 34.1, 5, "常点", "湘菜", None),
        ("大米先生套餐", "大米先生", 34.1, 4, "常点", "快餐", None),
        ("赛百味三明治", "Subway", 33, 3, "一般", "快餐", "常点但也就那样"),
        ("赛百味三明治", "Subway", 35, 3, "一般", "快餐", None),  # 最近又吃,应被降权
        ("迪拜生巧酸奶碗", "酸奶几何", 34, 2, "差评", "轻食", "有点噎人"),
    ]
    for item, rest, price, rating, tag, cat, notes in seed:
        db.add_order(item, rest, price, rating, tag, cat, notes)

    print("== 最近历史 ==")
    for o in db.get_history(limit=5):
        print(f"  {o['ts'][:16]}  {o['item']}  ¥{o['price']}  {o['rating']}★")

    print("\n== 口味画像(按平均分)==")
    for p in tools.db.summarize_prefs():
        print(f"  {p['item']}: 平均 {p['avg_rating']:.1f}★ / {p['times']}次 / 均价¥{p['avg_price']:.0f}")

    print("\n== 推荐(无预算)==")
    print("  ", tools.recommend()["reason"])

    print("\n== 推荐(预算 ¥40)==")
    r = tools.recommend(budget=40)
    print("  ", r["reason"] if r["ok"] else r["reason"])

    print("\n== 账本汇总(最近 7 天)==")
    s = tools.tool_summary(days=7)
    print(f"  {s['count']} 单 / 合计 ¥{s['total']} / 均价 ¥{s['avg']}")
    print(f"  评价分布: {s['by_tag']}")

    print("\nOK: 离线逻辑跑通 ✅")


if __name__ == "__main__":
    main()
