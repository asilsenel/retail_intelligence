"""
API Key Authentication Middleware.
Validates tenant API keys for protected endpoints.
"""
from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from typing import Optional
from uuid import UUID

# API Key header name
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthMiddleware:
    """
    Handles API key validation for tenant authentication.
    """
    
    def __init__(self):
        # In-memory cache for faster lookups (in production, use Redis)
        self._cache: dict = {}
    
    async def validate_api_key(
        self,
        api_key: str = Security(API_KEY_HEADER),
        db = None
    ) -> Optional[dict]:
        """
        Validate API key and return tenant info.
        
        Args:
            api_key: API key from X-API-Key header
            db: Database session
            
        Returns:
            Tenant info dict if valid
            
        Raises:
            HTTPException: If API key is invalid or missing
        """
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="Missing API key. Include X-API-Key header."
            )
        
        # Check cache first
        if api_key in self._cache:
            return self._cache[api_key]
        
        # For demo/testing, accept a test key
        if api_key == "test-api-key":
            tenant_info = {
                "tenant_id": UUID("00000000-0000-0000-0000-000000000001"),
                "name": "Test Tenant",
                "is_test": True
            }
            self._cache[api_key] = tenant_info
            return tenant_info
        
        # In production, validate against database
        if db is not None:
            from app.models.database import Tenant
            result = await db.execute(
                select(Tenant).where(
                    Tenant.api_key == api_key,
                    Tenant.is_active == True
                )
            )
            tenant = result.scalar_one_or_none()
            
            if tenant:
                tenant_info = {
                    "tenant_id": tenant.id,
                    "name": tenant.name,
                    "is_test": False
                }
                self._cache[api_key] = tenant_info
                return tenant_info
        
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    def clear_cache(self, api_key: Optional[str] = None):
        """Clear cached API key info."""
        if api_key:
            self._cache.pop(api_key, None)
        else:
            self._cache.clear()


# Singleton instance
auth_middleware = AuthMiddleware()


async def get_current_tenant(
    api_key: str = Security(API_KEY_HEADER)
) -> dict:
    """
    Dependency to get current tenant from API key.
    For use in route handlers.
    """
    return await auth_middleware.validate_api_key(api_key)
