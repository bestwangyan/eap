"""Phase 2: 知识库 API"""
import os
import logging
from flask import Blueprint, request, jsonify, g, current_app

from app.extensions import db
from app.middleware.auth import require_tenant_context, require_permission
from app.models.knowledge import KnowledgeCollection, KnowledgeDocument
from app.core.knowledge.pipeline import DocumentPipeline
from app.core.knowledge.retriever import HybridRetriever
from app.models.audit_log import AuditLog

knowledge_bp = Blueprint("knowledge", __name__)
logger = logging.getLogger(__name__)


@knowledge_bp.route("/knowledge/collections", methods=["GET"])
@require_tenant_context
def list_collections():
    collections = KnowledgeCollection.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(KnowledgeCollection.created_at.desc()).all()
    return jsonify({"collections": [c.to_dict() for c in collections]}), 200


@knowledge_bp.route("/knowledge/collections/<int:collection_id>", methods=["GET"])
@require_tenant_context
def get_collection(collection_id):
    c = KnowledgeCollection.query.filter_by(
        id=collection_id, tenant_id=g.tenant_id
    ).first()
    if not c:
        return jsonify({"error": "知识库不存在"}), 404
    return jsonify({"collection": c.to_dict()}), 200


@knowledge_bp.route("/knowledge/collections", methods=["POST"])
@require_permission("knowledge:create")
def create_collection():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "name is required"}), 422
    c = KnowledgeCollection(
        tenant_id=g.tenant_id, name=data["name"],
        description=data.get("description", ""),
        embedding_model=data.get("embedding_model", "text-embedding-3-small"),
        chunk_size=data.get("chunk_size", 1000),
        chunk_overlap=data.get("chunk_overlap", 200),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"collection": c.to_dict()}), 201


@knowledge_bp.route("/knowledge/collections/<int:collection_id>", methods=["PUT"])
@require_permission("knowledge:update")
def update_collection(collection_id):
    c = KnowledgeCollection.query.filter_by(id=collection_id, tenant_id=g.tenant_id).first()
    if not c:
        return jsonify({"error": "知识库不存在"}), 404
    data = request.get_json()
    for field in ["name", "description", "chunk_size", "chunk_overlap"]:
        if field in data:
            setattr(c, field, data[field])
    db.session.commit()
    return jsonify({"collection": c.to_dict()}), 200


@knowledge_bp.route("/knowledge/collections/<int:collection_id>", methods=["DELETE"])
@require_permission("knowledge:delete")
def delete_collection(collection_id):
    c = KnowledgeCollection.query.filter_by(id=collection_id, tenant_id=g.tenant_id).first()
    if not c:
        return jsonify({"error": "知识库不存在"}), 404
    # 删除向量表
    from sqlalchemy import text
    try:
        db.session.execute(text(f"DROP TABLE IF EXISTS kb_chunks_{collection_id}"))
        db.session.commit()
    except Exception as e:
        logger.warning(f"Failed to drop vector table: {e}")
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "已删除"}), 200


@knowledge_bp.route("/knowledge/collections/<int:collection_id>/documents/upload", methods=["POST"])
@require_permission("knowledge:create")
def upload_document(collection_id):
    c = KnowledgeCollection.query.filter_by(id=collection_id, tenant_id=g.tenant_id).first()
    if not c:
        return jsonify({"error": "知识库不存在"}), 404
    if "file" not in request.files:
        return jsonify({"error": "请选择文件"}), 422

    file = request.files["file"]
    storage_dir = os.path.join(
        current_app.config.get("UPLOAD_FOLDER", "/tmp/eap_uploads"),
        "knowledge", str(g.tenant_id), str(collection_id)
    )
    try:
        pipeline = DocumentPipeline()
        doc = pipeline.process(
            file_data=file.read(), filename=file.filename,
            collection_id=collection_id, tenant_id=g.tenant_id, storage_dir=storage_dir
        )
        AuditLog.log(tenant_slug=g.tenant_slug, user_id=int(g.user_id),
                     action="knowledge:upload", resource="knowledge_document",
                     resource_id=str(doc.id),
                     detail={"filename": file.filename, "collection_id": collection_id})
        return jsonify({"document": doc.to_dict()}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.exception("Document upload failed")
        return jsonify({"error": f"处理失败: {str(e)}"}), 500


@knowledge_bp.route("/knowledge/collections/<int:collection_id>/documents", methods=["GET"])
@require_tenant_context
def list_documents(collection_id):
    docs = KnowledgeDocument.query.filter_by(
        collection_id=collection_id, tenant_id=g.tenant_id
    ).order_by(KnowledgeDocument.created_at.desc()).all()
    return jsonify({"documents": [d.to_dict() for d in docs]}), 200


@knowledge_bp.route("/knowledge/documents/<int:document_id>", methods=["DELETE"])
@require_permission("knowledge:delete")
def delete_document(document_id):
    doc = KnowledgeDocument.query.filter_by(id=document_id, tenant_id=g.tenant_id).first()
    if not doc:
        return jsonify({"error": "文档不存在"}), 404
    pipeline = DocumentPipeline()
    pipeline.delete_document_chunks(doc.id, doc.collection_id)
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    db.session.delete(doc)
    db.session.commit()
    return jsonify({"message": "已删除"}), 200


@knowledge_bp.route("/knowledge/search", methods=["POST"])
@require_tenant_context
def search():
    data = request.get_json()
    if not data or "query" not in data or "collection_id" not in data:
        return jsonify({"error": "query and collection_id are required"}), 422
    retriever = HybridRetriever()
    results = retriever.search(
        query=data["query"], collection_id=data["collection_id"],
        tenant_id=g.tenant_id, top_k=data.get("top_k", 5)
    )
    return jsonify({"results": results, "query": data["query"]}), 200
