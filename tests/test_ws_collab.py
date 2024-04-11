import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.api.ws.manager import manager
from app.schemas.events import WSServerEvent, OTDelta


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_auth():
    """
    Mock JWT token validation to return mock users.
    """
    with patch("app.api.ws.router.authenticate_token_only") as mock:
        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.email = "collab1@example.com"
        mock.return_value = mock_user
        yield mock


@pytest.fixture
def mock_db():
    """
    Mock Database Session returned on startup.
    """
    with patch("app.api.ws.router.SessionLocal") as mock_session_local:
        mock_db_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db_session
        yield mock_db_session


@pytest.fixture
def mock_redis():
    """
    Mock Redis client interactions inside manager and presence.
    """
    with patch("app.api.ws.manager.redis_client") as mock_r, \
         patch("app.services.presence.redis_client") as mock_presence_r:
        mock_r.publish = AsyncMock()
        
        # Mock scan returning no active users initially
        mock_presence_r.scan = AsyncMock(return_value=(0, []))
        yield mock_r


def test_websocket_auth_rejection(client):
    """
    Checks that a WebSocket connection without a valid JWT token query param is rejected.
    """
    # Force authenticate_token_only to return None
    with patch("app.api.ws.router.authenticate_token_only", return_value=None):
        with pytest.raises(Exception):  # TestClient raises WebSocketDisconnect or exception
            with client.websocket_connect("/ws/doc/1?token=invalid-token") as ws:
                pass


def test_websocket_collaboration_handshake(client, mock_auth, mock_db, mock_redis):
    """
    Verifies successful WebSocket connection, presence tracking online triggers,
    and user joining announcements.
    """
    # 1. Mock DB returning document
    mock_doc = MagicMock()
    mock_doc.id = 1
    mock_doc.content = "Initial content"
    mock_doc.revision = 10
    
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        mock_auth.return_value,  # User authentication check
        mock_doc,                 # Document check
    ]

    # 2. Establish connection
    with client.websocket_connect("/ws/doc/1?token=valid-jwt") as ws:
        # Check that connection was registered in WS manager
        assert len(manager.active_connections[1]) == 1
        
        # Verify join event was published to Redis pub/sub room channel
        mock_redis.publish.assert_called()
        call_args = mock_redis.publish.call_args[0]
        assert call_args[0] == "channel:room:1"
        
        # Verify payload contains "user_joined"
        payload = json.loads(call_args[1])
        assert payload["event_type"] == "user_joined"
        assert payload["email"] == "collab1@example.com"


def test_websocket_delta_processing(client, mock_auth, mock_db, mock_redis):
    """
    Verifies that incoming deltas trigger row locking, conflict resolution,
    and broadcast updates.
    """
    mock_doc = MagicMock()
    mock_doc.id = 1
    mock_doc.content = "Initial content"
    mock_doc.revision = 10
    
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [
        mock_auth.return_value,  # User authentication
        mock_doc,                 # Document check on connect
        mock_doc                  # Document check (SELECT FOR UPDATE) on delta
    ]
    
    # Mock no concurrent operations in history
    mock_history_result = MagicMock()
    mock_history_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_history_result

    with client.websocket_connect("/ws/doc/1?token=valid-jwt") as ws:
        # Reset publish calls from join event
        mock_redis.publish.reset_mock()

        # Send insertion delta
        delta_payload = {
            "event_type": "delta",
            "delta": {
                "op": "insert",
                "pos": 8,
                "chars": "ly",
                "revision": 10
            }
        }
        ws.send_text(json.dumps(delta_payload))
        
        # Give asyncio loop time to run background router blocks
        import time
        time.sleep(0.1)
        
        # Verify transactional commit & OT broadcast
        mock_db.commit.assert_called()
        mock_redis.publish.assert_called()
        
        # Check broadcast payload
        call_args = mock_redis.publish.call_args[0]
        assert call_args[0] == "channel:room:1"
        payload = json.loads(call_args[1])
        assert payload["event_type"] == "delta_broadcast"
        assert payload["delta"]["op"] == "insert"
        assert payload["delta"]["pos"] == 8
        assert payload["delta"]["chars"] == "ly"
        assert payload["delta"]["revision"] == 11
