import math
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class CalculatorInput(BaseModel):
    expression: str = Field(
        description="数学表达式，支持 +, -, *, /, ** (幂), sqrt, sin, cos, log 等"
    )


def _calculate(expression: str) -> str:
    """安全计算数学表达式"""
    allowed = {
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log10": math.log10, "log2": math.log2,
        "sqrt": math.sqrt, "abs": abs, "pow": pow,
        "pi": math.pi, "e": math.e,
        "ceil": math.ceil, "floor": math.floor,
    }
    try:
        # 只允许安全的内置函数和数学函数
        result = eval(expression, {"__builtins__": {}}, allowed)
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"


calculator_tool = StructuredTool.from_function(
    name="calculator",
    description="执行数学计算。支持基本运算和常用数学函数。",
    func=_calculate,
    args_schema=CalculatorInput,
)
