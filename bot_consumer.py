#!/usr/bin/env python3
"""
Telegram Bot Consumer - 将模型响应发送回 Telegram 用户。

Behavior:
- 监听 telegram_response_queue
- 将 tool call 执行信息和最终回复发送给 Telegram 用户
- 使用 bot_producer 中初始化的 bot 实例发送消息
"""

import asyncio
from typing import Optional

from queue_utils import MessageType, print_message


async def send_telegram_message(bot, chat_id: int, text: str) -> bool:
    """Send a text message to Telegram chat, splitting if too long."""
    if not bot or not chat_id:
        return False
    
    # Telegram 消息长度限制为 4096 字符
    MAX_LENGTH = 4000
    
    try:
        # 如果消息太长，分段发送
        if len(text) > MAX_LENGTH:
            chunks = []
            for i in range(0, len(text), MAX_LENGTH):
                chunk = text[i:i + MAX_LENGTH]
                chunks.append(chunk)
            
            for i, chunk in enumerate(chunks):
                prefix = f"[Part {i+1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
                await bot.send_message(
                    chat_id=chat_id,
                    text=prefix + chunk,
                    parse_mode=None  # 不使用 markdown 避免格式问题
                )
                await asyncio.sleep(0.1)  # 避免发送太快
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=None
            )
        return True
    except Exception as e:
        print(f"[Telegram Consumer ERROR] Failed to send message: {e}")
        return False


async def telegram_bot_consumer(
    telegram_response_queue: asyncio.Queue,
    print_queue: asyncio.Queue,
    get_bot_func,  # 函数，返回 bot 实例
    get_chat_id_func,  # 函数，返回当前目标 chat_id
):
    """
    Telegram Bot Consumer - 监听 telegram_response_queue，
    将模型响应发送给 Telegram 用户。
    """
    await print_queue.put(print_message("[Telegram Consumer] Started"))
    
    running = True
    while running:
        try:
            msg = await telegram_response_queue.get()
            
            if msg.type == MessageType.TELEGRAM_RESPONSE:
                data = msg.data
                response_type = data.get("type", "text")
                content = data.get("content", "")
                
                if not content:
                    continue
                
                # 获取 bot 和 chat_id
                bot = get_bot_func()
                chat_id = get_chat_id_func()
                
                if not bot or not chat_id:
                    await print_queue.put(
                        print_message(f"[Telegram Consumer] Skip sending: bot={bool(bot)}, chat_id={chat_id}")
                    )
                    continue
                
                # 根据类型格式化消息
                if response_type == "tool_start":
                    formatted = f"🛠️ <b>Executing Tool</b>\n<pre>{content}</pre>"
                    await send_telegram_message(bot, chat_id, formatted)
                    
                elif response_type == "tool_result":
                    formatted = f"📊 <b>Tool Result</b>\n<pre>{content[:3000]}{'...' if len(content) > 3000 else ''}</pre>"
                    await send_telegram_message(bot, chat_id, formatted)
                    
                elif response_type == "content":
                    # 中间过程的 content（模型在调用工具前的思考/说明）
                    formatted = f"💭 <b>Thinking</b>\n{content}"
                    await send_telegram_message(bot, chat_id, formatted)
                    
                elif response_type == "final":
                    formatted = f"🤖 <b>Assistant</b>\n{content}"
                    await send_telegram_message(bot, chat_id, formatted)
                    
                else:
                    # 普通文本
                    await send_telegram_message(bot, chat_id, content)
                    
            elif msg.type == MessageType.COMMAND and msg.data == "exit":
                running = False
                
        except asyncio.CancelledError:
            await print_queue.put(print_message("[Telegram Consumer] Cancelled"))
            raise
        except Exception as e:
            await print_queue.put(
                print_message(f"[Telegram Consumer ERROR] {e}")
            )
    
    await print_queue.put(print_message("[Telegram Consumer] Stopped"))
