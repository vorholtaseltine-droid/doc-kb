# Auth Module Documentation

This document details the authentication mechanism in the auth module, covering login flow, JWT authentication, session management, and permission checking.

## How Auth Module Authenticates

### 1. Login Flow (Login → Verify Credentials → Issue JWT + Server Session)

#### 1.1 User Login
- Users submit username and password in a login form
- System verifies user existence (by querying user database)
- Password hash verification (using bcrypt for secure hashing)

#### 1.2 Credential Verification
- Check if the username exists
- Verify password hash matches
- Check user account status (active, locked, expired, etc.)
- Validate IP address and user agent (optional security check)

#### 1.3 Issue JWT Token + Server Session
- Issue a JWT token (containing user_id, username, expiration time, etc.)
- Create a server-side session (session_id) stored in Redis
- Associate session_id with user_id
- Set cookie (session_id) to client

### 2. JWT Authentication (Authorization: Bearer <token>)

#### 2.1 Token Extraction
- Extract JWT token from request header `Authorization: Bearer <token>`
- Or get session_id from cookie

#### 2.2 Token Verification
- Use HMAC-SHA256 to verify token signature (using secret from environment variable)
- Check if token is expired (verify `exp` field)
- Validate token issuer and audience (optional)

#### 2.3 Get Current User
- After verification, extract `user_id` from token
- Get user information via user_id
- Attach user information to request object

### 3. Session Authentication (session cookie)

#### 3.1 Session Creation
- Create session on successful login
- Use `secrets.token_urlsafe()` to generate secure session_id
- Set session_id as cookie
- Store session_id in Redis, containing user_id, expiration time, and additional data

#### 3.2 Session Validation
- Read session_id from cookie
- Verify if session_id exists in Redis
- Check if session has expired
- Return user_id if session is valid

### 4. Permission Checking (get_current_user)

#### 4.1 User Information Retrieval
- Get current user via `get_current_user()` function
- This function first checks JWT, then session

#### 4.2 Permission Checking
- Check user role and permissions to access resources
- Support Role-Based Access Control (RBAC)
- Support Policy-Based Access Control (PBAC)

### 5. Token Refresh & Revocation (revoke_session)

#### 5.1 Token Refresh
- Refresh JWT token when it's about to expire
- Issue new JWT token
- Retain existing server session

#### 5.2 Session Revocation
- Provide logout functionality to delete session
- Invalidate token
- Clear cookie

## Key Code Paths

### src/auth/jwt.py

#### create_jwt(payload, secret, expires_in)
- Input:
  - `payload` (dict): User information containing payload
  - `secret` (str): HMAC key
  - `expires_in` (int): Expiration time (seconds)
- Output:
  - JWT token string
- Function:
  - Create a signed token using HS256 algorithm
  - Include user ID, username, expiration time, etc.

#### verify_jwt(token, secret)
- Input:
  - `token` (str): JWT token
  - `secret` (str): HMAC key
- Output:
  - `dict`: Decoded payload
- Exception:
  - `ValueError`: Raised when signature verification fails or token expires

### src/auth/session.py

#### create_session(user_id, ttl_seconds)
- Input:
  - `user_id` (str): User ID
  - `ttl_seconds` (int): TTL (seconds)
- Output:
  - `session_id` (str): Session ID
- Function:
  - Create new session
  - Store in memory (Redis or in-memory database)
  - Return session_id

#### validate_session(session_id)
- Input:
  - `session_id` (str): Session ID
- Output:
  - `user_id` (str or None): Return user_id if session is valid, otherwise None

#### revoke_session(session_id)
- Input:
  - `session_id` (str): Session ID
- Output:
  - `bool`: Return True if session is successfully revoked, otherwise False

### src/middleware/session.ts

#### sessionMiddleware(req, res, next)
- Input:
  - `req`: Express request object
  - `res`: Express response object
  - `next`: Next middleware function
- Function:
  - Get token from Authorization Bearer JWT or session_id cookie
  - Verify JWT signature with HMAC-SHA256
  - Otherwise fall back to session lookup placeholder
  - Attach req.user
  - Return 401 JSON when authentication fails

## Common Troubleshooting

### 1. Login Failure
- Check if username exists
- Verify password hash matches
- Check account status
- Ensure password has not expired

### 2. JWT Verification Failure
- Check if token signature is correct
- Verify token has not expired
- Check if secret matches
- Ensure token format is correct

### 3. Session Validation Failure
- Check if session_id exists
- Verify session has not expired
- Check Redis connection status
- Ensure session is stored correctly

### 4. Permission Denied
- Check user role
- Verify user has required permissions
- Check resource ownership
- Verify session status

## Code Examples

### Login Flow Example

```typescript
// POST /api/auth/login
app.post('/api/auth/login', async (req, res) => {
  const { username, password } = req.body;
  
  // Verify user credentials
  const user = await verifyCredentials(username, password);
  if (!user) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }
  
  // Issue JWT token
  const token = createJwt(
    { userId: user.id, username: user.username },
    process.env.JWT_SECRET,
    3600 // 1 hour expiration
  );
  
  // Create server session
  const sessionId = createSession(user.id, 1800); // 30 minutes expiration
  
  // Set cookie
  res.cookie('session_id', sessionId, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    maxAge: 30 * 60 * 1000
  });
  
  res.json({ token, sessionId });
});
```

### API Protection Example

```typescript
// Protect route middleware
app.use('/api/protected', sessionMiddleware, (req, res) => {
  const user = getCurrentUser(req);
  if (!user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  
  // Check permissions
  if (!user.hasPermission('read:data')) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  
  res.json({ message: 'Access granted', user });
});
```

## Security Considerations

### 1. JWT Security
- Use secure HMAC key
- Rotate key periodically
- Check token expiration time
- Use cryptographically secure random number generator

### 2. Session Security
- Use secure session_id generation
- Implement session expiration and revocation
- Clear cookie (on logout)
- Use secure flags (only over HTTPS)

### 3. Credential Storage
- Use strong hash algorithms to store passwords
- Avoid logging credentials
- Use secure password verification

## Monitoring and Logging

### 1. Login Attempts
- Log successful and failed login attempts
- Record IP address and user agent
- Detect abnormal login patterns

### 2. Token Activity
- Log token verification
- Detect token replay attacks
- Log token revocation

### 3. Session Activity
- Log session creation and destruction
- Detect abnormal session patterns
- Log session expiration events

## Future Extensions

### 1. Multi-Factor Authentication
- Implement TOTP-based second factor authentication
- Support SMS or email verification codes

### 2. Role Management
- Implement fine-grained permission control
- Support permission inheritance

### 3. Audit Logging
- Record all authentication-related operations
- Implement audit log queries

### 4. Session Sharing
- Support login across devices
- Implement session synchronization

## Glossary

- **JWT**: JSON Web Token, a standard token format based on JSON
- **HMAC**: Hash-based Message Authentication Code, a hash-based message authentication code
- **RBAC**: Role-based Access Control, access control based on roles
- **PBAC**: Policy-based Access Control, access control based on policies
- **TOTP**: Time-based One-Time Password, a time-based single-use password
- **API**: Application Programming Interface, an interface for application programming
- **CORS**: Cross-Origin Resource Sharing, cross-origin resource sharing

These terms and concepts ensure the security and reliability of the auth module. Regular review and updates to these documents ensure system security and performance.