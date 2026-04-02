from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class SamplePoint:
    progressive: float
    x: float
    y: float
    z_terrain: float
    z_project: float = 0.0


@dataclass
class WidthInfo:
    left_width: float
    right_width: float
    total_width: float
    classification: str = "STANDARD"


@dataclass
class SectionData:
    index: int
    progressive: float
    axis_point: Tuple[float, float]
    tangent: Tuple[float, float]
    normal: Tuple[float, float]
    offsets: List[float]
    terrain_z: List[float]
    project_z: List[float] = field(default_factory=list)
    road_core_z: List[float] = field(default_factory=list)
    road_core_left_offset: Optional[float] = None
    crown_offset: float = 0.0
    road_core_right_offset: Optional[float] = None
    side_slope_left_resolved: bool = True
    side_slope_right_resolved: bool = True
    left_slope_resolved: bool = True
    right_slope_resolved: bool = True
    left_slope_hit_offset: Optional[float] = None
    right_slope_hit_offset: Optional[float] = None
    side_slope_left_outer_offset: Optional[float] = None
    side_slope_right_outer_offset: Optional[float] = None
    side_slope_left_note: str = ""
    side_slope_right_note: str = ""
    warnings: List[str] = field(default_factory=list)
    cut_area: float = 0.0
    fill_area: float = 0.0
    width_info: Optional[WidthInfo] = None


@dataclass
class ProfileData:
    progressive: List[float]
    terrain_z: List[float]
    project_z: List[float]




@dataclass
class PviRow:
    feature_id: int
    progressive: float
    elevation: float
    curve_length: float = 0.0
    enabled: bool = True
    source_label: str = ""
    warning: str = ""

@dataclass
class EarthworkInterval:
    section_i: int
    section_f: int
    progressive_i: float
    progressive_f: float
    cut_area_i: float
    cut_area_f: float
    fill_area_i: float
    fill_area_f: float
    cut_volume: float
    fill_volume: float
    cum_cut: float
    cum_fill: float


@dataclass
class EarthworkResult:
    intervals: List[EarthworkInterval]
    total_cut: float
    total_fill: float


@dataclass
class PluginSettings:
    min_platform_width: float = 5.0
    crossfall_nominal_pct: float = 3.0
    crossfall_min_pct: float = 2.0
    crossfall_max_pct: float = 6.0
    max_longitudinal_slope_pct: float = 12.0
    min_plan_radius: float = 40.0
    min_vertical_radius: float = 250.0
    cut_slope_hv: float = 1.5
    fill_slope_hv: float = 1.8
    pad_slope_pct: float = 2.0
    axis_sample_step: float = 5.0
    section_step: float = 20.0
    section_length: float = 80.0
    section_sample_step: float = 1.0
    profile_h_scale: float = 1000.0
    profile_v_scale: float = 200.0
    section_scale: float = 200.0
    section_vertical_exaggeration: float = 2.0
    section_quote_step: float = 5.0
    output_folder: str = ""
    project_name: str = "road_project"
    export_sections_dxf: bool = True
    export_profile_dxf: bool = True
    export_csv: bool = True
    dtm_layer_name: str = ""
    axis_layer_name: str = ""
    polygon_layer_name: str = ""
    forced_points_layer_name: str = ""
    terrain_source_mode: str = "raster"
    tin_contour_interval: float = 1.0
    tin_processing_buffer: float = 120.0
    tin_simplify_tolerance: float = 0.0
    tin_add_contours_layer: bool = False
    tin_add_triangles_layer: bool = False
    tin_use_session_cache: bool = True
    profile_mode: str = "automatic"
    pvi_layer_name: str = ""
    pvi_elevation_field: str = ""
    pvi_curve_length_field: str = ""
    pvi_default_curve_length: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "PluginSettings":
        inst = cls()
        for key, value in data.items():
            if hasattr(inst, key):
                setattr(inst, key, value)
        return inst
