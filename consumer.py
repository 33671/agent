import asyncio
import html
import json
import os
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML

from queue_utils import Message, MessageType, print_message, telegram_message, telegram_response_message
from tools import TOOLS, AVAILABLE_TOOLS
from utils import strip_past_turn_reasoning_context

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量获取配置，允许设置默认值
client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.moonshot.cn/v1"),
    api_key=os.getenv("OPENAI_API_KEY"),          # 必须提供，否则 OpenAI 客户端会报错
)
REASONING_MODEL_NAME = os.getenv("REASONING_MODEL_NAME", "kimi-k2.5")


async def call_model(messages, tools, tool_choice):
    """在线程池中执行同步的模型调用"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model=REASONING_MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            stream=False,
        )
    )


import inspect  # 或 import asyncio，根据实际导入情况选择

async def execute_tool_calls(tool_calls, print_queue, telegram_response_queue=None):
    """执行工具调用"""
    results = []

    for call in tool_calls:
        tool_name = call.function.name
        tool_args = json.loads(call.function.arguments)

        exec_info = f"{tool_name}({json.dumps(tool_args)})"
        await print_queue.put(print_message(
            f"[Executing tool]: {exec_info}"
        ))
        
        # 发送 tool call 开始信息到 telegram
        if telegram_response_queue:
            await telegram_response_queue.put(
                telegram_response_message(exec_info, "tool_start")
            )

        async def _run_tool():
            tool_func = AVAILABLE_TOOLS.get(tool_name)
            if tool_func:
                try:
                    if inspect.iscoroutinefunction(tool_func):
                        return await tool_func(**tool_args)
                    else:
                        return tool_func(**tool_args)
                except Exception as e:
                    return f"Error executing {tool_name}: {str(e)}"
            return f"Error: Unknown tool '{tool_name}'"

        result = await _run_tool()

        result_str = json.dumps(result, indent=2) if isinstance(result, (list, dict)) else str(result)
        if len(result_str) > 16000:
            result_str = result_str[:16000] + f'\n... ({len(result_str) - 16000} more chars)'
        await print_queue.put(print_message(
            f"[Tool call id: {call.id} {tool_name} result]:\n {result_str}"
        ))
        
        # 发送 tool call 结果到 telegram
        if telegram_response_queue:
            await telegram_response_queue.put(
                telegram_response_message(f"{tool_name}:\n{result_str}", "tool_result")
            )

        results.append({
            "role": "tool",
            "content": result_str,
            "tool_call_id": call.id,
            "name": tool_name,
        })
    return results


async def process_user_message(user_content: str, messages: List[Dict],
                               is_preserved_thinking: bool, print_queue, telegram_response_queue=None):
    """处理一条用户消息（用户输入或终端输出）"""
    messages.append({"role": "user", "content": user_content})

    step_count = 0
    while True:
        step_count += 1
        if asyncio.current_task().cancelled():
            break
        await print_queue.put(print_message(f"\n[Step {step_count}] Sending request to model..."))
        current_messages = strip_past_turn_reasoning_context(messages, is_preserved_thinking)
        response = await call_model(current_messages, TOOLS, "auto")

        # 打印模型响应
        msg = response.choices[0].message
        await print_queue.put(print_message(
            f"\n{'=' * 20} Model Response (Step {step_count}) {'=' * 20}"
        ))
        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
            await print_queue.put(print_message(f"\n[REASONING]:\n{msg.reasoning_content}"))
        if hasattr(msg, "content") and msg.content:
            await print_queue.put(print_message(f"\n[CONTENT]:\n{msg.content}"))
            # 发送中间过程的 content 到 telegram（如果有 tool_calls，说明是中间步骤）
            if telegram_response_queue and msg.tool_calls:
                await telegram_response_queue.put(
                    telegram_response_message(msg.content, "content")
                )
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            await print_queue.put(print_message("\n[TOOL CALLS]:"))
            for i, tc in enumerate(msg.tool_calls, 1):
                await print_queue.put(print_message(
                    f"  [{i}] Function: {tc.function.name}\n"
                    f"      Arguments: {tc.function.arguments}"
                ))
        await print_queue.put(print_message('=' * 50 + '\n'))

        # 保存 assistant 消息
        assistant_msg = {
            "role": "assistant",
            "reasoning_content": msg.reasoning_content,
        }
        if not msg.tool_calls:
            assistant_msg["content"] = msg.content
        else:
            assistant_msg["tool_calls"] = msg.tool_calls
        messages.append(assistant_msg)
        if asyncio.current_task().cancelled():
            break
        if msg.tool_calls:
            tool_results = await execute_tool_calls(msg.tool_calls, print_queue, telegram_response_queue)
            messages.extend(tool_results)
        else:
            # 发送最终回复到 telegram
            if telegram_response_queue and msg.content:
                await telegram_response_queue.put(
                    telegram_response_message(msg.content, "final")
                )
            break
    return messages


async def model_consumer(main_queue: asyncio.Queue, print_queue: asyncio.Queue, user_interrupt_queue: asyncio.Queue,
                         telegram_response_queue: asyncio.Queue, is_preserved_thinking: bool, system_prompt: str):
    """从 main_queue 获取消息，调用模型处理"""
    messages: List[Dict] = [{"role": "system", "content": system_prompt}]
    running = True

    while running:
        msg = await main_queue.get()
        process_user_message_task:asyncio.Task= None

        if msg.type == MessageType.COMMAND:
            cmd = msg.data
            if cmd == "exit":
                await print_queue.put(print_message("\nExiting"))
                running = False
            elif cmd == "clear":
                messages.clear()
                messages.append({"role": "system", "content": system_prompt})
                await print_queue.put(print_message("\n对话历史已清空。"))
            elif cmd == "history":
                await print_queue.put(print_message(f"\n历史消息 ({len(messages)} 条):"))
                for i, m in enumerate(messages):
                    role = m.get("role", "unknown")
                    content = m.get("content", "")
                    if len(content) > 100:
                        content = content[:100] + "..."
                    await print_queue.put(print_message(f"  [{i}] {role}: {content}"))
            else:
                await print_queue.put(print_message(f"未知命令: {cmd}"))

        elif msg.type == MessageType.USER_INPUT:
            # await print_queue.put(print_message(f"\n[收到用户输入]: {msg.data}"))
            process_user_message_task = asyncio.create_task(process_user_message(msg.data, messages, is_preserved_thinking, print_queue, telegram_response_queue))

        elif msg.type == MessageType.TERMINAL:
            await print_queue.put(print_message(f"\n[收到终端输出]: {msg.data}"))
            process_user_message_task = asyncio.create_task(process_user_message(msg.data, messages, is_preserved_thinking, print_queue, telegram_response_queue))

        elif msg.type == MessageType.TELEGRAM:
            await print_queue.put(print_message(f"\n[收到 Telegram 消息]: {msg.data}"))
            # 收到 Telegram 消息后，等待 10 秒看是否有后续新消息
            await print_queue.put(print_message("[等待 10 秒收集更多消息...]"))
            await asyncio.sleep(10)
            
            # 收集这 10 秒内收到的所有 Telegram 消息
            telegram_messages = [msg.data]
            while not main_queue.empty():
                try:
                    next_msg = main_queue.get_nowait()
                    if next_msg.type == MessageType.TELEGRAM:
                        telegram_messages.append(next_msg.data)
                        await print_queue.put(print_message(f"[合并 Telegram 消息]: {next_msg.data}"))
                    else:
                        # 如果不是 telegram 消息，放回队列
                        await main_queue.put(next_msg)
                        break
                except asyncio.QueueEmpty:
                    break
            
            # 合并所有消息
            combined_content = "\n".join(telegram_messages)
            await print_queue.put(print_message(f"[合并后的消息]: {combined_content}"))
            process_user_message_task = asyncio.create_task(process_user_message(combined_content, messages, is_preserved_thinking, print_queue, telegram_response_queue))

        else:
            await print_queue.put(print_message(f"未知消息类型: {msg.type}"))
        if process_user_message_task:
            irpt_task = asyncio.create_task(user_interrupt_queue.get())
            done, _ = await asyncio.wait(
                [process_user_message_task, irpt_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            if process_user_message_task not in done:
                process_user_message_task.cancel()
                await print_queue.put(print_message("\n检测到用户打断，任务取消"))
            else:
                messages = await process_user_message_task
                # await print_queue.put(print_message(f"正常执行:{messages[len(messages) - 1]}"))
            
        await asyncio.sleep(0)  # 让出控制权，帮助 prompt_toolkit 刷新

    await print_queue.put(print_message("Loop stopped"))


async def print_consumer(print_queue: asyncio.Queue):
    """专门处理打印任务，避免多协程同时输出干扰"""
    while True:
        msg = await print_queue.get()
        if msg.type == MessageType.PRINT:
            text, kwargs = msg.data
            safe_text = html.escape(text)
            print_formatted_text(HTML(safe_text), **kwargs)
        else:
            print_formatted_text(f"未知打印消息: {msg}")