"""Skill 配置 - 用户上传的 Skill 压缩包"""
import os
import zipfile
import yaml
import shutil
import hashlib
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class SkillConfig(BaseModel):
    """用户上传的 Skill"""
    __tablename__ = "skill_configs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    version = db.Column(db.String(20), default="1.0.0")
    author = db.Column(db.String(100))
    tools = db.Column(db.JSON, default=list)       # 依赖的工具列表
    tags = db.Column(db.JSON, default=list)         # 标签
    trigger_keywords = db.Column(db.JSON, default=list)  # 触发关键词
    file_path = db.Column(db.String(500))           # 解压后存储路径
    original_filename = db.Column(db.String(500))   # 原始压缩包名
    file_hash = db.Column(db.String(64))            # SHA256 去重
    is_active = db.Column(db.Boolean, default=True)
    mode = db.Column(db.String(20), default="prompt")  # "prompt" | "agent"
    skill_content = db.Column(db.Text)              # SKILL.md 完整内容

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_skill_tenant_name"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tools": self.tools,
            "tags": self.tags,
            "trigger_keywords": self.trigger_keywords,
            "original_filename": self.original_filename,
            "is_active": self.is_active,
            "mode": self.mode or "prompt",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_zip(cls, zip_data: bytes, filename: str, tenant_id: int,
                 storage_root: str = "/home/wangyan/deploy/eap/skills_storage") -> "SkillConfig":
        """从 ZIP 压缩包创建 Skill 配置

        压缩包结构要求:
        ├── <skill_name>/
        │   ├── SKILL.md       (必须, YAML frontmatter + Markdown)
        │   ├── scripts/       (可选)
        │   ├── prompts/       (可选)
        │   └── ...

        SKILL.md frontmatter:
        ---
        name: web_search
        description: 搜索技能
        version: 1.0.0
        author: xxx
        tools: [search, fetch]
        tags: [search, web]
        trigger_keywords: [搜索, 查找]
        ---
        """
        file_hash = hashlib.sha256(zip_data).hexdigest()

        # 检查是否已存在相同文件
        existing = cls.query.filter_by(
            tenant_id=tenant_id, file_hash=file_hash
        ).first()
        if existing:
            raise ValueError(f"Skill 已存在 (同名: {existing.name})")

        # 解压到临时目录
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, filename)
            with open(zip_path, "wb") as f:
                f.write(zip_data)

            extract_dir = os.path.join(tmpdir, "extracted")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # 查找 SKILL.md
            skill_md_path = None
            skill_dir = None
            for root, dirs, files in os.walk(extract_dir):
                if "SKILL.md" in files:
                    skill_md_path = os.path.join(root, "SKILL.md")
                    skill_dir = root
                    break

            if not skill_md_path:
                raise ValueError("压缩包中未找到 SKILL.md 文件")

            # 解析 SKILL.md frontmatter
            with open(skill_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            metadata = cls._parse_frontmatter(content)

            # 验证必填字段
            if not metadata.get("name"):
                raise ValueError("SKILL.md frontmatter 缺少必填字段: name")

            skill_name = metadata["name"]

            # 检查租户内是否重名
            if cls.query.filter_by(tenant_id=tenant_id, name=skill_name).first():
                raise ValueError(f"Skill '{skill_name}' 已存在")

            # 持久化到存储目录
            storage_path = os.path.join(storage_root, str(tenant_id), skill_name)
            if os.path.exists(storage_path):
                shutil.rmtree(storage_path)
            shutil.copytree(skill_dir, storage_path)

            # 创建数据库记录
            skill = cls(
                tenant_id=tenant_id,
                name=skill_name,
                description=metadata.get("description", ""),
                version=metadata.get("version", "1.0.0"),
                author=metadata.get("author", ""),
                tools=metadata.get("tools", []),
                tags=metadata.get("tags", []),
                trigger_keywords=metadata.get("trigger_keywords", []),
                mode=metadata.get("mode", "prompt"),
                file_path=storage_path,
                original_filename=filename,
                file_hash=file_hash,
                is_active=True,
                skill_content=content,
            )
            db.session.add(skill)
            db.session.commit()

        return skill

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        """解析 YAML frontmatter"""
        if not content.startswith("---"):
            return {}

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}

        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}

    def get_prompt(self) -> str:
        """获取 Skill 运行时提示词（SKILL.md 中 frontmatter 之后的正文）"""
        if not self.skill_content:
            return ""
        parts = self.skill_content.split("---", 2)
        return parts[2].strip() if len(parts) >= 3 else self.skill_content

    # =========================================================================
    # 资源文件管理（scripts / references / prompts 等 bundled 资源）
    # =========================================================================

    # 需要注入到上下文中的资源目录（文件内容直接拼入系统提示词）
    INLINE_DIRS = ("references", "prompts", "docs")

    # 按需读取的资源目录（LLM 可以通过 read_skill_file 工具读取）
    ON_DEMAND_DIRS = ("scripts", "data", "templates")

    def list_resources(self) -> dict[str, list[str]]:
        """
        扫描 skill 目录下的资源文件，按类型分类。

        Returns:
            {
              "references": ["api_guide.md", "schema.md"],
              "scripts": ["validate.py"],
              "prompts": ["detailed_instruction.md"],
              "data": ["config.json"],
              ...
            }
        """
        result: dict[str, list[str]] = {}
        if not self.file_path or not os.path.isdir(self.file_path):
            return result

        for entry in os.listdir(self.file_path):
            entry_path = os.path.join(self.file_path, entry)
            if os.path.isdir(entry_path) and entry.lower() not in ("agents",):
                files = []
                for f in sorted(os.listdir(entry_path)):
                    fp = os.path.join(entry_path, f)
                    if os.path.isfile(fp) and not f.startswith("."):
                        files.append(f)
                if files:
                    result[entry.lower()] = files
        return result

    def read_resource(self, relative_path: str) -> str | None:
        """
        读取 skill 目录下的指定资源文件。

        Args:
            relative_path: 相对路径，如 "scripts/validate.py" 或 "references/guide.md"

        Returns:
            文件内容字符串，或 None（文件不存在/越权/编码错误）
        """
        if not self.file_path or not os.path.isdir(self.file_path):
            return None

        # 安全检查：禁止 ../ 路径穿越
        normalized = os.path.normpath(relative_path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            return None

        full_path = os.path.join(self.file_path, normalized)
        if not os.path.isfile(full_path):
            return None

        # 只读文本类文件，拒绝二进制
        ext = os.path.splitext(full_path)[1].lower()
        if ext in (".pyc", ".pyo", ".so", ".dll", ".exe", ".zip", ".bin"):
            return None

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except (UnicodeDecodeError, PermissionError):
            return None

    def get_inline_context(self) -> str:
        """
        获取需要注入到系统提示词中的资源内容。
        扫描 references/、prompts/、docs/ 目录，将其内容拼入上下文。
        """
        resources = self.list_resources()
        parts = []

        for dir_name in self.INLINE_DIRS:
            files = resources.get(dir_name, [])
            for fname in files:
                content = self.read_resource(f"{dir_name}/{fname}")
                if content:
                    # 截断过长文件，避免撑爆上下文
                    truncated = content[:2000]
                    if len(content) > 2000:
                        truncated += "\n...(内容过长，已截断，可用 read_skill_file 读取完整内容)"
                    parts.append(
                        f"### 资源: {self.name}/{dir_name}/{fname}\n"
                        f"{truncated}\n"
                    )

        return "\n".join(parts) if parts else ""

    def get_on_demand_manifest(self) -> str:
        """
        生成按需读取的资源清单文本，供 LLM 了解有哪些文件可用。
        """
        resources = self.list_resources()
        lines = []
        for dir_name in self.ON_DEMAND_DIRS:
            files = resources.get(dir_name, [])
            for fname in files:
                lines.append(f"- `{self.name}/{dir_name}/{fname}`")

        if not lines:
            return ""
        return (
            f"\n📁 **{self.name}** 附带以下可按需读取的资源文件:\n"
            + "\n".join(lines)
        )
