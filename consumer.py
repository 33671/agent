import asyncio
import html
import json
import os
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML

from queue_utils import Message, MessageType, clear_queue, print_message, telegram_message, telegram_response_message
from bot_producer import set_telegram_batch_active
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

        # 检查结果是否是内容部件格式（如图片），如果是则直接使用数组格式
        def _is_content_parts(obj):
            """检查对象是否是内容部件列表（用于图片等多媒体内容）"""
            if not isinstance(obj, list):
                return False
            if len(obj) == 0:
                return False
            # 检查列表元素是否都有 'type' 字段
            return all(isinstance(item, dict) and "type" in item for item in obj)

        # 用于日志和 telegram 的字符串表示
        if _is_content_parts(result):
            # 对于内容部件，截断 base64 数据以便显示
            display_result = []
            for item in result:
                if item.get("type") == "image_url" and "image_url" in item:
                    url = item["image_url"].get("url", "")
                    if url.startswith("data:"):
                        display_result.append({
                            "type": "image_url",
                            "image_url": {"url": url[:100] + "... (base64 data truncated)"}
                        })
                    else:
                        display_result.append(item)
                else:
                    display_result.append(item)
            result_str = json.dumps(display_result, indent=2)
        else:
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

        # 构建 tool 结果消息
        tool_result_msg = {
            "role": "tool",
            "tool_call_id": call.id,
            "name": tool_name,
        }
        
        # 如果结果是内容部件格式（如图片），直接使用数组作为 content
        if _is_content_parts(result):
            tool_result_msg["content"] = result
        else:
            tool_result_msg["content"] = result_str if isinstance(result_str, str) else json.dumps(result, indent=2)
        
        results.append(tool_result_msg)
    return results


async def _process_telegram_messages(user_content: str, messages: List[Dict],
                                      is_preserved_thinking: bool, print_queue, telegram_response_queue):
    """处理 Telegram 消息的包装函数，确保 batch 标志被重置"""
    try:
        return await process_user_message(user_content, messages, is_preserved_thinking, print_queue, telegram_response_queue)
    finally:
        # 无论成功还是失败，都重置 batch 标志
        set_telegram_batch_active(False)
        await print_queue.put(print_message("[Telegram Batch] 处理完成，重置 batch 标志"))


async def process_user_message(user_content: str, messages: List[Dict],
                               is_preserved_thinking: bool, print_queue, telegram_response_queue=None):
    """处理一条用户消息（用户输入或终端输出）"""
    messages.append({"role": "user", "content": user_content})

    step_count = 0
    while True:
        if asyncio.current_task().cancelled():
            break
        step_count += 1
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
        # msg_task = asyncio.create_task(main_queue.get())
        # user_interrupt_get = asyncio.create_task(user_interrupt_queue.get())
        # await asyncio.wait([msg_task, user_interrupt_get], return_when=asyncio.FIRST_COMPLETED)
        # process_user_message_task:asyncio.Task= None
        msg = await main_queue.get()
        clear_queue(user_interrupt_queue)
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
            # 清空残留的中断信号（避免打断本次消息处理）
            while not user_interrupt_queue.empty():
                try:
                    user_interrupt_queue.get_nowait()
                    await print_queue.put(print_message("[清理残留中断信号]"))
                except asyncio.QueueEmpty:
                    break
            
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
            
            # 创建处理任务，并确保 batch 标志被重置
            process_user_message_task = asyncio.create_task(
                _process_telegram_messages(combined_content, messages, is_preserved_thinking, print_queue, telegram_response_queue)
            )

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