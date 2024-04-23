import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.workers.tasks import analyze_document_task
from app.api.sse.analysis import tail_analysis_stream


@pytest.mark.asyncio
async def test_debounce_filtering():
    """
    Verifies that the Celery worker discards tasks if the analysis token
    in Redis has been overwritten by a subsequent keystroke.
    """
    room_id = 101
    content = "Hello World"
    stale_token = "stale-uuid-1"
    fresh_token = "fresh-uuid-2"

    # Mock Redis client
    with patch("app.workers.tasks.sync_redis") as mock_redis:
        # Scenario A: Stale token. Redis has a newer token.
        mock_redis.get.return_value = fresh_token
        
        analyze_document_task(room_id, stale_token, content)
        
        # Should not write to Redis stream since it is debounced
        mock_redis.xadd.assert_not_called()
        mock_redis.delete.assert_not_called()

        # Scenario B: Fresh token. Redis token matches.
        mock_redis.get.return_value = fresh_token
        
        analyze_document_task(room_id, fresh_token, content)
        
        # Should clean the stream first and push chunks
        mock_redis.delete.assert_called_with(f"stream:room:{room_id}:analysis")
        mock_redis.xadd.assert_called()


@pytest.mark.asyncio
async def test_simulated_stream_writing():
    """
    Verifies that the simulated stream writes chunks and the final [DONE] sentinel.
    """
    room_id = 102
    content = "Some text"
    token = "token-1"

    with patch("app.workers.tasks.sync_redis") as mock_redis, \
         patch("app.workers.tasks.time.sleep") as mock_sleep:  # Speed up tests
        
        mock_redis.get.return_value = token
        
        analyze_document_task(room_id, token, content)
        
        # Verify chunks were added
        mock_redis.xadd.assert_called()
        
        # Verify the last call was the [DONE] sentinel
        last_call_args = mock_redis.xadd.call_args_list[-1]
        assert last_call_args[0][0] == f"stream:room:{room_id}:analysis"
        assert last_call_args[0][1] == {"chunk": "[DONE]"}


@pytest.mark.asyncio
@patch("app.api.sse.analysis.redis_client", new_callable=AsyncMock)
async def test_sse_generator_consumption(mock_redis):
    """
    Verifies that the SSE generator reads from Redis Stream
    and yields chunk objects, terminating gracefully on [DONE].
    """
    room_id = 103
    stream_key = f"stream:room:{room_id}:analysis"
    
    # Configure mock Redis xread to return two batches
    # First batch: some text chunks
    # Second batch: [DONE] sentinel
    mock_redis.xread.side_effect = [
        [
            (stream_key, [
                ("1-0", {"chunk": "Hello "}),
                ("2-0", {"chunk": "World!"})
            ])
        ],
        [
            (stream_key, [
                ("3-0", {"chunk": "[DONE]"})
            ])
        ]
    ]

    # Consume the SSE generator
    results = []
    async for event in tail_analysis_stream(room_id):
        results.append(event)

    # Assertions
    assert len(results) == 3
    assert results[0] == f"data: {json.dumps({'chunk': 'Hello '})}\n\n"
    assert results[1] == f"data: {json.dumps({'chunk': 'World!'})}\n\n"
    assert results[2] == "data: [DONE]\n\n"
    
    # Assert xread was queried starting with 0-0, then advancing last_id
    assert mock_redis.xread.call_count == 2
    mock_redis.xread.assert_any_call(streams={stream_key: "0-0"}, count=100, block=1000)
    mock_redis.xread.assert_any_call(streams={stream_key: "2-0"}, count=100, block=1000)
