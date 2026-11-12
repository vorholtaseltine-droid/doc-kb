#!/usr/bin/env python3
"""
HS256 JWT implementation using standard library only.

Provides functions to create and verify JWT tokens using HMAC-SHA256.
"""

import base64
import hashlib
import hmac
import json
import time

# Base64 URL safe encoding without padding
def _b64url_encode(data: bytes) -> str:
    """Base64 URL safe encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data: str) -> bytes:
    """Base64 URL safe decode with padding."""
    # Add padding if necessary
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data.encode('ascii'))


def create_jwt(payload: dict, secret: str, expires_in: int = 3600) -> str:
    """
    Create an HS256 JWT token.
    
    Args:
        payload: Dictionary containing claims
        secret: Secret key for HMAC signature
        expires_in: Token expiration time in seconds (default: 1 hour)
    
    Returns:
        JWT token string
    """
    # Add standard claims
    payload['iat'] = int(time.time())
    payload['exp'] = payload['iat'] + expires_in
    payload['iss'] = 'auth-module'
    
    # Encode header
    header = {
        'alg': 'HS256',
        'typ': 'JWT'
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(',', ':')).encode())
    
    # Encode payload
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode())
    
    # Create signature
    signing_input = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        secret.encode(),
        signing_input.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = _b64url_encode(signature)
    
    # Combine to create token
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_jwt(token: str, secret: str) -> dict:
    """
    Verify an HS256 JWT token.
    
    Args:
        token: JWT token string
        secret: Secret key for HMAC signature verification
    
    Returns:
        Decoded payload dictionary
    
    Raises:
        ValueError: If token signature is invalid or token is expired
    """
    # Split token into parts
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    
    header_b64, payload_b64, signature_b64 = parts
    
    # Verify signature
    signing_input = f"{header_b64}.{payload_b64}"
    expected_signature = hmac.new(
        secret.encode(),
        signing_input.encode(),
        hashlib.sha256
    ).digest()
    expected_signature_b64 = _b64url_encode(expected_signature)
    
    if not hmac.compare_digest(signature_b64, expected_signature_b64):
        raise ValueError("Invalid token signature")
    
    # Decode payload
    payload = json.loads(_b64url_decode(payload_b64).decode())
    
    # Check expiration
    current_time = int(time.time())
    if payload.get('exp', 0) <= current_time:
        raise ValueError("Token has expired")
    
    # Check issuer
    if payload.get('iss') != 'auth-module':
        raise ValueError("Invalid token issuer")
    
    return payload


if __name__ == "__main__":
    # Demo usage
    secret = "demo-secret-key"
    
    print("Creating JWT token...")
    payload = {
        "sub": "user123",
        "name": "Demo User",
        "role": "admin"
    }
    
    token = create_jwt(payload, secret)
    print(f"Token: {token}")
    
    print("\nVerifying token...")
    try:
        decoded = verify_jwt(token, secret)
        print(f"Verified payload: {decoded}")
    except ValueError as e:
        print(f"Verification failed: {e}")
    
    # Test with invalid secret
    print("\nTesting with invalid secret...")
    try:
        verify_jwt(token, "wrong-secret")
        print("ERROR: Should have failed")
    except ValueError as e:
        print(f"Expected failure: {e}")