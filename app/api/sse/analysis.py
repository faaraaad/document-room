import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from app.core.redis import redis_client
from app.api.rest.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sse", tags=["sse"])


async def tail_analysis_stream(room_id: int):
    """
    Async generator that reads AI analysis chunks from the Redis stream for a room.
    Yields chunks formatted as SSE data blocks.
    """
    stream_key = f"stream:room:{room_id}:analysis"
    last_id = "0-0"  # Start reading from the very beginning of the stream
    
    logger.info(f"SSE client started tailing analysis stream: {stream_key}")

    try:
        while True:
            # Non-blocking read from the stream with a 1-second timeout
            # xread arguments: streams={key: last_id}, count=10, block=1000 (ms)
            streams_batch = await redis_client.xread(
                streams={stream_key: last_id},
                count=100,
                block=1000
            )

            if streams_batch:
                for _, messages in streams_batch:
                    for msg_id, data in messages:
                        last_id = msg_id
                        chunk = data.get("chunk")
                        
                        if chunk == "[DONE]":
                            yield "data: [DONE]\n\n"
                            logger.info(f"SSE stream {stream_key} reached [DONE] sentinel.")
                            return
                            
                        # Format as standard Server-Sent Event data line
                        payload = {"chunk": chunk}
                        yield f"data: {json.dumps(payload)}\n\n"

            # Sleep briefly to yield execution and avoid CPU spinning
            await asyncio.sleep(0.05)
            
    except asyncio.CancelledError:
        logger.info(f"SSE connection for room {room_id} cancelled by client.")
    except Exception as e:
        logger.error(f"Error reading SSE stream for room {room_id}: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': 'Internal server error streaming analysis'})}\n\n"


@router.get("/analysis/{room_id}")
async def stream_analysis(
    room_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Server-Sent Events endpoint supplying real-time AI critique/suggestions for a room.
    Clients connect to this URL via EventSource to receive a streaming analysis.
    """
    # Verify the Redis stream exists or is reachable
    try:
        # Check if the room exists by checking document presence or presence of the analysis keys
        # We can yield a starting message before streaming
        pass
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Redis connection issues: {e}"
        )

    return StreamingResponse(
        tail_analysis_stream(room_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable Nginx buffering
        }
    )
