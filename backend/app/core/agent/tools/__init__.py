from app.core.agent.tools.calculator import calculator_tool
from app.core.agent.tools.datetime_tool import datetime_tool
from app.core.agent.tools.web_search import web_search_tool
# code_execution 退役：deepagents 内置 execute 接管（沙箱协议），
# tools_config 中 "code_execution" 名字保留为 execute 启用开关
from app.core.agent.tools.knowledge_search import knowledge_search_tool
from app.core.agent.tools.memory_tools import memory_save_tool, memory_search_tool
from app.core.agent.tools.skill_file_tool import read_skill_file_tool

DEFAULT_TOOLS = [
    calculator_tool,
    datetime_tool,
    web_search_tool,
    knowledge_search_tool,
    memory_save_tool,
    memory_search_tool,
    read_skill_file_tool,
]

__all__ = [
    "DEFAULT_TOOLS",
    "calculator_tool",
    "datetime_tool",
    "web_search_tool",
    "knowledge_search_tool",
    "memory_save_tool",
    "memory_search_tool",
    "read_skill_file_tool",
]
