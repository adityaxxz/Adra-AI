from fastapi import HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Callable
import time


# Initialize rate limiter
# TEMPORARILY DISABLED FOR TESTING
# limiter = Limiter(key_func=get_remote_address)
limiter = None


# Rate limit decorators
def rate_limit(limit: str, key_func: Callable = get_remote_address):
    """Rate limit decorator using slowapi."""
    return limiter.limit(limit)(key_func=key_func)


# Rate limit configurations
RATE_LIMITS = {
    "auth": "5/minute",  # Auth endpoints: 5 requests per minute
    "generation": "2/hour",  # Generation endpoints: 2 per hour (expensive operations)
    "api": "60/minute",  # General API: 60 requests per minute
    "websocket": "10/minute",  # WebSocket connections: 10 per minute
}


# Custom rate limit exception handler
async def rate_limit_handler(request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": str(exc.retry_after) if hasattr(exc, 'retry_after') else "60"
        }
    )
