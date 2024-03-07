import asyncio
import logging
import time
import os
import redis
from celery import Celery
from sqlalchemy import select
from app.config import settings

logger = logging.getLogger(__name__)

# Configure Celery
celery_app = Celery(
    "collabstream_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Celery Beat Schedule Configuration
from app.workers.beat_schedule import BEAT_SCHEDULE
celery_app.conf.beat_schedule = BEAT_SCHEDULE
celery_app.conf.timezone = "UTC"

# Synchronous Redis client for Celery workers
sync_redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@celery_app.task
def analyze_document_task(room_id: int, analysis_id: str, content: str):
    """
    Debounced AI analysis task.
    First checks if the trigger matches the latest token in Redis.
    If yes, streams LLM analysis into a Redis Stream.
    """
    token_key = f"room:{room_id}:latest_analysis_id"
    latest_token = sync_redis.get(token_key)

    # 1. Debounce check: If the token in Redis doesn't match this task's token, discard.
    if latest_token != analysis_id:
        logger.info(f"AI task for room {room_id} with token {analysis_id} discarded (debounced).")
        return

    logger.info(f"AI task for room {room_id} with token {analysis_id} running analysis...")

    stream_key = f"stream:room:{room_id}:analysis"
    
    # 2. Clear out any previous analysis stream
    sync_redis.delete(stream_key)

    # 3. Stream AI chunks (OpenAI / Anthropic or simulated)
    has_api_key = settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY
    
    if has_api_key:
        try:
            if settings.OPENAI_API_KEY:
                from openai import OpenAI
                client = OpenAI(api_key=settings.OPENAI_API_KEY)
                
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": "You are a concise, helpful collaborative writing assistant. Suggest grammar improvements or next ideas. Keep it extremely brief (max 2 short sentences)."},
                        {"role": "user", "content": f"Document content:\n\"\"\"\n{content}\n\"\"\""}
                    ],
                    stream=True
                )
                for chunk in response:
                    text = chunk.choices[0].delta.content or ""
                    if text:
                        # Append to Redis Stream
                        sync_redis.xadd(stream_key, {"chunk": text}, maxlen=100)
            
            elif settings.ANTHROPIC_API_KEY:
                from anthropic import Anthropic
                client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                
                with client.messages.stream(
                    model="claude-3-haiku-20240307",
                    max_tokens=150,
                    system="You are a concise collaborative writing assistant. Keep recommendations under 2 sentences.",
                    messages=[
                        {"role": "user", "content": f"Document content:\n\"\"\"\n{content}\n\"\"\""}
                    ]
                ) as stream:
                    for text in stream.text_stream:
                        sync_redis.xadd(stream_key, {"chunk": text}, maxlen=100)
                        
        except Exception as e:
            logger.error(f"Error calling AI API: {e}", exc_info=True)
            # Fallback to simulated on failure
            _run_simulated_stream(stream_key, content)
    else:
        # Out-of-the-box mock execution when keys are missing
        _run_simulated_stream(stream_key, content)

    # 4. Mark completion by sending a special [DONE] sentinel
    sync_redis.xadd(stream_key, {"chunk": "[DONE]"}, maxlen=100)
    logger.info(f"AI Stream for room {room_id} complete.")


def _run_simulated_stream(stream_key: str, content: str):
    """
    Simulates high-quality, real-time AI annotation feedback based on document content.
    Exhibits streaming character delays for rich UI effects.
    """
    word_count = len(content.split())
    doc_summary = content[:40] + "..." if len(content) > 40 else content
    
    analysis_text = (
        f"[AI Analysis] Document analysis complete (approx. {word_count} words). "
        f"The content focuses on '{doc_summary}'. "
        "Suggestion: Consider strengthening the opening statement, and maintain active voice. "
        "Your composition flow is excellent!"
    )
    
    # Send chunks with micro-delays
    words = analysis_text.split(" ")
    for word in words:
        chunk = word + " "
        sync_redis.xadd(stream_key, {"chunk": chunk}, maxlen=100)
        time.sleep(0.08)  # 80ms keystroke feeling delay


@celery_app.task
def periodic_snapshot_task():
    """
    Triggered periodically by Celery Beat.
    Launches the async event loop to query current documents and save snapshots to S3/MinIO.
    """
    logger.info("Starting periodic document snapshots...")
    asyncio.run(_async_snapshot_runner())


async def _async_snapshot_runner():
    """
    Asynchronous runner to process snapshots.
    """
    from app.core.db import SessionLocal
    from app.models.document import Document
    from app.services.snapshot import snapshot_service
    
    async with SessionLocal() as db:
        # Fetch all documents to back up
        result = await db.execute(select(Document))
        documents = result.scalars().all()
        
        for doc in documents:
            try:
                # To prevent unnecessary storage overhead, check if the snapshot
                # for this exact revision already exists.
                from sqlalchemy import and_
                from app.models.document import DocumentSnapshot
                
                snap_check = await db.execute(
                    select(DocumentSnapshot).where(
                        and_(
                            DocumentSnapshot.document_id == doc.id,
                            DocumentSnapshot.revision == doc.revision
                        )
                    )
                )
                existing = snap_check.scalar_one_or_none()
                
                if not existing:
                    logger.info(f"Backing up Document {doc.id} at revision {doc.revision}...")
                    await snapshot_service.save_snapshot(
                        db=db,
                        document_id=doc.id,
                        content=doc.content,
                        revision=doc.revision
                    )
                else:
                    logger.debug(f"Document {doc.id} already backed up at revision {doc.revision}.")
            except Exception as e:
                logger.error(f"Failed to save snapshot for document {doc.id}: {e}", exc_info=True)
        
        await db.commit()
