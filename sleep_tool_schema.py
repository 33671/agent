SLEEP_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "sleep",
            "description": "sleep for secends",
            "parameters": {
                "type": "object",
                "properties": {
                    "secs": {
                        "type": "integer",
                        "description": "seconds to sleep",
                    },
                },
                "required": ["path"],
            },
        },
    }
]
