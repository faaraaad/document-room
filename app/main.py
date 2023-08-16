from fastapi import FastAPI
from app.config import settings

app = FastAPI(title=settings.PROJECT_NAME)


@app.get("/")
async def root():
    return {"status": "ok"}
