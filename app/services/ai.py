import uuid
import logging
from app.core.redis import redis_client

logger = logging.getLogger(__name__)


class AIService:
    @staticmethod
    def _latest_analysis_key(room_id: int) -> str:
        return f"room:{room_id}:latest_analysis_id"

    async def trigger_analysis(self, room_id: int, content: str) -> None:
        """
        Triggers a debounced AI analysis for the given room.
        Generates a new UUID, saves it to Redis, and dispatches a Celery task with a 0.8s countdown.
        """
        # 1. Generate unique analysis token
        analysis_id = str(uuid.uuid4())
        
        # 2. Update Redis with the latest token (this invalidates any pending tasks)
        key = self._latest_analysis_key(room_id)
        await redis_client.set(key, analysis_id)
        
        # 3. Import and dispatch the Celery task (lazy import to prevent circular dependency)
        from app.workers.tasks import analyze_document_task
        
        analyze_document_task.apply_async(
            args=[room_id, analysis_id, content],
            countdown=0.8  # Celery supports float countdowns for sub-second execution
        )
        logger.debug(f"Dispatched debounced AI analysis task for room {room_id} with token {analysis_id}")


ai_service = AIService()
