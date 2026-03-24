"""
Tool schema definitions for file tools.
"""

FILE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write string content to a file. Creates parent directories if needed. Mode determines write behavior: if not specified,  write uses 'overwrite'. Explicit mode can be set to 'overwrite' or 'append'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to write to the file",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Write mode.",
                        "enum": ["overwrite", "append"],
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_replace",
            "description": "Replace occurrences of a substring in a file. Optionally replace all occurrences or only the first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "old": {
                        "type": "string",
                        "description": "The substring to be replaced",
                    },
                    "new": {
                        "type": "string",
                        "description": "The replacement substring",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If True, replace all occurrences; otherwise replace only the first occurrence",
                        "default": False,
                    },
                },
                "required": ["path", "old", "new"],
            },
        },
    },
]