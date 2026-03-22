#!/usr/bin/env python3
"""
Telegram Bot Producer - 接收 Telegram 消息并发送到 main queue。

Behavior:
- 通过环境变量 TELEGRAM_BOT_TOKEN 配置 bot token
- 通过环境变量 TARGET_USERNAME 配置目标用户（可选）
- 收到消息后先发送中断信号打断当前 model step
- 然后将消息放入 main_queue 作为 role:user
- 如果配置了 TARGET_USERNAME，只处理该用户的消息
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from queue_utils import telegram_message, print_message

load_dotenv()

# Environment variables
ENV_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ENV_TARGET_USERNAME = os.getenv("TARGET_USERNAME")

# Where to persist username->chat_id mappings
DEFAULT_STORE_PATH = Path.home() / ".tgpipe_targets.json"

# Globals
app: Optional[Application] = None
_resolved_chat_id: Optional[int] = None


def get_bot():
    """Get the current bot instance."""
    global app
    return app.bot if app else None


def get_target_chat_id():
    """Get the resolved target chat_id."""
    global _resolved_chat_id
    return _resolved_chat_id


def _norm_username(u: Optional[str]) -> Optional[str]:
    """Normalize a username to lowercase without leading @; return None if empty."""
    if not u:
        return None
    u = u.lstrip("@").strip()
    return u.lower() or None


def load_saved_targets(path: Path = DEFAULT_STORE_PATH) -> dict:
    """Load saved username->chat_id mapping from JSON file."""
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    _norm_username(k): int(v)
                    for k, v in (data or {}).items()
                    if _norm_username(k) and v is not None
                }
    except Exception:
        pass
    return {}


def save_target(username: str, chat_id: int, path: Path = DEFAULT_STORE_PATH) -> None:
    """Save or update the mapping username->chat_id atomically."""
    username_norm = _norm_username(username)
    if not username_norm:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = load_saved_targets(path)
        data[username_norm] = int(chat_id)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except Exception as e:
        print(f"[WARN] failed to save target: {e}")


async def handle_incoming(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    main_queue: asyncio.Queue,
    user_interrupt_queue: asyncio.Queue,
    print_queue: asyncio.Queue,
    target_username: Optional[str],
    set_chat_id_func,
):
    """
    Handler for incoming messages.
    If message matches target (if configured), interrupt current model step
    and send message to main_queue.
    """
    if not update.message:
        return

    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return

    username_raw = user.username or user.first_name or ""
    username_norm = _norm_username(user.username) or _norm_username(username_raw)
    chat_id = chat.id

    # Get text content
    text = update.message.text or update.message.caption or ""
    if not text:
        return

    # Check if target username is configured and matches
    if target_username:
        if username_norm != target_username:
            # Ignore messages from other users
            return

    # Save target if new
    if username_norm:
        saved = load_saved_targets()
        if username_norm not in saved:
            save_target(username_norm, chat_id)
            await print_queue.put(
                print_message(f"[Telegram] Saved new target: @{username_raw} (chat_id={chat_id})")
            )
        # 更新全局 chat_id
        set_chat_id_func(chat_id)

    ts = datetime.now().strftime("%H:%M:%S")
    await print_queue.put(
        print_message(f"[Telegram {ts}] Received from @{username_raw}: {text}")
    )

    # 1. 首先发送中断信号，打断当前的 model step
    if user_interrupt_queue.empty():
        await user_interrupt_queue.put("telegram_interrupt")
        await print_queue.put(
            print_message(f"[Telegram] Sent interrupt signal to stop current model step")
        )

    # 2. 将消息放入 main_queue
    await main_queue.put(telegram_message(text))


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply to /start to confirm bot reachability."""
    chat = update.effective_chat
    user = update.effective_user
    if chat and update.message:
        uname = user.username if user else "unknown"
        await update.message.reply_text(
            f"Bot connected. Your username: @{uname}, chat_id: {chat.id}"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log handler errors."""
    print(f"[Telegram ERROR] {context.error}")


async def telegram_bot_producer(
    main_queue: asyncio.Queue,
    print_queue: asyncio.Queue,
    user_interrupt_queue: asyncio.Queue,
):
    """
    Telegram Bot Producer - 监听 Telegram 消息，收到后打断当前 model step
    并将消息发送到 main_queue。
    """
    token = ENV_TOKEN
    if not token:
        await print_queue.put(
            print_message("[Telegram] TELEGRAM_BOT_TOKEN not set, bot producer will not start")
        )
        return

    target_username = _norm_username(ENV_TARGET_USERNAME)

    if target_username:
        await print_queue.put(
            print_message(f"[Telegram] Target username configured: @{target_username}")
        )
        saved = load_saved_targets()
        if target_username in saved:
            await print_queue.put(
                print_message(f"[Telegram] Using saved chat_id for @{target_username}: {saved[target_username]}")
            )
    else:
        await print_queue.put(
            print_message("[Telegram] No TARGET_USERNAME configured, will accept messages from any user")
        )

    global app
    app = Application.builder().token(token).build()

    def set_chat_id(chat_id: int):
        global _resolved_chat_id
        _resolved_chat_id = chat_id
    
    # Create handler with access to queues
    async def handle_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await handle_incoming(
            update, context, main_queue, user_interrupt_queue, print_queue, target_username, set_chat_id
        )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wrapper))
    app.add_error_handler(error_handler)

    await print_queue.put(print_message("[Telegram] Bot starting..."))

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        # Keep running until cancelled
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        await print_queue.put(print_message("[Telegram] Bot producer cancelled"))
        raise
    finally:
        if app:
            try:
                await app.updater.stop()
            except Exception:
                pass
            try:
                await app.stop()
            except Exception:
                pass
            try:
                await app.shutdown()
            except Exception:
                pass
        await print_queue.put(print_message("[Telegram] Bot stopped"))
