"""
Tool schema definitions for image tools.
"""

IMAGE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_image",
            "description": "Read an image from the file system or a URL and return it as base64 encoded data URL suitable for display or analysis",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the image file (e.g., './image.png' or 'C:/Users/user/image.jpg') or a URL to the image (e.g., 'https://example.com/image.png')",
                    },
                },
                "required": ["path"],
            },
        },
    },
]
