// session.ts - TypeScript middleware for JWT/session authentication

import crypto from 'node:crypto';

// Environment variable for JWT secret
const JWT_SECRET = process.env.JWT_SECRET || 'default-secret-key';

// Verify JWT token signature and validate
export function verifyJwt(token: string, secret: string): Record<string, any> | null {
  try {
    const [headerB64, payloadB64, signatureB64] = token.split('.');
    if (!headerB64 || !payloadB64 || !signatureB64) return null;

    const signingInput = `${headerB64}.${payloadB64}`;
    const expectedSignature = crypto
      .createHmac('sha256', secret)
      .update(signingInput)
      .digest('base64url');

    if (signatureB64 !== expectedSignature) return null;

    const payload = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'));

    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;

    return payload;
  } catch (error) {
    return null;
  }
}

// Express-style middleware for authentication
export function sessionMiddleware(req: any, res: any, next: any) {
  // Check for Bearer token in Authorization header
  let token = null;
  const authHeader = req.headers.authorization || '';
  if (authHeader.startsWith('Bearer ')) {
    token = authHeader.substring(7);
  }

  // Fall back to session_id cookie if no token
  if (!token && req.cookies?.session_id) {
    token = req.cookies.session_id;
  }

  // Verify JWT token
  if (token) {
    const payload = verifyJwt(token, JWT_SECRET);
    if (payload?.sub) {
      req.user = { userId: payload.sub, ...payload };
      return next();
    }
  }

  // Placeholder for session lookup (Redis/Memory)
  // This would typically query your session store
  // For this demo, we'll try a session ID from cookie
  if (req.cookies?.session_id) {
    const sessionId = req.cookies.session_id;
    // In a real implementation, you'd validate against your session store
    // For now, we'll assume it's valid if it exists in the cookie
    req.user = { userId: sessionId, sessionId };
    return next();
  }

  // Authentication failed
  res.status(401).json({
    error: 'Authentication required',
    message: 'Valid JWT token or session cookie required'
  });
}