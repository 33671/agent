"""
Tool schema definitions for tmux tools.
These define the function signatures for the OpenAI/DeepSeek API.
"""

TMUX_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "tmux_new",
            "description": "Create a new tmux window in the agent_session with one pane. If the session doesn't exist, it is created automatically. The window's output is automatically captured to a log file for reading. Each window has exactly one pane.",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_name": {
                        "type": "string",
                        "description": "Name for the window (e.g., 'worker', 'backend'). If omitted, tmux assigns a numeric name.",
                    },
                    "start_directory": {
                        "type": "string",
                        "description": "Working directory for the new window. Defaults to current directory.",
                    },
                    "longrunning_command": {
                        "type": "string",
                        "description": "Initial command to run in the window (e.g., 'python server.py'). If omitted, a bash shell is started.",
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
            "description": "Read the last N lines from a window's output. ANSI escape codes are stripped, and lines are right-trimmed. Returns the content as a plain string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name (e.g., 'worker', 'main', 'backend').",
                    },
                    "n_lines": {
                        "type": "integer",
                        "description": "Number of lines to read from the end. Use 0 to read the entire screen.",
                    },
                },
                "required": ["target_window", "n_lines"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tmux_write",
            "description": "Send input (keys) to a window and return the new output generated after waiting. The output is cleaned of ANSI codes. Each window has exactly one pane.",
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
                    "wait_secs": {
                        "type": "number",
                        "description": "Seconds to wait before reading output. Defaults to 1.0. Increase for slower commands.",
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
                        "description": "Window name to kill.",
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
            "description": "Wait for a substring to appear in a window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Substring to search for in the comming content.",
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
            "description": "Send a signal to the foreground process in a window. Common signals (SIGINT, SIGTERM, SIGQUIT, SIGSTOP, SIGTSTP) are mapped to tmux key sequences; others are sent via kill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_window": {
                        "type": "string",
                        "description": "Window name.",
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