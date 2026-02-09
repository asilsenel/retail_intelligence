"""
Body measurement estimator based on anthropometric data.
Estimates body measurements from height, weight, BMI, and body shape.
"""
import numpy as np
from typing import Dict, Optional
from app.models.schemas import BodyShape


class BodyEstimator:
    """
    Estimates body measurements using statistical models based on:
    - Height and weight (for BMI calculation)
    - Body shape classification
    - Age (optional, for minor adjustments)
    
    All measurements returned in centimeters.
    """
    
    # Base anthropometric ratios (relative to height)
    # Derived from statistical averages
    BASE_RATIOS = {
        "chest": 0.52,      # Chest circumference as ratio of height
        "waist": 0.44,      # Waist circumference
        "hip": 0.53,        # Hip circumference
        "shoulder": 0.24,   # Shoulder width
    }
    
    # Body shape modifiers (multipliers)
    BODY_SHAPE_MODIFIERS = {
        BodyShape.ATHLETIC: {
            "chest": 1.05,
            "waist": 0.92,
            "hip": 0.98,
            "shoulder": 1.08
        },
        BodyShape.AVERAGE: {
            "chest": 1.0,
            "waist": 1.0,
            "hip": 1.0,
            "shoulder": 1.0
        },
        BodyShape.SLIM: {
            "chest": 0.92,
            "waist": 0.88,
            "hip": 0.94,
            "shoulder": 0.95
        },
        BodyShape.STOCKY: {
            "chest": 1.08,
            "waist": 1.12,
            "hip": 1.06,
            "shoulder": 1.05
        },
        BodyShape.PLUS_SIZE: {
            "chest": 1.15,
            "waist": 1.22,
            "hip": 1.18,
            "shoulder": 1.02
        }
    }
    
    # BMI impact factors (how much BMI deviation affects measurements)
    BMI_IMPACT = {
        "chest": 0.8,
        "waist": 1.2,  # Waist is most affected by weight
        "hip": 0.9,
        "shoulder": 0.3  # Shoulders less affected
    }
    
    # Reference BMI for calculations (considered "average")
    REFERENCE_BMI = 22.5
    
    def __init__(self):
        pass
    
    def calculate_bmi(self, height_cm: float, weight_kg: float) -> float:
        """Calculate BMI from height (cm) and weight (kg)."""
        height_m = height_cm / 100
        return weight_kg / (height_m ** 2)
    
    def estimate_measurements(
        self,
        height_cm: float,
        weight_kg: float,
        body_shape: Optional[BodyShape] = None,
        age: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Estimate body measurements from user data.
        
        Args:
            height_cm: User's height in centimeters
            weight_kg: User's weight in kilograms
            body_shape: Optional body shape classification
            age: Optional age for minor adjustments
            
        Returns:
            Dict with estimated measurements in cm:
            - chest: Chest circumference
            - waist: Waist circumference
            - hip: Hip circumference
            - shoulder: Shoulder width
        """
        if body_shape is None:
            body_shape = BodyShape.AVERAGE
        
        bmi = self.calculate_bmi(height_cm, weight_kg)
        bmi_deviation = (bmi - self.REFERENCE_BMI) / self.REFERENCE_BMI
        
        measurements = {}
        
        for measurement, base_ratio in self.BASE_RATIOS.items():
            # Start with base calculation
            base_value = height_cm * base_ratio
            
            # Apply body shape modifier
            shape_modifier = self.BODY_SHAPE_MODIFIERS[body_shape][measurement]
            adjusted_value = base_value * shape_modifier
            
            # Apply BMI impact
            bmi_factor = 1 + (bmi_deviation * self.BMI_IMPACT[measurement])
            adjusted_value *= bmi_factor
            
            # Age adjustment (slight increase for older ages)
            if age is not None and age > 40:
                age_factor = 1 + ((age - 40) * 0.002)  # 0.2% per year over 40
                if measurement in ["waist", "hip"]:
                    adjusted_value *= min(age_factor, 1.05)  # Cap at 5%
            
            measurements[measurement] = round(adjusted_value, 1)

        # Foot length estimation (anthropometric ratio)
        # Average: foot_length ≈ height × 0.153
        measurements["foot_length"] = round(height_cm * 0.153, 1)

        return measurements
    
    def get_body_analysis(
        self,
        height_cm: float,
        weight_kg: float,
        body_shape: Optional[BodyShape] = None
    ) -> Dict:
        """
        Get a complete body analysis including BMI category and proportions.
        
        Returns:
            Dict with:
            - bmi: Calculated BMI value
            - bmi_category: underweight/normal/overweight/obese
            - measurements: Estimated body measurements
            - proportions: Body proportion analysis
        """
        bmi = self.calculate_bmi(height_cm, weight_kg)
        measurements = self.estimate_measurements(height_cm, weight_kg, body_shape)
        
        # Determine BMI category
        if bmi < 18.5:
            bmi_category = "underweight"
        elif bmi < 25:
            bmi_category = "normal"
        elif bmi < 30:
            bmi_category = "overweight"
        else:
            bmi_category = "obese"
        
        # Calculate proportions
        waist_to_hip = measurements["waist"] / measurements["hip"]
        chest_to_waist = measurements["chest"] / measurements["waist"]
        
        return {
            "bmi": round(bmi, 1),
            "bmi_category": bmi_category,
            "measurements": measurements,
            "proportions": {
                "waist_to_hip_ratio": round(waist_to_hip, 2),
                "chest_to_waist_ratio": round(chest_to_waist, 2)
            }
        }


# Singleton instance
body_estimator = BodyEstimator()
