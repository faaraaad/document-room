from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, document_id: int, websocket: WebSocket):
        await websocket.accept()
        if document_id not in self.active_connections:
            self.active_connections[document_id] = []
        self.active_connections[document_id].append(websocket)

    def disconnect(self, document_id: int, websocket: WebSocket):
        if document_id in self.active_connections:
            self.active_connections[document_id].remove(websocket)


manager = ConnectionManager()
