from fastapi import APIRouter
from app.schemas.auth import UserCreate, UserLogin, Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=Token)
async def signup(user_in: UserCreate):
    return {"access_token": "mock_token", "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin):
    return {"access_token": "mock_token", "token_type": "bearer"}
