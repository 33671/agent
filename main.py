import asyncio
import sys
from pathlib import Path

# 加载系统提示
SYSTEM_PROMPT = open("system_prompt.md", "r", encoding="utf-8").read()

from queue_utils import Message, command_message, telegram_response_message
from producers import user_input_producer, terminal_output_producer
from bot_producer import telegram_bot_producer, get_bot, get_target_chat_id
from bot_consumer import telegram_bot_consumer
from consumer import model_consumer, print_consumer


async def main(is_preserved_thinking=False):
    print("=" * 60)
    print(f"Config: isPreservedthinking={is_preserved_thinking}")
    print("Commands:")
    print("  Ctrl+D/exit    - Exit")
    print("  clear          - Clear history")
    print("=" * 60)

    main_queue = asyncio.Queue()   # 传递用户/终端消息和命令
    print_queue = asyncio.Queue()   # 传递打印任务
    user_interrupt_queue = asyncio.Queue()
    telegram_response_queue = asyncio.Queue()  # 传递需要发送给 Telegram 的响应
    
    producers = [
        asyncio.create_task(user_input_producer(main_queue, print_queue, user_interrupt_queue)),
        asyncio.create_task(terminal_output_producer(main_queue, print_queue)),
        asyncio.create_task(telegram_bot_producer(main_queue, print_queue, user_interrupt_queue)),
    ]

    consumers = [
        asyncio.create_task(model_consumer(main_queue, print_queue, user_interrupt_queue,
                                           telegram_response_queue, is_preserved_thinking, SYSTEM_PROMPT)),
        asyncio.create_task(print_consumer(print_queue)),
        asyncio.create_task(telegram_bot_consumer(telegram_response_queue, print_queue, 
                                                   get_bot, get_target_chat_id)),
    ]

    done, pending = await asyncio.wait(consumers, return_when=asyncio.FIRST_COMPLETED)

    # 通知 telegram_consumer 退出
    await telegram_response_queue.put(command_message("exit"))
    
    for task in pending:
        task.cancel()
    for task in producers:
        task.cancel()
    await asyncio.gather(*pending, *producers, return_exceptions=True)


if __name__ == "__main__":
    preserve_thinking = False
    asyncio.run(main(preserve_thinking))