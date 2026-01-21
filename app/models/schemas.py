"""
Pydantic schemas for API request/response models.
"""
from pydantic import BaseModel, Field, validator
from typing import Dict, Optional, Literal
from uuid import UUID
from datetime import datetime
from enum import Enum


# === Enums ===

class FitType(str, Enum):
    """Garment fit type classifications."""
    SLIM_FIT = "slim_fit"
    REGULAR_FIT = "regular_fit"
    LOOSE_FIT = "loose_fit"
    OVERSIZED = "oversized"


class BodyShape(str, Enum):
    """User body shape classifications for better estimation."""
    ATHLETIC = "athletic"
    AVERAGE = "average"
    SLIM = "slim"
    STOCKY = "stocky"
    PLUS_SIZE = "plus_size"


class SizeCode(str, Enum):
    """Standard size codes."""
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    XXL = "XXL"
    XXXL = "XXXL"


# === Product Ingestion ===

class ProductMeasurements(BaseModel):
    """Measurements for a single size of a product (in cm)."""
    chest_width: float = Field(..., ge=30, le=200, description="Chest width in cm")
    length: float = Field(..., ge=30, le=150, description="Garment length in cm")
    waist: Optional[float] = Field(None, ge=30, le=180, description="Waist width in cm")
    hip: Optional[float] = Field(None, ge=30, le=200, description="Hip width in cm")
    sleeve_length: Optional[float] = Field(None, ge=20, le=100, description="Sleeve length in cm")
    shoulder_width: Optional[float] = Field(None, ge=20, le=80, description="Shoulder width in cm")


class ProductIngestRequest(BaseModel):
    """Request body for ingesting a new product."""
    sku: str = Field(..., min_length=1, max_length=100, description="Unique product SKU")
    name: str = Field(..., min_length=1, max_length=255, description="Product name")
    fit_type: FitType = Field(..., description="Garment fit type")
    fabric_composition: Dict[str, float] = Field(
        ...,
        description="Fabric composition as percentages, e.g., {'cotton': 95, 'elastane': 5}"
    )
    measurements: Dict[str, ProductMeasurements] = Field(
        ...,
        description="Measurements per size, e.g., {'S': {...}, 'M': {...}}"
    )
    
    @validator('fabric_composition')
    def validate_fabric_composition(cls, v):
        total = sum(v.values())
        if not (99 <= total <= 101):  # Allow small rounding errors
            raise ValueError(f"Fabric composition must sum to 100%, got {total}%")
        return v
    
    @validator('measurements')
    def validate_measurements(cls, v):
        if not v:
            raise ValueError("At least one size measurement is required")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "sku": "SHIRT-001",
                "name": "Classic Oxford Shirt",
                "fit_type": "regular_fit",
                "fabric_composition": {"cotton": 100},
                "measurements": {
                    "S": {"chest_width": 104, "length": 72},
                    "M": {"chest_width": 110, "length": 74},
                    "L": {"chest_width": 116, "length": 76}
                }
            }
        }


class ProductIngestResponse(BaseModel):
    """Response after successfully ingesting a product."""
    product_id: UUID
    sku: str
    message: str = "Product ingested successfully"
    sizes_count: int


# === Size Recommendation ===

class RecommendRequest(BaseModel):
    """Request body for size recommendation."""
    product_id: UUID = Field(..., description="Product UUID to get recommendation for")
    user_height: float = Field(..., ge=100, le=250, description="User height in cm")
    user_weight: float = Field(..., ge=30, le=300, description="User weight in kg")
    age: Optional[int] = Field(None, ge=10, le=120, description="User age")
    body_shape: Optional[BodyShape] = Field(None, description="User body shape for better accuracy")
    preferred_fit: Optional[Literal["tighter", "true_to_size", "looser"]] = Field(
        "true_to_size",
        description="User's fit preference"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_height": 180,
                "user_weight": 85,
                "age": 30,
                "body_shape": "average",
                "preferred_fit": "true_to_size"
            }
        }


class SizeBreakdown(BaseModel):
    """Detailed breakdown of fit for each measurement."""
    measurement: str
    user_estimated: float = Field(..., description="Estimated user measurement in cm")
    garment_actual: float = Field(..., description="Actual garment measurement in cm")
    ease_applied: float = Field(..., description="Ease (bolluk payı) applied in cm")
    fit_status: Literal["tight", "fitted", "comfortable", "loose", "very_loose"]


class RecommendResponse(BaseModel):
    """Response with size recommendation."""
    recommended_size: str = Field(..., description="Recommended size code (S/M/L/XL)")
    confidence_score: int = Field(..., ge=0, le=100, description="Confidence percentage")
    fit_description: str = Field(..., description="Human-readable fit description in English")
    fit_description_tr: Optional[str] = Field(None, description="Fit description in Turkish")
    size_breakdown: list[SizeBreakdown] = Field(
        default_factory=list,
        description="Detailed breakdown per measurement"
    )
    alternative_size: Optional[str] = Field(None, description="Alternative size if confidence is borderline")
    notes: Optional[str] = Field(None, description="Additional fitting notes")

    class Config:
        json_schema_extra = {
            "example": {
                "recommended_size": "M",
                "confidence_score": 87,
                "fit_description": "Good fit overall. Slightly roomy on chest.",
                "fit_description_tr": "Genel olarak iyi uyum. Göğüste hafif bol.",
                "size_breakdown": [
                    {
                        "measurement": "chest",
                        "user_estimated": 100,
                        "garment_actual": 110,
                        "ease_applied": 5,
                        "fit_status": "comfortable"
                    }
                ],
                "alternative_size": "L",
                "notes": "Size up if you prefer a looser fit."
            }
        }


# === Analytics ===

class WidgetEventRequest(BaseModel):
    """Request body for logging a widget event."""
    product_id: UUID
    recommended_size: str
    confidence_score: int
    user_input: Dict


class WidgetEventResponse(BaseModel):
    """Response after logging a widget event."""
    event_id: UUID
    recorded_at: datetime
