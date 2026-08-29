"""Skill 资源文件读取工具 — 按需读取技能捆绑的 scripts/data/templates 等文件"""
import logging
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_READ_SIZE = 8000


class ReadSkillFileInput(BaseModel):
    skill_name: str = Field(description="技能名称（与 Skill 管理页中的名称一致）")
    relative_path: str = Field(
        description="资源文件相对路径，如 scripts/validate.py 或 data/config.json"
    )


def _read_skill_file(skill_name: str, relative_path: str) -> str:
    """读取指定技能的捆绑资源文件内容"""
    try:
        from app.models.skill_config import SkillConfig
        from app.core.agent.runtime_context import get_tenant_id

        tenant_id = int(get_tenant_id())
        skill = SkillConfig.query.filter_by(
            tenant_id=tenant_id, name=skill_name, is_active=True
        ).first()
        if not skill:
            return f"未找到技能: {skill_name}（请检查技能名是否与 Skill 管理页一致）"

        content = skill.read_resource(relative_path)
        if content is None:
            available = skill.list_resources()
            return (
                f"文件不存在或不可读: {relative_path}。"
                f"该技能可读的资源: {available or '无'}"
            )

        if len(content) > MAX_READ_SIZE:
            content = content[:MAX_READ_SIZE] + f"\n...(共 {len(content)} 字符，已截断)"

        return content
    except Exception as e:
        logger.warning(f"read_skill_file failed: {e}")
        return f"读取技能资源失败: {str(e)}"


read_skill_file_tool = StructuredTool.from_function(
    name="read_skill_file",
    description=(
        "读取指定技能的捆绑资源文件（scripts/data/templates 等目录）。"
        "当技能说明中提到可按需读取的资源文件时，用此工具获取内容。"
        "参数: skill_name 技能名, relative_path 文件相对路径。"
    ),
    func=_read_skill_file,
    args_schema=ReadSkillFileInput,
)
