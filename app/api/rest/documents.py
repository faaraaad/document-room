from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.api.rest.auth import get_current_user
from app.models.user import User
from app.models.document import Document, DocumentSnapshot
from app.schemas.document import DocumentCreate, DocumentOut, SnapshotOut
from app.services.snapshot import snapshot_service
from app.core.metrics import SNAPSHOTS_CREATED_TOTAL

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    doc_in: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Creates a new blank document room.
    """
    db_doc = Document(
        title=doc_in.title,
        content="",
        revision=0
    )
    db.add(db_doc)
    await db.flush()
    return db_doc


@router.get("/", response_model=List[DocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lists all available document rooms.
    """
    result = await db.execute(select(Document).order_by(Document.updated_at.desc()))
    return result.scalars().all()


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the current state (title, content, and revision) of a specific document.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document room not found.")
    return doc


@router.get("/{document_id}/snapshots", response_model=List[SnapshotOut])
async def list_document_snapshots(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the complete list of S3 snapshots taken for a specific document.
    """
    # Verify document exists
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document room not found.")

    snap_result = await db.execute(
        select(DocumentSnapshot)
        .where(DocumentSnapshot.document_id == document_id)
        .order_by(DocumentSnapshot.created_at.desc())
    )
    return snap_result.scalars().all()


@router.post("/{document_id}/snapshot", response_model=SnapshotOut, status_code=status.HTTP_201_CREATED)
async def trigger_manual_snapshot(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually forces an instant S3/MinIO snapshot of the current state of a document.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document room not found.")

    # Save to S3 via service
    s3_key = await snapshot_service.save_snapshot(
        db=db,
        document_id=doc.id,
        content=doc.content,
        revision=doc.revision
    )
    
    # Commit changes
    await db.commit()

    # Track Prometheus metric
    SNAPSHOTS_CREATED_TOTAL.labels(document_id=doc.id).inc()

    # Fetch snapshot record
    snap_check = await db.execute(
        select(DocumentSnapshot)
        .where(DocumentSnapshot.document_id == document_id, DocumentSnapshot.revision == doc.revision)
        .order_by(DocumentSnapshot.created_at.desc())
    )
    snap = snap_check.scalars().first()
    return snap
