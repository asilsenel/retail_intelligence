"""
Recommendations Router - Size recommendation endpoint.
"""
from fastapi import APIRouter, HTTPException, status
from uuid import UUID
from datetime import datetime

from app.models.schemas import (
    RecommendRequest, RecommendResponse, FitType, BodyShape
)
from app.services.recommendation_engine import recommendation_engine
from app.routers.products import get_product_by_id

router = APIRouter(prefix="/api/v1", tags=["Recommendations"])


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Get Size Recommendation",
    description="Get an AI-powered size recommendation based on user measurements."
)
async def get_recommendation(request: RecommendRequest):
    """
    Generate a size recommendation for a specific product.
    
    **Algorithm Overview:**
    1. Estimate user body measurements from height, weight, BMI, and body shape
    2. Apply ease (bolluk payı) based on the garment's fit type
    3. Account for fabric stretch properties
    4. Compare with product sizes and find the best fit
    5. Return recommendation with confidence score and fit details
    
    **Ease Calculation:**
    - Garment must be larger than body for comfortable fit
    - Slim Fit: +2-3cm ease
    - Regular Fit: +4-6cm ease
    - Loose Fit: +8-12cm ease
    - Stretch fabrics reduce required ease
    
    **Body Shape Options:**
    - `athletic`: Broader shoulders, narrower waist
    - `average`: Standard proportions
    - `slim`: Lean build
    - `stocky`: Wider torso proportions
    - `plus_size`: More generous proportions
    
    **Fit Preference:**
    - `tighter`: Prefer closer-fitting sizes
    - `true_to_size`: Standard recommendation
    - `looser`: Prefer more relaxed fit
    """
    # Get product from store
    product = get_product_by_id(request.product_id)
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {request.product_id} not found. Please ingest the product first."
        )
    
    # Parse body shape
    body_shape = None
    if request.body_shape:
        body_shape = request.body_shape
    
    # Parse fit type
    try:
        fit_type = FitType(product["fit_type"])
    except ValueError:
        fit_type = FitType.REGULAR_FIT
    
    # Generate recommendation
    recommendation = recommendation_engine.recommend(
        user_height=request.user_height,
        user_weight=request.user_weight,
        product_measurements=product["measurements"],
        fit_type=fit_type,
        fabric_composition=product["fabric_composition"],
        body_shape=body_shape,
        age=request.age,
        preferred_fit=request.preferred_fit or "true_to_size"
    )
    
    return recommendation


@router.post(
    "/quick-recommend",
    response_model=RecommendResponse,
    summary="Quick Size Recommendation",
    description="Get a quick recommendation with inline product data (no prior ingestion needed)."
)
async def quick_recommend(
    user_height: float,
    user_weight: float,
    fit_type: str = "regular_fit",
    fabric_stretch: bool = False,
    size_s_chest: float = 104,
    size_m_chest: float = 110,
    size_l_chest: float = 116,
    size_xl_chest: float = 122,
    body_shape: str = None
):
    """
    Quick recommendation without prior product ingestion.
    
    Useful for testing or simple integrations where you just want
    to pass measurements directly.
    
    **Parameters:**
    - Chest measurements for each size (in cm)
    - `fabric_stretch`: If true, reduces required ease by 2cm
    """
    # Build measurements dict
    measurements = {
        "S": {"chest_width": size_s_chest, "length": 72},
        "M": {"chest_width": size_m_chest, "length": 74},
        "L": {"chest_width": size_l_chest, "length": 76},
        "XL": {"chest_width": size_xl_chest, "length": 78}
    }
    
    # Build fabric composition
    fabric_composition = {"cotton": 100}
    if fabric_stretch:
        fabric_composition = {"cotton": 95, "elastane": 5}
    
    # Parse body shape
    parsed_body_shape = None
    if body_shape:
        try:
            parsed_body_shape = BodyShape(body_shape)
        except ValueError:
            pass
    
    # Parse fit type
    try:
        parsed_fit_type = FitType(fit_type)
    except ValueError:
        parsed_fit_type = FitType.REGULAR_FIT
    
    # Generate recommendation
    recommendation = recommendation_engine.recommend(
        user_height=user_height,
        user_weight=user_weight,
        product_measurements=measurements,
        fit_type=parsed_fit_type,
        fabric_composition=fabric_composition,
        body_shape=parsed_body_shape
    )
    
    return recommendation
