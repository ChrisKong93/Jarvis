import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from backend.database import ChatSession, get_db_session


@dataclass
class Session:
    session_id: str
    messages: List[Dict]
    created_at: datetime
    last_active: datetime


class SessionManager:
    def __init__(self, max_sessions: int = 100, session_timeout_days: int = 30):
        self.max_sessions = max_sessions
        self.session_timeout_days = session_timeout_days

    def _row_to_session(self, row: ChatSession) -> Session:
        return Session(
            session_id=row.session_id,
            messages=json.loads(row.messages_json or "[]"),
            created_at=row.created_at,
            last_active=row.last_active,
        )

    def create_session(self, session_id: Optional[str] = None) -> str:
        db = get_db_session()
        try:
            if not session_id:
                session_id = str(uuid.uuid4())

            row = ChatSession(
                session_id=session_id,
                messages_json="[]",
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            return session_id
        finally:
            db.close()

    def get_session(self, session_id: str) -> Optional[Session]:
        db = get_db_session()
        try:
            row = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            if not row:
                return None

            row.last_active = datetime.utcnow()
            db.commit()
            return self._row_to_session(row)
        finally:
            db.close()

    def update_session_messages(self, session_id: str, messages: List[Dict]) -> bool:
        db = get_db_session()
        try:
            row = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            if not row:
                return False

            row.messages_json = json.dumps(messages, ensure_ascii=False)
            row.last_active = datetime.utcnow()
            db.commit()
            return True
        finally:
            db.close()

    def update_session_title(self, session_id: str, title: str) -> bool:
        db = get_db_session()
        try:
            row = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            if not row:
                return False
            if title:
                row.title = title[:200]
                db.commit()
            return True
        finally:
            db.close()

    def delete_session(self, session_id: str) -> bool:
        db = get_db_session()
        try:
            row = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True
        finally:
            db.close()

    def list_sessions(self) -> List[Dict]:
        db = get_db_session()
        try:
            rows = (
                db.query(ChatSession)
                .order_by(ChatSession.last_active.desc())
                .limit(self.max_sessions)
                .all()
            )

            result = []
            for row in rows:
                messages = json.loads(row.messages_json or "[]")
                preview = ""
                if messages:
                    last_message = messages[-1]
                    content = last_message.get("content", "")
                    preview = content[:50]
                    if len(content) > 50:
                        preview += "..."

                result.append({
                    "session_id": row.session_id,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                    "last_active": row.last_active.isoformat() if row.last_active else "",
                    "message_count": len(messages),
                    "preview": row.title if row.title and row.title != "新会话" else (preview or "新会话"),
                })

            return result
        finally:
            db.close()

    def get_sessions_count(self) -> int:
        db = get_db_session()
        try:
            return db.query(ChatSession).count()
        finally:
            db.close()

    def cleanup_expired_sessions(self):
        db = get_db_session()
        try:
            from datetime import timedelta

            cutoff = datetime.utcnow() - timedelta(days=self.session_timeout_days)
            expired = db.query(ChatSession).filter(ChatSession.last_active < cutoff).all()
            for row in expired:
                db.delete(row)
            db.commit()
            return len(expired)
        finally:
            db.close()


session_manager = SessionManager()
