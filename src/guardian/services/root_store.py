from __future__ import annotations

import aiosqlite
import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass

from .base import BaseStore


@dataclass(frozen=True)
class RootUser:
    user_id: int
    added_by: int
    added_at: datetime.datetime


@dataclass(frozen=True)
class RootRequest:
    request_id: int
    target_id: int
    requester_id: int
    requested_at: datetime.datetime
    approved_by: Optional[int]
    approved_at: Optional[datetime.datetime]
    status: str  # "pending", "approved", "rejected"


class RootStore(BaseStore):
    """Persistent storage for bot root operators and pending requests."""
    
    async def initialize(self) -> None:
        """Create database tables for root users and requests."""
        await self._execute("""
            CREATE TABLE IF NOT EXISTS root_users (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                added_at TEXT NOT NULL
            )
        """)
        
        await self._execute("""
            CREATE TABLE IF NOT EXISTS root_pending (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL,
                requester_id INTEGER NOT NULL,
                requested_at TEXT NOT NULL,
                approved_by INTEGER,
                approved_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        
        await self._execute("""
            CREATE INDEX IF NOT EXISTS idx_root_users_user_id ON root_users(user_id)
        """)
        
        await self._execute("""
            CREATE INDEX IF NOT EXISTS idx_root_pending_status ON root_pending(status)
        """)
    
    async def is_root(self, user_id: int) -> bool:
        """Check if user is a root operator."""
        row = await self._fetchone(
            "SELECT 1 FROM root_users WHERE user_id = ?",
            (user_id,)
        )
        return row is not None
    
    async def request_add_root(self, target_id: int, requester_id: int) -> int:
        """Create a request to add a new root operator."""
        # Check if target is already a root
        if await self.is_root(target_id):
            raise ValueError("User is already a root operator")
        
        # Check if there's already a pending request
        existing = await self._fetchone(
            "SELECT request_id FROM root_pending WHERE target_id = ? AND status = 'pending'",
            (target_id,)
        )
        if existing:
            raise ValueError("Pending request already exists for this user")
        
        # Create new request
        now = datetime.datetime.utcnow().isoformat()
        cursor = await self._execute(
            """INSERT INTO root_pending (target_id, requester_id, requested_at, status)
               VALUES (?, ?, ?, 'pending')""",
            (target_id, requester_id, now)
        )
        return cursor.lastrowid
    
    async def approve_request(self, request_id: int, approver_id: int) -> bool:
        """Approve a pending root request and add user to root_users."""
        # Get request details
        request = await self._fetchone(
            """SELECT target_id, requester_id, status FROM root_pending 
               WHERE request_id = ?""",
            (request_id,)
        )
        
        if not request:
            raise ValueError("Request not found")
        
        target_id, requester_id, status = request
        
        if status != "pending":
            raise ValueError(f"Request is not pending (status: {status})")
        
        if requester_id == approver_id:
            raise ValueError("Cannot approve your own request")
        
        # Check if target is already root (double check)
        if await self.is_root(target_id):
            # Mark request as rejected since user is already root
            await self._execute(
                "UPDATE root_pending SET status = 'rejected', approved_by = ?, approved_at = ? WHERE request_id = ?",
                (approver_id, datetime.datetime.utcnow().isoformat(), request_id)
            )
            return False
        
        # Add to root_users
        now = datetime.datetime.utcnow().isoformat()
        await self._execute(
            "INSERT INTO root_users (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (target_id, approver_id, now)
        )
        
        # Update request
        await self._execute(
            "UPDATE root_pending SET status = 'approved', approved_by = ?, approved_at = ? WHERE request_id = ?",
            (approver_id, now, request_id)
        )
        
        return True
    
    async def reject_request(self, request_id: int, approver_id: int) -> bool:
        """Reject a pending root request."""
        request = await self._fetchone(
            "SELECT status FROM root_pending WHERE request_id = ?",
            (request_id,)
        )
        
        if not request:
            raise ValueError("Request not found")
        
        status = request[0]
        
        if status != "pending":
            raise ValueError(f"Request is not pending (status: {status})")
        
        # Update request
        await self._execute(
            "UPDATE root_pending SET status = 'rejected', approved_by = ?, approved_at = ? WHERE request_id = ?",
            (approver_id, datetime.datetime.utcnow().isoformat(), request_id)
        )
        
        return True
    
    async def remove_root(self, user_id: int) -> bool:
        """Remove a user from root operators."""
        # Cannot remove if not a root
        if not await self.is_root(user_id):
            return False
        
        await self._execute(
            "DELETE FROM root_users WHERE user_id = ?",
            (user_id,)
        )
        
        return True
    
    async def list_roots(self) -> List[RootUser]:
        """List all root operators."""
        rows = await self._fetchall(
            "SELECT user_id, added_by, added_at FROM root_users ORDER BY added_at"
        )
        
        return [
            RootUser(
                user_id=row[0],
                added_by=row[1],
                added_at=datetime.datetime.fromisoformat(row[2])
            )
            for row in rows
        ]
    
    async def list_pending_requests(self) -> List[RootRequest]:
        """List all pending root requests."""
        rows = await self._fetchall(
            """SELECT request_id, target_id, requester_id, requested_at, 
                      approved_by, approved_at, status 
               FROM root_pending 
               WHERE status = 'pending' 
               ORDER BY requested_at"""
        )
        
        return [
            RootRequest(
                request_id=row[0],
                target_id=row[1],
                requester_id=row[2],
                requested_at=datetime.datetime.fromisoformat(row[3]),
                approved_by=row[4],
                approved_at=datetime.datetime.fromisoformat(row[5]) if row[5] else None,
                status=row[6]
            )
            for row in rows
        ]
    
    async def get_request(self, request_id: int) -> Optional[RootRequest]:
        """Get a specific root request."""
        row = await self._fetchone(
            """SELECT request_id, target_id, requester_id, requested_at, 
                      approved_by, approved_at, status 
               FROM root_pending 
               WHERE request_id = ?""",
            (request_id,)
        )
        
        if not row:
            return None
        
        return RootRequest(
            request_id=row[0],
            target_id=row[1],
            requester_id=row[2],
            requested_at=datetime.datetime.fromisoformat(row[3]),
            approved_by=row[4],
            approved_at=datetime.datetime.fromisoformat(row[5]) if row[5] else None,
            status=row[6]
        )
