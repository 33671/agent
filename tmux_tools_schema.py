"""
Tool schema definitions for tmux tools.
These define the function signatures for the OpenAI/DeepSeek API.
"""

TMUX_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "tmux_new",
            "description": "Create a new tmux window in the agent session with one pane. If agent_session doesn't exist, it will be created automatically. Each window can only have one pane.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_name": {
                        "type": "string",
                        "description": "Name of the window. If omitted, a tmux-generated name is used.",
                    },
                    "start_directory": {
                        "type": "string",
                        "description": "Working directory for the new window. Defaults to current directory.",
                    },
                    "command": {
                        "type": "string",
                        "description": "Initial command to run in the window (e.g., 'bash', 'python'). If omitted, the default shell is started.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_read_last",
            "description": "Read the last N lines from a tmux window. Returns content string with line range header like '[lines X-Y]\\ncontent'. Each window has exactly one pane.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name (e.g., 'worker', 'main', 'backend').",
                    },
                    "n_lines": {
                        "type": "integer",
                        "description": "Number of lines to read from the end.",
                    },
                },
                "required": ["target_window", "n_lines"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_read",
            "description": "Read N lines from a starting line offset in a tmux window. Line numbers are 1-indexed. Returns content string with line range header like '[lines X-Y]\\ncontent'. Each window has exactly one pane.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name (e.g., 'worker', 'main', 'backend').",
                    },
                    "line_offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed).",
                    },
                    "n_lines": {
                        "type": "integer",
                        "description": "Number of lines to read.",
                    },
                },
                "required": ["target_window", "line_offset", "n_lines"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_write",
            "description": "Send input (keys) to a window. Each window has exactly one pane.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name (e.g., 'worker', 'main').",
                    },
                    "input": {
                        "type": "string",
                        "description": "Text to send. Use '\\n' for Enter, and tmux key syntax like 'C-c' for Ctrl+C.",
                    },
                },
                "required": ["target_window", "input"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_del",
            "description": "Kill a window in agent_session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name to kill (e.g., 'worker', 'main').",
                    },
                },
                "required": ["target_window"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_list",
            "description": "List all windows in agent_session. Each window has one pane.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_wait",
            "description": "Wait for a substring to appear in a window's output, with a timeout. Only matches unread content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name (e.g., 'worker', 'main').",
                    },
                    "text": {
                        "type": "string",
                        "description": "Substring to search for in unread output.",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Maximum seconds to wait. If omitted, wait indefinitely.",
                    },
                },
                "required": ["target_window", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_send_signal",
            "description": "Send a signal to the foreground process in a window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name (e.g., 'worker', 'main').",
                    },
                    "signal": {
                        "type": "string",
                        "description": "Signal name (e.g., 'SIGINT', 'SIGTERM') or number.",
                    },
                },
                "required": ["target_window", "signal"],
            },
        },
    },
]
