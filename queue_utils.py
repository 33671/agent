from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple

class MessageType(Enum):
    USER_INPUT = "user_input"
    TERMINAL = "terminal"
    COMMAND = "command"
    PRINT = "print"
    USER_INTERRUPT = "user_interrupt"

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