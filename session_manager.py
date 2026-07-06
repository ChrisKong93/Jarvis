import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class Session:
    session_id: str
    messages: List[Dict]
    created_at: datetime
    last_active: datetime

class SessionManager:
    def __init__(self, max_sessions: int = 100, session_timeout: int = 3600):
        self.sessions: Dict[str, Session] = {}
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout

    def create_session(self) -> str:
        self._cleanup_expired_sessions()
        
        if len(self.sessions) >= self.max_sessions:
            oldest_session = min(self.sessions.values(), key=lambda s: s.last_active)
            del self.sessions[oldest_session.session_id]
        
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = Session(
            session_id=session_id,
            messages=[],
            created_at=datetime.now(),
            last_active=datetime.now()
        )
        return session_id

    def get_session(self, session_id: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session:
            session.last_active = datetime.now()
        return session

    def update_session_messages(self, session_id: str, messages: List[Dict]) -> bool:
        session = self.sessions.get(session_id)
        if session:
            session.messages = messages
            session.last_active = datetime.now()
            return True
        return False

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def _cleanup_expired_sessions(self):
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if (now - session.last_active).total_seconds() > self.session_timeout
        ]
        for sid in expired_sessions:
            del self.sessions[sid]

    def get_sessions_count(self) -> int:
        self._cleanup_expired_sessions()
        return len(self.sessions)

session_manager = SessionManager()