# 保持原有工具导入不变
from tmux_tools_schema import TMUX_TOOLS_SCHEMA
from tmux_tools import TMUX_TOOLS
from image_tools_schema import IMAGE_TOOLS_SCHEMA
from image_tools import IMAGE_TOOLS

TOOLS = TMUX_TOOLS_SCHEMA + IMAGE_TOOLS_SCHEMA
AVAILABLE_TOOLS = {**TMUX_TOOLS, **IMAGE_TOOLS}