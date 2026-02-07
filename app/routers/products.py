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

# Demo products with size measurements (for DEMO_INVENTORY in main.py)
DEMO_PRODUCTS_WITH_MEASUREMENTS = {
    # Shirts
    "2608e0bf-7f8c-47bb-b6c5-84200460638b": {
        "id": UUID("2608e0bf-7f8c-47bb-b6c5-84200460638b"),
        "name": "Slim Fit Klasik Yaka Gömlek",
        "fit_type": "slim_fit",
        "fabric_composition": {"cotton": 100},
        "measurements": {
            "S": {"chest_width": 100, "length": 72, "shoulder_width": 42},
            "M": {"chest_width": 106, "length": 74, "shoulder_width": 44},
            "L": {"chest_width": 112, "length": 76, "shoulder_width": 46},
            "XL": {"chest_width": 118, "length": 78, "shoulder_width": 48},
            "XXL": {"chest_width": 124, "length": 80, "shoulder_width": 50}
        }
    },
    "c5118cf5-aa71-434e-8f2a-2b159c9d8bc7": {
        "id": UUID("c5118cf5-aa71-434e-8f2a-2b159c9d8bc7"),
        "name": "Regular Fit Oxford Gömlek",
        "fit_type": "regular_fit",
        "fabric_composition": {"cotton": 100},
        "measurements": {
            "S": {"chest_width": 104, "length": 72, "shoulder_width": 44},
            "M": {"chest_width": 110, "length": 74, "shoulder_width": 46},
            "L": {"chest_width": 116, "length": 76, "shoulder_width": 48},
            "XL": {"chest_width": 122, "length": 78, "shoulder_width": 50},
            "XXL": {"chest_width": 128, "length": 80, "shoulder_width": 52}
        }
    },
    "57337148-0b35-4141-84b3-bc9ea4f55aa0": {
        "id": UUID("57337148-0b35-4141-84b3-bc9ea4f55aa0"),
        "name": "Slim Fit Pamuklu Gömlek",
        "fit_type": "slim_fit",
        "fabric_composition": {"cotton": 97, "elastane": 3},
        "measurements": {
            "S": {"chest_width": 100, "length": 72, "shoulder_width": 42},
            "M": {"chest_width": 106, "length": 74, "shoulder_width": 44},
            "L": {"chest_width": 112, "length": 76, "shoulder_width": 46},
            "XL": {"chest_width": 118, "length": 78, "shoulder_width": 48},
            "XXL": {"chest_width": 124, "length": 80, "shoulder_width": 50}
        }
    },
    # Blazer Jacket
    "a1b2c3d4-e5f6-7890-abcd-ef1234567890": {
        "id": UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
        "name": "Kruvaze Lacivert Blazer Ceket",
        "fit_type": "slim_fit",
        "fabric_composition": {"wool": 55, "polyester": 45},
        "measurements": {
            "S": {"chest_width": 104, "length": 70, "shoulder_width": 44},
            "M": {"chest_width": 110, "length": 72, "shoulder_width": 46},
            "L": {"chest_width": 116, "length": 74, "shoulder_width": 48},
            "XL": {"chest_width": 122, "length": 76, "shoulder_width": 50},
            "XXL": {"chest_width": 128, "length": 78, "shoulder_width": 52}
        }
    },
    # Chino Pants
    "b2c3d4e5-f6a7-8901-bcde-f23456789012": {
        "id": UUID("b2c3d4e5-f6a7-8901-bcde-f23456789012"),
        "name": "Slim Fit Chino Pantolon",
        "fit_type": "slim_fit",
        "fabric_composition": {"cotton": 98, "elastane": 2},
        "measurements": {
            "S": {"chest_width": 84, "length": 102, "waist": 76},
            "M": {"chest_width": 88, "length": 104, "waist": 82},
            "L": {"chest_width": 92, "length": 106, "waist": 88},
            "XL": {"chest_width": 96, "length": 108, "waist": 94},
            "XXL": {"chest_width": 100, "length": 110, "waist": 100}
        }
    },
    # Wool Pants
    "c3d4e5f6-a7b8-9012-cdef-345678901234": {
        "id": UUID("c3d4e5f6-a7b8-9012-cdef-345678901234"),
        "name": "Klasik Kesim Yün Pantolon",
        "fit_type": "regular_fit",
        "fabric_composition": {"wool": 70, "polyester": 30},
        "measurements": {
            "S": {"chest_width": 88, "length": 102, "waist": 78},
            "M": {"chest_width": 92, "length": 104, "waist": 84},
            "L": {"chest_width": 96, "length": 106, "waist": 90},
            "XL": {"chest_width": 100, "length": 108, "waist": 96},
            "XXL": {"chest_width": 104, "length": 110, "waist": 102}
        }
    }
}


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
    Helper function to get product by ID (sync, in-memory only).
    Checks both ingested products and demo products.
    """
    if product_id in _products_store:
        return _products_store[product_id]
    product_id_str = str(product_id)
    if product_id_str in DEMO_PRODUCTS_WITH_MEASUREMENTS:
        return DEMO_PRODUCTS_WITH_MEASUREMENTS[product_id_str]
    return None


async def get_product_by_id_from_db(product_id: UUID) -> dict:
    """
    Fetch product from Supabase DB by ID. Returns a dict with measurements
    (falling back to category-based defaults if the product has none).
    """
    from app.models.database import get_session_factory, Product as DBProduct
    from sqlalchemy import select as sa_select

    # Lazy import to avoid circular deps
    from app.main import _guess_category, _get_default_measurements, _extract_brand_from_url

    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = sa_select(DBProduct).where(DBProduct.id == str(product_id))
        result = await session.execute(stmt)
        p = result.scalars().first()

    if not p:
        return None

    category = p.category or _guess_category(p.name)
    measurements = p.measurements or _get_default_measurements(category)
    if p.fit_type:
        fit_type = p.fit_type
    elif category in ("palto", "mont", "kaban", "parka", "pardösü"):
        fit_type = "loose_fit"
    else:
        fit_type = "regular_fit"
    fabric = p.fabric_composition or {"cotton": 100}

    return {
        "id": str(p.id),
        "name": p.name,
        "measurements": measurements,
        "fit_type": fit_type,
        "fabric_composition": fabric,
        "brand": p.brand or _extract_brand_from_url(p.url),
    }

