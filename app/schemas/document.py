from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DocumentCreate(BaseModel):
    title: str


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class DocumentOut(BaseModel):
    id: int
    title: str
    content: str
    revision: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SnapshotOut(BaseModel):
    id: int
    document_id: int
    s3_key: str
    revision: int
    created_at: datetime

    class Config:
        from_attributes = True
