"""
Products Router - Handles product ingestion from brands.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict
from uuid import UUID, uuid4

from app.models.schemas import (
    ProductIngestRequest, ProductIngestResponse
)
from app.models.database import Product, get_db
from app.middleware.auth import get_current_tenant

router = APIRouter(prefix="/api/v1", tags=["Products"])

# In-memory store for demo (replace with database in production)
_products_store: Dict[UUID, dict] = {}


@router.post(
    "/ingest-product",
    response_model=ProductIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Product Data",
    description="Push product measurement data to the FitEngine system."
)
async def ingest_product(
    request: ProductIngestRequest,
    tenant: dict = Depends(get_current_tenant)
):
    """
    Ingest a new product with its measurement specifications.
    
    This endpoint allows brands to push their product catalog data,
    including size measurements for accurate recommendations.
    
    **Required headers:**
    - `X-API-Key`: Your tenant API key
    
    **Measurements structure:**
    Each size should include measurements in cm:
    - `chest_width`: Garment chest width (required)
    - `length`: Garment length (required)
    - `waist`: Waist width (optional)
    - `hip`: Hip width (optional)
    - `sleeve_length`: Sleeve length (optional)
    - `shoulder_width`: Shoulder width (optional)
    """
    tenant_id = tenant["tenant_id"]
    product_id = uuid4()
    
    # Store product data
    product_data = {
        "id": product_id,
        "tenant_id": tenant_id,
        "sku": request.sku,
        "name": request.name,
        "fit_type": request.fit_type.value,
        "fabric_composition": request.fabric_composition,
        "measurements": {
            size: measurements.model_dump()
            for size, measurements in request.measurements.items()
        }
    }
    
    _products_store[product_id] = product_data
    
    return ProductIngestResponse(
        product_id=product_id,
        sku=request.sku,
        message="Product ingested successfully",
        sizes_count=len(request.measurements)
    )


@router.get(
    "/products/{product_id}",
    summary="Get Product",
    description="Retrieve product details by ID."
)
async def get_product(
    product_id: UUID,
    tenant: dict = Depends(get_current_tenant)
):
    """
    Get product details including measurements.
    
    **Required headers:**
    - `X-API-Key`: Your tenant API key
    """
    if product_id not in _products_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found"
        )
    
    product = _products_store[product_id]
    
    # Verify tenant ownership
    if product["tenant_id"] != tenant["tenant_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this product"
        )
    
    return product


@router.get(
    "/products",
    summary="List Products",
    description="List all products for the authenticated tenant."
)
async def list_products(
    tenant: dict = Depends(get_current_tenant)
):
    """
    List all products belonging to the authenticated tenant.
    
    **Required headers:**
    - `X-API-Key`: Your tenant API key
    """
    tenant_id = tenant["tenant_id"]
    
    products = [
        {
            "id": p["id"],
            "sku": p["sku"],
            "name": p["name"],
            "fit_type": p["fit_type"],
            "sizes_count": len(p["measurements"])
        }
        for p in _products_store.values()
        if p["tenant_id"] == tenant_id
    ]
    
    return {"products": products, "total": len(products)}


def get_product_by_id(product_id: UUID) -> dict:
    """
    Helper function to get product by ID.
    Used by other routers.
    """
    if product_id not in _products_store:
        return None
    return _products_store[product_id]
