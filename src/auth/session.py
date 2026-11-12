#!/usr/bin/env python3
"""
In-memory session store with expiry support.

Provides functions to create, validate, and revoke user sessions.
"""

import secrets
import time
from typing import Dict, Optional

# In-memory session store: session_id -> {user_id, created_at, expires_at}
_sessions: Dict[str, dict] = {}


def create_session(user_id: str, ttl_seconds: int = 1800) -> str:
    """
    Create a new session for a user.
    
    Args:
        user_id: User ID to associate with the session
        ttl_seconds: Time-to-live in seconds (default: 30 minutes)
    
    Returns:
        Session ID
    """
    session_id = secrets.token_urlsafe(32)
    current_time = time.time()
    
    _sessions[session_id] = {
        'user_id': user_id,
        'created_at': current_time,
        'expires_at': current_time + ttl_seconds
    }
    
    # Clean up expired sessions periodically
    _cleanup_expired_sessions()
    
    return session_id


def validate_session(session_id: str) -> Optional[str]:
    """
    Validate a session and return the user ID if valid.
    
    Args:
        session_id: Session ID to validate
    
    Returns:
        User ID if session is valid, None otherwise
    """
    if session_id not in _sessions:
        return None
    
    session = _sessions[session_id]
    current_time = time.time()
    
    # Check if session has expired
    if current_time > session['expires_at']:
        # Remove expired session
        del _sessions[session_id]
        return None
    
    return session['user_id']


def revoke_session(session_id: str) -> bool:
    """
    Revoke a session.
    
    Args:
        session_id: Session ID to revoke
    
    Returns:
        True if session was revoked, False if session_id was not found
    """
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False


def _cleanup_expired_sessions() -> None:
    """
    Remove expired sessions from the store.
    """
    current_time = time.time()
    expired_session_ids = []
    
    for session_id, session in _sessions.items():
        if current_time > session['expires_at']:
            expired_session_ids.append(session_id)
    
    for session_id in expired_session_ids:
        del _sessions[session_id]


def get_session_info(session_id: str) -> Optional[dict]:
    """
    Get information about a session (for debugging/monitoring).
    
    Args:
        session_id: Session ID to look up
    
    Returns:
        Session info dict if found, None otherwise
    """
    if session_id in _sessions:
        return _sessions[session_id].copy()
    return None


def get_all_sessions() -> Dict[str, dict]:
    """
    Get all sessions (for debugging/monitoring).
    
    Returns:
        Copy of all sessions
    """
    return _sessions.copy()


if __name__ == "__main__":
    # Demo usage
    print("Creating session for user 'demo_user'...")
    session_id = create_session('demo_user', 60)  # 1 minute for demo
    print(f"Session ID: {session_id}")
    
    print("\nValidating session...")
    user_id = validate_session(session_id)
    if user_id:
        print(f"Session valid for user: {user_id}")
    else:
        print("Session invalid or expired")
    
    print("\nRevoking session...")
    if revoke_session(session_id):
        print("Session revoked successfully")
    
    print("\nAttempting to validate revoked session...")
    user_id = validate_session(session_id)
    if user_id:
        print(f"ERROR: Session should be invalid but returned user: {user_id}")
    else:
        print("Session correctly invalidated")
    
    print("\nDemo complete. Current sessions:", len(get_all_sessions()))