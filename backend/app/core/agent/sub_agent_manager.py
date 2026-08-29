"""Phase 3: 子 Agent 管理器 + 监督者路由"""
import logging
from app.extensions import db
from app.models.sub_agent import SubAgentDefinition
from app.core.agent.tools import DEFAULT_TOOLS

logger = logging.getLogger(__name__)


class SubAgentManager:
    def __init__(self):
        self._registry: dict[str, dict] = {}

    def register(self, definition: SubAgentDefinition):
        self._registry[definition.name] = {
            "id": definition.id, "name": definition.name,
            "role_prompt": definition.role_prompt, "tools": definition.tools or [],
            "model": definition.model, "mode": definition.mode,
        }

    def load_from_db(self, tenant_id: int, parent_agent_id: int):
        subs = SubAgentDefinition.query.filter_by(
            tenant_id=tenant_id, parent_agent_id=parent_agent_id, is_active=True
        ).all()
        for s in subs:
            self.register(s)
        return list(self._registry.keys())

    def get_all(self) -> list[dict]:
        return list(self._registry.values())

    def get_by_name(self, name: str) -> dict | None:
        return self._registry.get(name)

    def build_supervisor_prompt(self, user_message: str) -> str:
        workers = self.get_all()
        if not workers:
            return ""
        worker_desc = "\n".join(
            f"- **{w['name']}**: {w['role_prompt'][:100]} (tools: {w['tools']})"
            for w in workers
        )
        return f"""你是任务监督者。分析用户请求并分发给合适的 Worker Agent。

可用 Worker:
{worker_desc}

用户消息: {user_message}

请回复 JSON 格式的路由决策:
{{"worker": "<name>", "task": "<subtask description>", "reason": "<why>"}}
如果不需委托，回复: {{"worker": null, "reason": "直接处理"}}"""
