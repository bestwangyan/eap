"""Phase 2: 知识库数据模型"""
from app.extensions import db
from app.models.base import BaseModel


class KnowledgeCollection(BaseModel):
    """知识库集合"""
    __tablename__ = "knowledge_collections"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    embedding_model = db.Column(db.String(100), default="text-embedding-3-small")
    chunk_size = db.Column(db.Integer, default=1000)
    chunk_overlap = db.Column(db.Integer, default=200)

    documents = db.relationship("KnowledgeDocument", back_populates="collection",
                                cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_kb_collection_tenant_name"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "embedding_model": self.embedding_model,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "document_count": len(self.documents) if self.documents else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class KnowledgeDocument(BaseModel):
    """知识库文档"""
    __tablename__ = "knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(
        db.Integer, db.ForeignKey("knowledge_collections.id"), nullable=False
    )
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    filename = db.Column(db.String(500))
    file_type = db.Column(db.String(20))
    file_size = db.Column(db.Integer)
    file_path = db.Column(db.String(1000))
    status = db.Column(db.String(20), default="pending")
    chunk_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)

    collection = db.relationship("KnowledgeCollection", back_populates="documents")

    def to_dict(self):
        return {
            "id": self.id,
            "collection_id": self.collection_id,
            "tenant_id": self.tenant_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
