import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.db import SessionLocal
from app.api.rest.auth import authenticate_token_only
from app.api.ws.manager import manager
from app.api.ws.ot import apply_op, transform_against_history
from app.services.presence import presence_service
from app.services.ai import ai_service
from app.models.document import Document, DocumentOperation
from app.schemas.events import WSClientEvent, WSServerEvent, OTDelta, UserPresenceInfo
from app.core.metrics import ACTIVE_WS_CONNECTIONS, DOCUMENT_DELTAS_TOTAL, AI_ANALYSIS_TRIGGERS_TOTAL, OT_CONCURRENT_CONFLICTS_TOTAL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websockets"])


@router.websocket("/doc/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: int,
    token: str = Query(..., description="JWT authentication token")
):
    """
    Real-time collaborative document synchronization endpoint.
    Validates JWT query tokens, maintains status heartbeats, resolves concurrent
    Operational Transform conflict blocks, and forwards actions to other server instances.
    """
    # 1. Authenticate connection
    async with SessionLocal() as db:
        user = await authenticate_token_only(token, db)
        if not user:
            logger.warning(f"Rejected WS connection to room {room_id}: Invalid token.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Double-check document room exists
        doc_res = await db.execute(select(Document).where(Document.id == room_id))
        doc_exists = doc_res.scalar_one_or_none()
        if not doc_exists:
            logger.warning(f"Rejected WS connection: Document room {room_id} does not exist.")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

    # 2. Join Room & Presence tracking
    await manager.connect(websocket, room_id)
    ACTIVE_WS_CONNECTIONS.labels(room_id=room_id).inc()
    
    # Track user info in websocket state
    websocket.state.user_id = user.id
    websocket.state.email = user.email

    try:
        # Register presence in Redis
        await presence_service.set_online(user.id, user.email, room_id)
        
        # Broadcast join notification to room
        active_users = await presence_service.get_active_users(room_id)
        join_event = WSServerEvent(
            event_type="user_joined",
            user_id=user.id,
            email=user.email,
            users=active_users
        )
        await manager.broadcast_to_redis(room_id, join_event)

        # 3. Connection listener loop
        while True:
            data = await websocket.receive_text()
            try:
                event_data = json.loads(data)
                client_event = WSClientEvent(**event_data)
            except Exception as e:
                logger.warning(f"Malformed event payload from user {user.id}: {e}")
                err_event = WSServerEvent(event_type="error", error="Invalid payload format")
                await websocket.send_text(err_event.model_dump_json())
                continue

            # Heartbeat handling
            if client_event.event_type == "heartbeat":
                await presence_service.set_online(user.id, user.email, room_id)
                continue

            # Cursor position tracking broadcast (Premium UX feature)
            elif client_event.event_type == "cursor":
                cursor_event = WSServerEvent(
                    event_type="presence_update",
                    user_id=user.id,
                    email=user.email,
                    error=f"cursor_pos:{client_event.cursor_pos}"  # Safely pack cursor into generic field
                )
                await manager.broadcast_to_redis(room_id, cursor_event)
                continue

            # Delta/Edit operational transform synchronizer
            elif client_event.event_type == "delta":
                if not client_event.delta:
                    continue

                client_delta = client_event.delta
                
                # DB transaction block with row level locking (SELECT FOR UPDATE)
                async with SessionLocal() as db_session:
                    try:
                        # Locking the document row to guarantee atomic, sequential transform calculations
                        stmt = select(Document).where(Document.id == room_id).with_for_update()
                        res = await db_session.execute(stmt)
                        doc = res.scalar_one_or_none()

                        if not doc:
                            raise HTTPException(status_code=404, detail="Document missing")

                        # Query outstanding concurrent server-applied modifications since the client's revision
                        op_stmt = (
                            select(DocumentOperation)
                            .where(
                                DocumentOperation.document_id == room_id,
                                DocumentOperation.revision >= client_delta.revision
                            )
                            .order_by(DocumentOperation.revision.asc())
                        )
                        op_res = await db_session.execute(op_stmt)
                        history = op_res.scalars().all()

                        history_deltas = [
                            OTDelta(op=h.op, pos=h.pos, chars=h.chars, revision=h.revision)
                            for h in history
                        ]

                        # Calculate transforms mathematically
                        if history_deltas:
                            OT_CONCURRENT_CONFLICTS_TOTAL.labels(room_id=room_id).inc()
                            transformed_ops = transform_against_history(client_delta, history_deltas)
                            logger.info(f"Conflict resolved. Transformed {client_delta} into {len(transformed_ops)} ops against {len(history_deltas)} history ops.")
                        else:
                            # Apply directly
                            transformed_ops = [client_delta]

                        # Apply resulting operations sequentially
                        for transformed_op in transformed_ops:
                            # 1. Update text state
                            doc.content = apply_op(doc.content, transformed_op)
                            # 2. Advance document revision
                            doc.revision += 1
                            
                            # 3. Log mutation operation
                            db_op = DocumentOperation(
                                document_id=room_id,
                                user_id=user.id,
                                op=transformed_op.op,
                                pos=transformed_op.pos,
                                chars=transformed_op.chars,
                                revision=doc.revision
                            )
                            db_session.add(db_op)

                            # 4. Broadcast edit to all room participants
                            broadcast_payload = WSServerEvent(
                                event_type="delta_broadcast",
                                delta=OTDelta(
                                    op=transformed_op.op,
                                    pos=transformed_op.pos,
                                    chars=transformed_op.chars,
                                    revision=doc.revision
                               ),
                                user_id=user.id,
                                email=user.email
                            )
                            await manager.broadcast_to_redis(room_id, broadcast_payload)
                            DOCUMENT_DELTAS_TOTAL.labels(room_id=room_id, op_type=transformed_op.op).inc()

                        # Commit the atomic update
                        await db_session.commit()

                        # Trigger debounced background AI annotation streaming
                        AI_ANALYSIS_TRIGGERS_TOTAL.labels(room_id=room_id).inc()
                        await ai_service.trigger_analysis(room_id, doc.content)

                    except Exception as transaction_err:
                        await db_session.rollback()
                        logger.error(f"Failed to process OT delta in transaction: {transaction_err}", exc_info=True)
                        err_event = WSServerEvent(event_type="error", error="Failed to synchronize edit")
                        await websocket.send_text(err_event.model_dump_json())

    except WebSocketDisconnect:
        logger.info(f"User {user.id} disconnected from room {room_id}")
    except Exception as general_err:
        logger.error(f"Unexpected connection error in room {room_id}: {general_err}", exc_info=True)
    finally:
        # 4. Disconnect, cleanup, and broadcast leave notifications
        await manager.disconnect(websocket, room_id)
        ACTIVE_WS_CONNECTIONS.labels(room_id=room_id).dec()
        await presence_service.set_offline(user.id, room_id)
        
        # Broadcast refreshed online user presence details
        active_users = await presence_service.get_active_users(room_id)
        leave_event = WSServerEvent(
            event_type="user_left",
            user_id=user.id,
            email=user.email,
            users=active_users
        )
        await manager.broadcast_to_redis(room_id, leave_event)
