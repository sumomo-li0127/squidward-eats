"""Slack 外卖助手 Agent · 入口。

用 Slack Bolt(Socket Mode)接收消息,交给 LLM Agent 处理;
后台线程做饭点定时提醒。

运行前需在 .env 设置:
  SLACK_BOT_TOKEN   (xoxb-...)
  SLACK_APP_TOKEN   (xapp-...,Socket Mode)
  OPENAI_API_KEY 或 ANTHROPIC_API_KEY
  SLACK_REMINDER_CHANNEL  (提醒发到哪个频道/用户,如 C0123 或 U0123)
"""

import os
import threading
import time
from datetime import datetime

import schedule
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from foodagent import db
from foodagent.llm import run_agent

load_dotenv()
db.init_db()

app = App(token=os.environ["SLACK_BOT_TOKEN"])


# ---------------------------------------------------------------------------
# 消息处理:DM 或 @机器人 都走 Agent
# ---------------------------------------------------------------------------
@app.event("message")
def handle_message(event, say):
    # 忽略机器人自己的消息 / 无文本消息
    if event.get("bot_id") or not event.get("text"):
        return
    reply = run_agent(event["text"])
    say(reply)


@app.event("app_mention")
def handle_mention(event, say):
    text = event.get("text", "")
    reply = run_agent(text)
    say(reply)


# ---------------------------------------------------------------------------
# 定时提醒:饭点主动推送
# ---------------------------------------------------------------------------
def send_reminder():
    channel = os.getenv("SLACK_REMINDER_CHANNEL")
    if not channel:
        return
    if datetime.now().weekday() >= 5:  # 5=周六, 6=周日 → 周末不推
        return
    reply = run_agent("现在是饭点,用你毒舌的口吻提醒我点外卖,并基于我的历史给一个推荐。")
    app.client.chat_postMessage(channel=channel, text=f"🍱 {reply}")


def run_scheduler():
    # 仅工作日午餐 11:00、晚餐 18:00 提醒(周末在 send_reminder 内跳过)
    schedule.every().day.at("11:00").do(send_reminder)
    schedule.every().day.at("18:00").do(send_reminder)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=run_scheduler, daemon=True).start()
    print("⚡️ 外卖助手 Agent 已启动(Socket Mode)…")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
