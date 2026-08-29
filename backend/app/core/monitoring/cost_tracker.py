"""Phase 5: Token 成本追踪"""
from datetime import datetime
from flask import current_app


class CostTracker:
    PRICING = {
        "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "deepseek-v4-pro": {"input": 0.27, "output": 1.10},
        "deepseek-chat": {"input": 0.27, "output": 1.10},
    }

    def __init__(self):
        self.redis = current_app.extensions.get("redis_client")

    def record(self, tenant_id: str, user_id: str, model: str,
               input_tokens: int, output_tokens: int):
        if not self.redis:
            return
        pricing = self.PRICING.get(model, {"input": 0, "output": 0})
        cost = input_tokens / 1_000_000 * pricing["input"] + output_tokens / 1_000_000 * pricing["output"]
        today = datetime.utcnow().strftime("%Y-%m-%d")
        self.redis.client.hincrby(f"cost:{tenant_id}:{today}", "input_tokens", input_tokens)
        self.redis.client.hincrby(f"cost:{tenant_id}:{today}", "output_tokens", output_tokens)
        self.redis.client.hincrbyfloat(f"cost:{tenant_id}:{today}", "cost_usd", cost)

    def get_tenant_daily(self, tenant_id: str, date: str = None) -> dict:
        if not self.redis:
            return {}
        date = date or datetime.utcnow().strftime("%Y-%m-%d")
        data = self.redis.client.hgetall(f"cost:{tenant_id}:{date}")
        return {
            "input_tokens": int(data.get("input_tokens", 0)),
            "output_tokens": int(data.get("output_tokens", 0)),
            "cost_usd": round(float(data.get("cost_usd", 0)), 6),
            "date": date,
        }
