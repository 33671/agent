from typing import List, Dict

def strip_past_turn_reasoning_context(messages: List[Dict], preserve_thinking: bool = False) -> List[Dict]:
    """保留最后一个 user 消息之后的 reasoning_content（根据配置）"""
    if not messages:
        return []
    if preserve_thinking:
        return [msg.copy() for msg in messages]

    last_user_index = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user_index = i

    filtered = []
    for idx, msg in enumerate(messages):
        msg_copy = msg.copy()
        if idx <= last_user_index:
            msg_copy.pop("reasoning_content", None)
        filtered.append(msg_copy)
    return filtered