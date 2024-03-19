import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket
from app.core.redis import redis_client
from app.schemas.events import WSServerEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # Maps room_id -> Set of local WebSockets
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Maps room_id -> asyncio.Task for Redis Pub/Sub listening
        self.listener_tasks: Dict[int, asyncio.Task] = {}

    def _channel_name(self, room_id: int) -> str:
        return f"channel:room:{room_id}"

    async def connect(self, websocket: WebSocket, room_id: int):
        """
        Accepts WebSocket, registers it locally, and boots a Redis Pub/Sub listener if needed.
        """
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
            
        self.active_connections[room_id].add(websocket)
        logger.info(f"New client connected to room {room_id} on this server.")

        # Start a Redis Pub/Sub listener for this room if one is not already running on this instance
        if room_id not in self.listener_tasks:
            self.listener_tasks[room_id] = asyncio.create_task(
                self._redis_pubsub_listener(room_id)
            )
            logger.info(f"Started Redis Pub/Sub listener task for room {room_id}")

    async def disconnect(self, websocket: WebSocket, room_id: int):
        """
        Removes WebSocket, cleans up memory, and terminates Redis Pub/Sub listener if room is empty.
        """
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
                logger.info(f"Room {room_id} is now empty on this server.")
                
                # Cancel the pub/sub listener since no local clients remain
                task = self.listener_tasks.pop(room_id, None)
                if task:
                    task.cancel()
                    logger.info(f"Cancelled Redis Pub/Sub listener task for room {room_id}")

    async def broadcast_to_redis(self, room_id: int, message: WSServerEvent):
        """
        Publishes a message to the Redis channel for the room.
        All server instances (including this one) will receive and broadcast it to their local sockets.
        """
        channel = self._channel_name(room_id)
        payload = message.model_dump_json()
        await redis_client.publish(channel, payload)
        logger.debug(f"Broadcasted to Redis channel {channel}: {payload[:150]}")

    async def _redis_pubsub_listener(self, room_id: int):
        """
        Background listener task. It reads messages from Redis Pub/Sub for the room,
        and broadcasts them to all local WebSockets.
        """
        channel_name = self._channel_name(room_id)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)
        
        try:
            while True:
                # Wait for a message with a short timeout to prevent blocking cancellation
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data_str = message.get("data")
                    if data_str:
                        # Forward to all local WebSockets in the room
                        sockets = self.active_connections.get(room_id, set())
                        if sockets:
                            # Deliver concurrently to prevent one slow client from delaying others
                            await asyncio.gather(
                                *(self._send_safe(ws, data_str) for ws in sockets),
                                return_exceptions=True
                            )
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            logger.info(f"Redis Pub/Sub listener for room {room_id} was cancelled.")
        except Exception as e:
            logger.error(f"Error in Redis Pub/Sub listener for room {room_id}: {e}", exc_info=True)
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    async def _send_safe(self, websocket: WebSocket, message: str):
        """
        Sends a text message over a websocket, ignoring standard close errors.
        """
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.debug(f"Failed to send to client socket (likely closed): {e}")


manager = ConnectionManager()
