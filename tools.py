# 保持原有工具导入不变
from tmux_tools_schema import TMUX_TOOLS_SCHEMA
from tmux_tools import TMUX_TOOLS
from image_tools_schema import IMAGE_TOOLS_SCHEMA
from image_tools import IMAGE_TOOLS
from sleep_tool import SLEEP_TOOLS
from sleep_tool_schema import SLEEP_TOOLS_SCHEMA
TOOLS = TMUX_TOOLS_SCHEMA + IMAGE_TOOLS_SCHEMA + SLEEP_TOOLS_SCHEMA
AVAILABLE_TOOLS = {**TMUX_TOOLS, **IMAGE_TOOLS,**SLEEP_TOOLS}