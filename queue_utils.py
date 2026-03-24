import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple

class MessageType(Enum):
    USER_INPUT = "user_input"
    TERMINAL = "terminal"
    COMMAND = "command"
    PRINT = "print"
    USER_INTERRUPT = "user_interrupt"
    TELEGRAM = "telegram"
    TELEGRAM_RESPONSE = "telegram_response"

@dataclass
class Message:
    type: MessageType
    data: Any

def user_input_message(content: str) -> Message:
    return Message(MessageType.USER_INPUT, content)

def terminal_message(content: str) -> Message:
    return Message(MessageType.TERMINAL, content)

def command_message(cmd: str) -> Message:
    return Message(MessageType.COMMAND, cmd)

def print_message(text: str, **kwargs) -> Message:
    return Message(MessageType.PRINT, (text, kwargs))


def telegram_message(content: str) -> Message:
    return Message(MessageType.TELEGRAM, content)


def telegram_response_message(content: str, response_type: str = "text") -> Message:
    """
    response_type: "text", "tool_start", "tool_result", "final"
    """
    return Message(MessageType.TELEGRAM_RESPONSE, {"type": response_type, "content": content})

def clear_queue(queue: asyncio.Queue):
    while True:
        try:
            queue.get_nowait()          # 非阻塞获取元素
        except asyncio.QueueEmpty:
            break                       # 队列已空，退出循环