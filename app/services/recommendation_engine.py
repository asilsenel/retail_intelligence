"""
Size Recommendation Engine with Ease (Bolluk Payı) Calculation.

This is the core logic for determining the best fitting size based on:
1. User's estimated body measurements
2. Garment measurements from the product
3. Ease allowance based on fit type and fabric composition
"""
import numpy as np
from typing import Dict, List, Optional, Tuple, Literal
from app.models.schemas import (
    FitType, BodyShape, RecommendResponse, SizeBreakdown
)
from app.services.body_estimator import body_estimator


class RecommendationEngine:
    """
    Statistical heuristic model for size recommendations.
    
    Key concept: EASE (Bolluk Payı)
    - Garment Measurement ≠ Body Measurement
    - Garment must be LARGER than body to allow comfortable movement
    - Required ease varies by fit type and fabric stretch
    """
    
    # Ease configuration per fit type (in cm)
    # These are the MINIMUM ease values for comfortable wear
    EASE_CONFIG = {
        FitType.SLIM_FIT: {
            "chest": 3,
            "waist": 2,
            "hip": 2
        },
        FitType.REGULAR_FIT: {
            "chest": 5,
            "waist": 5,
            "hip": 5
        },
        FitType.LOOSE_FIT: {
            "chest": 10,
            "waist": 10,
            "hip": 10
        },
        FitType.OVERSIZED: {
            "chest": 15,
            "waist": 15,
            "hip": 15
        }
    }
    
    # Fabric stretch factors - reduce required ease for stretchy fabrics
    # Key is fabric type, value is ease reduction in cm
    STRETCH_FABRICS = {
        "elastane": 2.5,
        "spandex": 2.5,
        "lycra": 2.5,
        "polyester_blend": 1.0,
        "jersey": 1.5,
        "stretch_cotton": 1.5
    }
    
    # Confidence penalties (percentage points deducted)
    CONFIDENCE_PENALTIES = {
        "borderline_fit": 15,      # When garment is at minimum ease
        "requires_stretch": 10,    # When we need stretch for fit
        "no_exact_match": 20,      # When recommending closest available
        "missing_measurement": 5   # Per missing measurement
    }
    
    # Fit status thresholds (ease ratio: garment_space / required_ease)
    FIT_THRESHOLDS = {
        "tight": 0.5,       # Less than half required ease
        "fitted": 0.8,      # 50-80% of ideal ease
        "comfortable": 1.2, # 80-120% of ideal ease
        "loose": 1.5,       # 120-150% of ideal ease
        "very_loose": 2.0   # More than 150% of ideal ease
    }
    
    def __init__(self):
        self.body_estimator = body_estimator
    
    def _calculate_stretch_reduction(self, fabric_composition: Dict[str, float]) -> float:
        """
        Calculate total ease reduction based on fabric stretch properties.
        
        Args:
            fabric_composition: Dict like {"cotton": 95, "elastane": 5}
            
        Returns:
            Total ease reduction in cm
        """
        total_reduction = 0.0
        
        for fabric, percentage in fabric_composition.items():
            fabric_lower = fabric.lower()
            for stretch_fabric, reduction in self.STRETCH_FABRICS.items():
                if stretch_fabric in fabric_lower:
                    # Proportional reduction based on fabric percentage
                    total_reduction += reduction * (percentage / 100)
                    break
        
        # Cap the maximum reduction
        return min(total_reduction, 4.0)
    
    def _calculate_required_ease(
        self,
        fit_type: FitType,
        fabric_composition: Dict[str, float],
        measurement_type: str
    ) -> float:
        """
        Calculate the required ease for a specific measurement.
        
        Args:
            fit_type: The garment's fit type
            fabric_composition: Fabric blend percentages
            measurement_type: Type of measurement (chest, waist, hip)
            
        Returns:
            Required ease in cm
        """
        base_ease = self.EASE_CONFIG[fit_type].get(measurement_type, 5)
        stretch_reduction = self._calculate_stretch_reduction(fabric_composition)
        
        # Apply stretch reduction
        adjusted_ease = base_ease - stretch_reduction
        
        # Ensure minimum positive ease (unless very stretchy)
        if stretch_reduction > 2:
            return max(adjusted_ease, 0)  # Can go to 0 with enough stretch
        else:
            return max(adjusted_ease, 1)  # Minimum 1cm ease
    
    def _get_fit_status(
        self,
        available_space: float,
        required_ease: float
    ) -> Literal["tight", "fitted", "comfortable", "loose", "very_loose"]:
        """
        Determine fit status based on available space vs required ease.
        
        Args:
            available_space: Garment measurement - body measurement
            required_ease: Required ease for the fit type
            
        Returns:
            Fit status string
        """
        if required_ease == 0:
            ratio = available_space / 5  # Use 5cm as reference for stretch fits
        else:
            ratio = available_space / required_ease
        
        if ratio < self.FIT_THRESHOLDS["tight"]:
            return "tight"
        elif ratio < self.FIT_THRESHOLDS["fitted"]:
            return "fitted"
        elif ratio < self.FIT_THRESHOLDS["comfortable"]:
            return "comfortable"
        elif ratio < self.FIT_THRESHOLDS["loose"]:
            return "loose"
        else:
            return "very_loose"
    
    def _score_size(
        self,
        body_measurements: Dict[str, float],
        garment_measurements: Dict[str, float],
        fit_type: FitType,
        fabric_composition: Dict[str, float],
        preferred_fit: str = "true_to_size"
    ) -> Tuple[float, List[SizeBreakdown]]:
        """
        Score how well a garment size fits the user.
        
        Args:
            body_measurements: Estimated user measurements
            garment_measurements: Product measurements for this size
            fit_type: Garment fit type
            fabric_composition: Fabric blend
            preferred_fit: User's fit preference
            
        Returns:
            Tuple of (score 0-100, list of SizeBreakdown)
        """
        score = 100.0
        breakdowns = []
        
        # Weight of each measurement in the overall score
        measurement_weights = {
            "chest": 0.4,
            "waist": 0.3,
            "hip": 0.2,
            "shoulder": 0.1
        }
        
        # Map garment measurement keys to body measurement keys
        measurement_mapping = {
            "chest_width": "chest",
            "chest": "chest",
            "waist": "waist",
            "hip": "hip",
            "shoulder_width": "shoulder"
        }
        
        measured_weight = 0
        weighted_fit_score = 0
        
        for garm_key, body_key in measurement_mapping.items():
            # Check if garment measurement exists and is not None
            garment_value = garment_measurements.get(garm_key)
            if garment_value is None:
                continue
            
            # Check if body measurement exists
            body_value = body_measurements.get(body_key)
            if body_value is None:
                continue
            
            # Both values are expected to be in the same unit (circumference in cm)
            # Garment chest_width is typically full circumference (e.g., 104cm for size S)
            
            required_ease = self._calculate_required_ease(
                fit_type, fabric_composition, body_key
            )
            
            available_space = garment_value - body_value
            fit_status = self._get_fit_status(available_space, required_ease)
            
            # Calculate fit score for this measurement
            if available_space < 0:
                # Garment is smaller than body - too tight
                fit_score = max(0, 30 + (available_space * 5))  # Severe penalty
            elif fit_status == "tight":
                fit_score = 50
            elif fit_status == "fitted":
                fit_score = 75
            elif fit_status == "comfortable":
                fit_score = 100
            elif fit_status == "loose":
                fit_score = 85
            else:  # very_loose
                fit_score = 60
            
            # Apply user preference adjustment
            if preferred_fit == "tighter" and fit_status in ["fitted", "tight"]:
                fit_score += 10
            elif preferred_fit == "looser" and fit_status in ["loose", "very_loose"]:
                fit_score += 10
            
            weight = measurement_weights.get(body_key, 0.1)
            measured_weight += weight
            weighted_fit_score += fit_score * weight
            
            breakdowns.append(SizeBreakdown(
                measurement=body_key,
                user_estimated=round(body_value, 1),
                garment_actual=round(garment_measurements[garm_key], 1),
                ease_applied=round(required_ease, 1),
                fit_status=fit_status
            ))
        
        # Calculate final score
        if measured_weight > 0:
            score = weighted_fit_score / measured_weight
        else:
            score -= self.CONFIDENCE_PENALTIES["missing_measurement"] * 4
        
        return (max(0, min(100, score)), breakdowns)
    
    def _generate_fit_description(
        self,
        breakdowns: List[SizeBreakdown],
        preferred_fit: str
    ) -> Tuple[str, str]:
        """
        Generate human-readable fit descriptions in English and Turkish.
        
        Returns:
            Tuple of (english_description, turkish_description)
        """
        issues_en = []
        issues_tr = []
        
        status_descriptions = {
            "tight": {
                "chest": ("Tight on chest", "Göğüste dar"),
                "waist": ("Tight on waist", "Belde dar"),
                "hip": ("Tight on hips", "Kalçada dar"),
                "shoulder": ("Tight on shoulders", "Omuzlarda dar")
            },
            "fitted": {
                "chest": ("Fitted on chest", "Göğüste oturumlu"),
                "waist": ("Fitted on waist", "Belde oturumlu"),
                "hip": ("Fitted on hips", "Kalçada oturumlu"),
                "shoulder": ("Fitted on shoulders", "Omuzlarda oturumlu")
            },
            "comfortable": {
                "chest": ("Comfortable chest fit", "Göğüste rahat"),
                "waist": ("Comfortable waist fit", "Belde rahat"),
                "hip": ("Comfortable hip fit", "Kalçada rahat"),
                "shoulder": ("Comfortable shoulder fit", "Omuzlarda rahat")
            },
            "loose": {
                "chest": ("Roomy on chest", "Göğüste bol"),
                "waist": ("Roomy on waist", "Belde bol"),
                "hip": ("Roomy on hips", "Kalçada bol"),
                "shoulder": ("Roomy on shoulders", "Omuzlarda bol")
            },
            "very_loose": {
                "chest": ("Very loose on chest", "Göğüste çok bol"),
                "waist": ("Very loose on waist", "Belde çok bol"),
                "hip": ("Very loose on hips", "Kalçada çok bol"),
                "shoulder": ("Very loose on shoulders", "Omuzlarda çok bol")
            }
        }
        
        for breakdown in breakdowns:
            if breakdown.fit_status in ["tight", "loose", "very_loose"]:
                desc = status_descriptions[breakdown.fit_status].get(
                    breakdown.measurement,
                    (f"{breakdown.fit_status.title()} fit", "Genel uyum")
                )
                issues_en.append(desc[0])
                issues_tr.append(desc[1])
        
        if not issues_en:
            return ("Good overall fit", "Genel olarak iyi uyum")
        
        return (". ".join(issues_en) + ".", ". ".join(issues_tr) + ".")
    
    def recommend(
        self,
        user_height: float,
        user_weight: float,
        product_measurements: Dict[str, Dict],
        fit_type: FitType,
        fabric_composition: Dict[str, float],
        body_shape: Optional[BodyShape] = None,
        age: Optional[int] = None,
        preferred_fit: str = "true_to_size"
    ) -> RecommendResponse:
        """
        Generate size recommendation.
        
        Args:
            user_height: Height in cm
            user_weight: Weight in kg
            product_measurements: Dict of size -> measurements
            fit_type: Garment fit type
            fabric_composition: Fabric blend percentages
            body_shape: Optional body shape classification
            age: Optional user age
            preferred_fit: User preference (tighter/true_to_size/looser)
            
        Returns:
            RecommendResponse with recommended size, confidence, and details
        """
        # Step 1: Estimate body measurements
        body_measurements = self.body_estimator.estimate_measurements(
            user_height, user_weight, body_shape, age
        )
        
        # Step 2: Score each available size
        size_scores: Dict[str, Tuple[float, List[SizeBreakdown]]] = {}
        
        for size_code, measurements in product_measurements.items():
            # Convert to proper format if nested
            if isinstance(measurements, dict) and not any(
                key in measurements for key in ['chest_width', 'chest', 'waist']
            ):
                # Measurements might be wrapped in a model-like structure
                measurements = dict(measurements)
            
            score, breakdowns = self._score_size(
                body_measurements,
                measurements,
                fit_type,
                fabric_composition,
                preferred_fit
            )
            size_scores[size_code] = (score, breakdowns)
        
        # Step 3: Find best size
        sorted_sizes = sorted(size_scores.items(), key=lambda x: x[1][0], reverse=True)
        best_size, (best_score, best_breakdowns) = sorted_sizes[0]
        
        # Step 4: Determine alternative size
        alternative_size = None
        if len(sorted_sizes) > 1:
            second_best = sorted_sizes[1]
            if second_best[1][0] >= best_score - 15:  # Within 15 points
                alternative_size = second_best[0]
        
        # Step 5: Generate descriptions
        fit_desc_en, fit_desc_tr = self._generate_fit_description(
            best_breakdowns, preferred_fit
        )
        
        # Step 6: Add notes based on fit analysis
        notes = None
        if any(b.fit_status == "tight" for b in best_breakdowns):
            notes = "Consider sizing up if you prefer a more relaxed fit."
        elif any(b.fit_status == "very_loose" for b in best_breakdowns):
            notes = "Consider sizing down for a more fitted look."
        
        return RecommendResponse(
            recommended_size=best_size,
            confidence_score=int(best_score),
            fit_description=fit_desc_en,
            fit_description_tr=fit_desc_tr,
            size_breakdown=best_breakdowns,
            alternative_size=alternative_size,
            notes=notes
        )


# Singleton instance
recommendation_engine = RecommendationEngine()
