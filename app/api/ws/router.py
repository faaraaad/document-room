from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.ws.manager import manager

router = APIRouter()


@router.websocket("/ws/doc/{doc_id}")
async def websocket_endpoint(websocket: WebSocket, doc_id: int):
    await manager.connect(doc_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo for now
            for conn in manager.active_connections.get(doc_id, []):
                await conn.send_text(data)
    except WebSocketDisconnect:
        manager.disconnect(doc_id, websocket)
