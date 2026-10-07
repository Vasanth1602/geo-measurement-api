"""
Pydantic v2 schemas for file status and measurement API endpoints.
Derived metrics (area_hectares, length_km) are automatically computed.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: Optional[int] = None
    crs: Optional[str] = None
    status: str


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: Optional[str] = None
    crs: str
    properties: Dict[str, Any]
    geometry: Optional[Dict[str, Any]] = None
    supported: bool
    area_sq_m: Optional[float] = None
    area_hectares: Optional[float] = None
    length_m: Optional[float] = None
    length_km: Optional[float] = None
    measurement_crs: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def compute_derived_units(self) -> "FeatureOut":
        if self.area_sq_m is not None:
            self.area_hectares = round(self.area_sq_m / 10000.0, 4)
        else:
            self.area_hectares = None

        if self.length_m is not None:
            self.length_km = round(self.length_m / 1000.0, 4)
        else:
            self.length_km = None

        return self


class MeasurementsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    crs: Optional[str] = None
    feature_count: int
    features: List[FeatureOut]
