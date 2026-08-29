from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool

# 服务器/用户均为中国时区
CHINA_TZ = timezone(timedelta(hours=8))
_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@tool
def datetime_tool() -> str:
    """获取当前日期、星期和时间（中国时区 UTC+8）。当用户询问今天的日期、星期几、现在几点时，必须使用本工具而不是代码执行。"""
    now = datetime.now(CHINA_TZ)
    return (
        f"{now.strftime('%Y-%m-%d')} {_WEEKDAYS[now.weekday()]} "
        f"{now.strftime('%H:%M:%S')} (UTC+8)"
    )
