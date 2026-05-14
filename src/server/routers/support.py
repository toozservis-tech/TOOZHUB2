import json
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, SupportSession, SupportMessage as DBSupportMessage
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.core.security import decode_access_token_payload
from src.modules.email_client.service import EmailService
from src.core.rbac import is_admin

router = APIRouter(prefix="/api/v1/support", tags=["support"])

class ConnectionManager:
    def __init__(self):
        # customer_id -> WebSocket
        self.active_users: Dict[int, WebSocket] = {}
        # list of admin WebSockets
        self.active_admins: List[WebSocket] = []

    async def connect_user(self, websocket: WebSocket, customer_id: int):
        await websocket.accept()
        self.active_users[customer_id] = websocket
        # Send current admin status
        await websocket.send_json({
            "type": "admin_status",
            "online": len(self.active_admins) > 0
        })

    def disconnect_user(self, customer_id: int):
        if customer_id in self.active_users:
            del self.active_users[customer_id]

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self.active_admins.append(websocket)
        # Broadcast to all users that admin is online
        await self.broadcast_admin_status(True)

    async def disconnect_admin(self, websocket: WebSocket):
        if websocket in self.active_admins:
            self.active_admins.remove(websocket)
        if len(self.active_admins) == 0:
            await self.broadcast_admin_status(False)

    async def broadcast_admin_status(self, online: bool):
        message = {
            "type": "admin_status",
            "online": online
        }
        for ws in self.active_users.values():
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def send_to_admin(self, message: dict):
        for ws in self.active_admins:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def send_to_user(self, customer_id: int, message: dict):
        if customer_id in self.active_users:
            try:
                await self.active_users[customer_id].send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

def get_user_from_token(token: str, db: Session) -> Optional[Customer]:
    try:
        payload = decode_access_token_payload(token)
        email = (payload or {}).get("sub")
        if not email:
            return None
        from sqlalchemy import func
        customer = db.query(Customer).filter(func.lower(Customer.email) == str(email).strip().lower()).first()
        return customer
    except Exception:
        return None

@router.websocket("/ws/user")
async def websocket_user(websocket: WebSocket, token: str = Query(...), db: Session = Depends(get_db)):
    user = get_user_from_token(token, db)
    if not user:
        await websocket.close(code=1008)
        return
        
    await manager.connect_user(websocket, user.id)
    
    # Get or create active session
    session = db.query(SupportSession).filter(
        SupportSession.customer_id == user.id,
        SupportSession.status == "active"
    ).first()
    
    if not session:
        session = SupportSession(customer_id=user.id, status="active")
        db.add(session)
        db.commit()
        db.refresh(session)
        
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                if payload.get("type") == "message":
                    text = payload.get("text", "").strip()
                    if text:
                        # Save to DB
                        msg = DBSupportMessage(
                            session_id=session.id,
                            sender_type="user",
                            sender_id=user.id,
                            message=text
                        )
                        db.add(msg)
                        db.commit()
                        db.refresh(msg)
                        
                        msg_data = {
                            "type": "message",
                            "id": msg.id,
                            "session_id": session.id,
                            "sender_type": "user",
                            "sender_id": user.id,
                            "customer_id": user.id,
                            "customer_name": user.name or user.email,
                            "customer_email": user.email,
                            "text": text,
                            "created_at": msg.created_at.isoformat()
                        }
                        
                        # Send back to user as confirmation
                        await manager.send_to_user(user.id, msg_data)
                        
                        # Send to admins if online
                        if len(manager.active_admins) > 0:
                            await manager.send_to_admin(msg_data)
                        else:
                            # Fallback to email
                            send_offline_email(user, text)
                            
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect_user(user.id)

@router.websocket("/ws/admin")
async def websocket_admin(websocket: WebSocket, token: str = Query(...), db: Session = Depends(get_db)):
    user = get_user_from_token(token, db)
    if not user or not is_admin(user.role):
        await websocket.close(code=1008)
        return
        
    await manager.connect_admin(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                if payload.get("type") == "message":
                    text = payload.get("text", "").strip()
                    session_id = payload.get("session_id")
                    customer_id = payload.get("customer_id")
                    
                    if text and session_id and customer_id:
                        # Save to DB
                        msg = DBSupportMessage(
                            session_id=session_id,
                            sender_type="admin",
                            sender_id=user.id,
                            message=text
                        )
                        db.add(msg)
                        db.commit()
                        db.refresh(msg)
                        
                        msg_data = {
                            "type": "message",
                            "id": msg.id,
                            "session_id": session_id,
                            "sender_type": "admin",
                            "sender_id": user.id,
                            "customer_id": customer_id,
                            "text": text,
                            "created_at": msg.created_at.isoformat()
                        }
                        
                        # Send to specific user
                        await manager.send_to_user(customer_id, msg_data)
                        # Broadcast to other admins
                        await manager.send_to_admin(msg_data)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect_admin(websocket)

def send_offline_email(user: Customer, message: str):
    email_service = EmailService()
    if not email_service.is_configured():
        return
        
    subject = f"Nová zpráva z podpory od uživatele {user.email}"
    body = f"Dobrý den,\n\nUživatel zanechal zprávu přes formulář podpory v aplikaci.\n\nID uživatele: {user.id}\nEmail uživatele: {user.email}\n\nZpráva:\n{message}\n\nS pozdravem,\nSystém Správy vozidel"
    try:
        email_service.send_simple_email(to="info@toozservis.cz", subject=subject, body=body)
    except Exception as e:
        print(f"[SUPPORT] Chyba při odesílání emailu: {e}")

# REST endpoints for history
@router.get("/history")
def get_user_history(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(SupportSession).filter(
        SupportSession.customer_id == current_user.id,
        SupportSession.status == "active"
    ).first()
    
    if not session:
        return []
        
    messages = db.query(DBSupportMessage).filter(
        DBSupportMessage.session_id == session.id
    ).order_by(DBSupportMessage.created_at.asc()).all()
    
    return [
        {
            "id": m.id,
            "sender_type": m.sender_type,
            "text": m.message,
            "created_at": m.created_at.isoformat()
        } for m in messages
    ]

# Admin endpoints
@router.get("/admin/sessions")
def get_admin_sessions(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Přístup odepřen")
        
    sessions = db.query(SupportSession).filter(SupportSession.status == "active").all()
    result = []
    for s in sessions:
        customer = db.query(Customer).filter(Customer.id == s.customer_id).first()
        last_msg = db.query(DBSupportMessage).filter(DBSupportMessage.session_id == s.id).order_by(DBSupportMessage.created_at.desc()).first()
        
        result.append({
            "session_id": s.id,
            "customer_id": s.customer_id,
            "customer_name": customer.name if customer else "Neznámý",
            "customer_email": customer.email if customer else "Neznámý",
            "created_at": s.created_at.isoformat(),
            "last_message": last_msg.message if last_msg else "",
            "last_message_time": last_msg.created_at.isoformat() if last_msg else s.created_at.isoformat(),
            "is_online": s.customer_id in manager.active_users
        })
        
    # Sort by last message time descending
    result.sort(key=lambda x: x["last_message_time"], reverse=True)
    return result

@router.get("/admin/sessions/{session_id}/messages")
def get_admin_session_messages(session_id: int, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Přístup odepřen")
        
    messages = db.query(DBSupportMessage).filter(DBSupportMessage.session_id == session_id).order_by(DBSupportMessage.created_at.asc()).all()
    return [
        {
            "id": m.id,
            "sender_type": m.sender_type,
            "text": m.message,
            "created_at": m.created_at.isoformat()
        } for m in messages
    ]
