"""数据层:用 SQLite 持久化外卖订单历史。"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.getenv("FOODAGENT_DB", os.path.join(os.path.dirname(__file__), "..", "food.db"))


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT NOT NULL,      -- ISO 时间
                item       TEXT NOT NULL,      -- 吃了什么
                restaurant TEXT,               -- 店铺
                price      REAL,               -- 花费
                rating     INTEGER,            -- 1-5 评分(可空)
                review_tag TEXT,               -- 评价标签:好评/常点/一般/差评
                category   TEXT,               -- 品类(如 川菜/日料)
                notes      TEXT                -- 自由文本评价/备注
            )
            """
        )
        # 平滑迁移:老库若缺 review_tag 列则补上
        cols = {r["name"] for r in c.execute("PRAGMA table_info(orders)").fetchall()}
        if "review_tag" not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN review_tag TEXT")


def add_order(item, restaurant=None, price=None, rating=None, review_tag=None,
              category=None, notes=None, ts=None):
    """记录一单。返回新订单 id。"""
    ts = ts or datetime.now().isoformat(timespec="seconds")
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO orders (ts, item, restaurant, price, rating, review_tag, category, notes) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ts, item, restaurant, price, rating, review_tag, category, notes),
        )
        return cur.lastrowid


def get_history(limit=20):
    """按时间倒序取最近 N 单。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM orders ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_items(days=3):
    """取最近 N 天吃过的品类/菜品(用于推荐时降权、避重复)。"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT item, category FROM orders WHERE ts >= ?", (since,)
        ).fetchall()
        return [dict(r) for r in rows]


def summarize_spend(days=7):
    """账本聚合:最近 N 天的餐次数、合计花费、均价,以及按评价标签的分布。"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with _conn() as c:
        agg = c.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(price),0) AS total, AVG(price) AS avg "
            "FROM orders WHERE ts >= ?",
            (since,),
        ).fetchone()
        tags = c.execute(
            "SELECT COALESCE(review_tag,'未评') AS tag, COUNT(*) AS cnt "
            "FROM orders WHERE ts >= ? GROUP BY tag ORDER BY cnt DESC",
            (since,),
        ).fetchall()
        return {
            "days": days,
            "count": agg["cnt"],
            "total": round(agg["total"], 2),
            "avg": round(agg["avg"], 2) if agg["avg"] else 0,
            "by_tag": {r["tag"]: r["cnt"] for r in tags},
        }


def summarize_prefs():
    """聚合口味画像:各菜品的平均评分与次数,供推荐参考。"""
    with _conn() as c:
        rows = c.execute(
            """
            SELECT item, category,
                   COUNT(*)      AS times,
                   AVG(rating)   AS avg_rating,
                   MAX(ts)       AS last_ts,
                   AVG(price)    AS avg_price,
                   SUM(CASE WHEN review_tag IN ('好评','常点') THEN 1 ELSE 0 END) AS good_count
            FROM orders
            GROUP BY item
            ORDER BY avg_rating DESC, times DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
