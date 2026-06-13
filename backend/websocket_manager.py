from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json
import asyncio
from datetime import datetime, timezone


class ConnectionManager:
    """WebSocket connection manager for real-time progress updates."""
    
    def __init__(self):
        # Active connections: {session_id: Set[WebSocket]}
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Session metadata: {session_id: {"user_id": str, "project_id": str, ...}}
        self.session_metadata: Dict[str, Dict] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str, user_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        
        self.active_connections[session_id].add(websocket)
        self.session_metadata[session_id] = {
            "user_id": user_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "connection_count": len(self.active_connections[session_id])
        }
        
        # Send connection confirmation
        await self.send_personal_message({
            "type": "connected",
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, websocket)
    
    def disconnect(self, websocket: WebSocket, session_id: str):
        """Remove a WebSocket connection."""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            
            # Clean up if no more connections for this session
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                if session_id in self.session_metadata:
                    del self.session_metadata[session_id]
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"Error sending message to WebSocket: {e}")
    
    async def broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast a message to all connections in a session."""
        if session_id not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        
        # Clean up disconnected connections
        for connection in disconnected:
            self.disconnect(connection, session_id)
    
    async def broadcast_progress(self, session_id: str, step: str, message: str, progress: float = None):
        """Send a progress update to the session."""
        update = {
            "type": "progress",
            "session_id": session_id,
            "step": step,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if progress is not None:
            update["progress"] = progress
        
        await self.broadcast_to_session(session_id, update)
    
    async def broadcast_error(self, session_id: str, error: str):
        """Send an error message to the session."""
        await self.broadcast_to_session(session_id, {
            "type": "error",
            "session_id": session_id,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def broadcast_complete(self, session_id: str, result: dict = None):
        """Send a completion message to the session."""
        message = {
            "type": "complete",
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if result:
            message["result"] = result
        
        await self.broadcast_to_session(session_id, message)
    
    async def broadcast_agent_update(self, session_id: str, agent_name: str, status: str, data: dict = None):
        """Send agent status update during execution."""
        update = {
            "type": "agent_update",
            "session_id": session_id,
            "agent": agent_name,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if data:
            update["data"] = data
        
        await self.broadcast_to_session(session_id, update)
    
    def get_connection_count(self, session_id: str) -> int:
        """Get the number of active connections for a session."""
        return len(self.active_connections.get(session_id, set()))
    
    def get_session_info(self, session_id: str) -> dict:
        """Get metadata for a session."""
        return self.session_metadata.get(session_id, {})
    
    def get_all_sessions(self) -> list:
        """Get all active session IDs."""
        return list(self.active_connections.keys())


# Global connection manager instance
manager = ConnectionManager()


class ProgressReporter:
    """Helper class for reporting progress during agent execution."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._steps_completed = 0
        self._total_steps = 0
    
    def set_total_steps(self, total: int):
        """Set the total number of steps for progress calculation."""
        self._total_steps = total
    
    async def start(self, message: str = "Starting task..."):
        """Report task start."""
        await manager.broadcast_progress(
            self.session_id,
            step="start",
            message=message,
            progress=0.0
        )
    
    async def step(self, step_name: str, message: str):
        """Report a step completion."""
        self._steps_completed += 1
        
        if self._total_steps > 0:
            progress = (self._steps_completed / self._total_steps) * 100
        else:
            progress = None
        
        await manager.broadcast_progress(
            self.session_id,
            step=step_name,
            message=message,
            progress=progress
        )
    
    async def update(self, step_name: str, message: str, progress: float = None):
        """Report a status update without incrementing step count."""
        await manager.broadcast_progress(
            self.session_id,
            step=step_name,
            message=message,
            progress=progress
        )
    
    async def complete(self, result: dict = None):
        """Report task completion."""
        await manager.broadcast_complete(self.session_id, result)
    
    async def error(self, error_message: str):
        """Report an error."""
        await manager.broadcast_error(self.session_id, error_message)
    
    async def agent_update(self, agent_name: str, status: str, data: dict = None):
        """Report agent status update."""
        await manager.broadcast_agent_update(self.session_id, agent_name, status, data)
