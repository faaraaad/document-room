from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class OTDelta(BaseModel):
    op: str = Field(..., description="Operation type: 'insert' or 'delete'")
    pos: int = Field(..., description="Zero-indexed string character index")
    chars: str = Field("", description="The characters to insert, or string deleted/length indicators")
    revision: int = Field(..., description="The document revision upon which this edit is based")


class WSClientEvent(BaseModel):
    event_type: str = Field(..., description="Event type: 'delta', 'heartbeat', 'cursor'")
    delta: Optional[OTDelta] = None
    cursor_pos: Optional[int] = None


class UserPresenceInfo(BaseModel):
    user_id: int
    email: str
    status: str = "online"


class WSServerEvent(BaseModel):
    event_type: str = Field(..., description="Event type: 'delta_broadcast', 'user_joined', 'user_left', 'presence_update', 'error'")
    delta: Optional[OTDelta] = None
    user_id: Optional[int] = None
    email: Optional[str] = None
    users: Optional[List[UserPresenceInfo]] = None
    error: Optional[str] = None
