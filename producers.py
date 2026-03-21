import asyncio
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from queue_utils import user_input_message, command_message, print_message

async def user_input_producer(main_queue: asyncio.Queue, print_queue: asyncio.Queue,user_interrupt_queue:asyncio.Queue):
    """异步读取用户输入，发送到 main_queue"""
    session = PromptSession(history=InMemoryHistory())
    completer = WordCompleter(["exit", "quit", "clear", "history"], ignore_case=True)
    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    turn_count = 1
    while True:
        try:
            sys.stdout.flush()  # 确保提示符立即显示
            user_input = await session.prompt_async(
                f"\nUser [Turn {turn_count}]: ",
                completer=completer,
                key_bindings=bindings,
                multiline=False,
                enable_history_search=True,
            )
        except KeyboardInterrupt:  # ctrl c interrupt
            if user_interrupt_queue.empty():
                await user_interrupt_queue.put("1")
            continue
        except EOFError:
            await main_queue.put(command_message("exit"))
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        lower_input = user_input.lower()
        if lower_input in ("exit", "quit"):
            await main_queue.put(command_message("exit"))
            break
        elif lower_input == "clear":
            await main_queue.put(command_message("clear"))
        elif lower_input == "history":
            await main_queue.put(command_message("history"))
        else:
            await main_queue.put(user_input_message(user_input))
            turn_count += 1


async def terminal_output_producer(main_queue: asyncio.Queue, print_queue: asyncio.Queue):
    """。
    每读取一行，向 main_queue 发送 terminal_message(line)
    """
    # 示例：模拟输出（实际使用时删除）
    await print_queue.put(print_message("terminal source listening"))
    try:
        while True:
            await asyncio.sleep(1)  # TODO
    except asyncio.CancelledError:
        await print_queue.put(print_message("[终端生产者] 已取消"))
        raise