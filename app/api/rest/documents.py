from fastapi import APIRouter
from app.schemas.document import DocumentCreate, DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", response_model=DocumentResponse)
async def create_document(doc_in: DocumentCreate):
    return {"id": 1, "title": doc_in.title, "content": "", "revision": 0}


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int):
    return {"id": doc_id, "title": "Mock", "content": "", "revision": 0}
