from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional, Dict
import os
import httpx
from pydantic import BaseModel


# Security
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


class OAuthConfig(BaseModel):
    """OAuth configuration for different providers."""
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    frontend_url: str = "http://localhost:3000"


oauth_config = OAuthConfig(
    google_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
    google_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
    github_client_id=os.getenv("GITHUB_OAUTH_CLIENT_ID"),
    github_client_secret=os.getenv("GITHUB_OAUTH_CLIENT_SECRET"),
    frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000")
)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict


class OAuthUser(BaseModel):
    """OAuth user information."""
    id: str
    email: str
    name: str
    avatar_url: Optional[str] = None
    provider: str


def create_access_token(data: Dict) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Dict:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Get current user from JWT token."""
    token = credentials.credentials
    payload = verify_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return payload


class GoogleOAuth:
    """Google OAuth 2.0 handler."""
    
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    
    @staticmethod
    def get_authorization_url(redirect_uri: str) -> str:
        """Generate Google OAuth authorization URL."""
        if not oauth_config.google_client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth not configured"
            )
        
        params = {
            "client_id": oauth_config.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline"
        }
        
        import urllib.parse
        return f"{GoogleOAuth.AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    @staticmethod
    async def exchange_code_for_token(code: str, redirect_uri: str) -> Dict:
        """Exchange authorization code for access token."""
        if not oauth_config.google_client_id or not oauth_config.google_client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth not configured"
            )
        
        data = {
            "client_id": oauth_config.google_client_id,
            "client_secret": oauth_config.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(GoogleOAuth.TOKEN_URL, data=data)
            response.raise_for_status()
            return response.json()
    
    @staticmethod
    async def get_user_info(access_token: str) -> OAuthUser:
        """Get user information from Google."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GoogleOAuth.USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            user_data = response.json()
            
            return OAuthUser(
                id=user_data["id"],
                email=user_data["email"],
                name=user_data["name"],
                avatar_url=user_data.get("picture"),
                provider="google"
            )


class GitHubOAuth:
    """GitHub OAuth 2.0 handler."""
    
    AUTH_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_INFO_URL = "https://api.github.com/user"
    USER_EMAIL_URL = "https://api.github.com/user/emails"
    
    @staticmethod
    def get_authorization_url(redirect_uri: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        if not oauth_config.github_client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub OAuth not configured"
            )
        
        params = {
            "client_id": oauth_config.github_client_id,
            "redirect_uri": redirect_uri,
            "scope": "user:email read:user"
        }
        
        import urllib.parse
        return f"{GitHubOAuth.AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    @staticmethod
    async def exchange_code_for_token(code: str, redirect_uri: str) -> Dict:
        """Exchange authorization code for access token."""
        if not oauth_config.github_client_id or not oauth_config.github_client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub OAuth not configured"
            )
        
        data = {
            "client_id": oauth_config.github_client_id,
            "client_secret": oauth_config.github_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }
        
        headers = {
            "Accept": "application/json",
            "User-Agent": "Adra-AI"
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(GitHubOAuth.TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
            return response.json()
    
    @staticmethod
    async def get_user_info(access_token: str) -> OAuthUser:
        """Get user information from GitHub."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Adra-AI"
        }
        async with httpx.AsyncClient() as client:
            # Get basic user info
            response = await client.get(
                GitHubOAuth.USER_INFO_URL,
                headers=headers
            )
            response.raise_for_status()
            user_data = response.json()
            
            # Get primary email
            email_response = await client.get(
                GitHubOAuth.USER_EMAIL_URL,
                headers=headers
            )
            email_response.raise_for_status()
            emails = email_response.json()
            
            primary_email = next((e["email"] for e in emails if e["primary"]), user_data.get("email"))
            
            return OAuthUser(
                id=str(user_data["id"]),
                email=primary_email or f"{user_data['login']}@users.noreply.github.com",
                name=user_data["name"] or user_data["login"],
                avatar_url=user_data.get("avatar_url"),
                provider="github"
            )


async def oauth_callback(provider: str, code: str, redirect_uri: str) -> Token:
    """Handle OAuth callback for both Google and GitHub."""
    if provider == "google":
        oauth_handler = GoogleOAuth
    elif provider == "github":
        oauth_handler = GitHubOAuth
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth provider"
        )
    
    try:
        # Exchange code for token
        token_data = await oauth_handler.exchange_code_for_token(code, redirect_uri)
        access_token = token_data.get("access_token")
        
        # Get user information
        user = await oauth_handler.get_user_info(access_token)
        
        # Create JWT token for our application
        jwt_token = create_access_token(
            data={
                "sub": user.id,
                "email": user.email,
                "name": user.name,
                "provider": user.provider
            }
        )
        
        return Token(
            access_token=jwt_token,
            user={
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "avatar_url": user.avatar_url,
                "provider": user.provider
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth callback failed: {str(e)}"
        )
