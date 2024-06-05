import json
import logging
from typing import List
from app.core.redis import redis_client
from app.schemas.events import UserPresenceInfo

logger = logging.getLogger(__name__)


class PresenceService:
    @staticmethod
    def _presence_key(user_id: int, room_id: int) -> str:
        return f"presence:user:{user_id}:room:{room_id}"

    @staticmethod
    def _room_pattern(room_id: int) -> str:
        return f"presence:user:*:room:{room_id}"

    async def set_online(self, user_id: int, email: str, room_id: int, ttl: int = 30) -> None:
        """
        Sets a user's presence to online in a specific room.
        Expiring key is set to handle unclean disconnects.
        """
        key = self._presence_key(user_id, room_id)
        data = {
            "user_id": user_id,
            "email": email,
            "status": "online"
        }
        await redis_client.setex(key, ttl, json.dumps(data))
        logger.debug(f"User {user_id} presence set to online in room {room_id}")

    async def set_offline(self, user_id: int, room_id: int) -> None:
        """
        Removes a user's presence from a room.
        """
        key = self._presence_key(user_id, room_id)
        await redis_client.delete(key)
        logger.debug(f"User {user_id} presence removed from room {room_id}")

    async def get_active_users(self, room_id: int) -> List[UserPresenceInfo]:
        """
        Queries Redis to find all active users in a specific room.
        """
        pattern = self._room_pattern(room_id)
        keys = []
        
        # Use SCAN rather than KEYS for production safety
        cursor = 0
        while True:
            cursor, batch = await redis_client.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
                
        active_users = []
        if keys:
            values = await redis_client.mget(keys)
            for val in values:
                if val:
                    try:
                        data = json.loads(val)
                        active_users.append(UserPresenceInfo(**data))
                    except Exception as e:
                        logger.error(f"Error parsing user presence data: {e}")
                        
        return active_users


presence_service = PresenceService()

# PEP8 clean audit update 4
