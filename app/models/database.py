"""
SQLAlchemy database models for FitEngine API.
"""
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Integer, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.config import settings

# Database setup - lazy initialization to avoid import-time errors
_engine = None
_async_session = None

Base = declarative_base()


def get_engine():
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        _engine = create_async_engine(settings.database_url, echo=not settings.is_production)
    return _engine


def get_session_factory():
    """Get or create the async session factory."""
    global _async_session
    if _async_session is None:
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import sessionmaker
        _async_session = sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session


async def get_db():
    """Dependency for getting async database sessions."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


class Tenant(Base):
    """
    Brand/Client information.
    Each tenant has unique API credentials.
    """
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    api_secret = Column(String(128), nullable=False)
    contact_email = Column(String(255))
    website_url = Column(String(500))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    products = relationship("Product", back_populates="tenant", cascade="all, delete-orphan")
    size_charts = relationship("SizeChart", back_populates="tenant", cascade="all, delete-orphan")


class Product(Base):
    """
    Product with detailed measurement specifications.
    Pushed by brands via the ingest endpoint.
    """
    __tablename__ = "products"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    sku = Column(String(100), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    fit_type = Column(String(50), nullable=False)  # slim_fit, regular_fit, loose_fit, oversized
    fabric_composition = Column(JSONB, nullable=False)  # {"cotton": 95, "elastane": 5}
    measurements = Column(JSONB, nullable=False)  # {"S": {"chest": 104, ...}, "M": {...}}
    category = Column(String(100))  # shirt, pants, jacket, etc.
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="products")
    widget_events = relationship("WidgetEvent", back_populates="product", cascade="all, delete-orphan")
    
    # Unique constraint: SKU must be unique per tenant
    __table_args__ = (
        # UniqueConstraint would be added here if needed
    )


class SizeChart(Base):
    """
    Base size guides for brands.
    Used as fallback when specific product measurements aren't available.
    """
    __tablename__ = "size_charts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # e.g., "Men's Shirts", "Women's Dresses"
    category = Column(String(100), nullable=False)  # shirt, pants, dress, etc.
    size_code = Column(String(10), nullable=False)  # S, M, L, XL
    measurements = Column(JSONB, nullable=False)  # {"chest_min": 96, "chest_max": 102, ...}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="size_charts")


class WidgetEvent(Base):
    """
    Analytics for tracking widget interactions.
    Records every size check request for analysis.
    """
    __tablename__ = "widget_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Denormalized for fast queries
    recommended_size = Column(String(10), nullable=False)
    confidence_score = Column(Integer, nullable=False)
    user_input = Column(JSONB, nullable=False)  # {"height": 180, "weight": 85, ...}
    user_agent = Column(Text)  # Browser/device info
    referrer_url = Column(String(500))  # Page where widget was used
    session_id = Column(String(100))  # For tracking unique users
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    product = relationship("Product", back_populates="widget_events")


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
