from __future__ import annotations

from typing import List

from .models import ProfileData, SectionData


class ConstraintChecker:
    def check_longitudinal(self, profile: ProfileData, max_slope_pct: float) -> List[str]:
        warnings: List[str] = []
        max_s = max_slope_pct / 100.0
        for i in range(1, len(profile.progressive)):
            ds = profile.progressive[i] - profile.progressive[i - 1]
            if ds <= 0:
                continue
            g = abs((profile.project_z[i] - profile.project_z[i - 1]) / ds)
            if g > max_s + 1e-6:
                warnings.append(f"Pendenza oltre limite tra {profile.progressive[i-1]:.1f} e {profile.progressive[i]:.1f} m")
        return warnings

    def check_crossfall(self, sections: List[SectionData], min_pct: float, max_pct: float) -> List[str]:
        warnings: List[str] = []
        for s in sections:
            if not s.project_z:
                continue
            left = s.road_core_left_offset if s.road_core_left_offset is not None else min(s.offsets)
            right = s.road_core_right_offset if s.road_core_right_offset is not None else max(s.offsets)
            i0 = min(range(len(s.offsets)), key=lambda i: abs(s.offsets[i] - left))
            i1 = min(range(len(s.offsets)), key=lambda i: abs(s.offsets[i] - right))
            if i0 == i1:
                continue
            dz = abs(s.project_z[i1] - s.project_z[i0])
            dx = abs(s.offsets[i1] - s.offsets[i0])
            if dx <= 0:
                continue
            pct = dz / dx * 100.0
            if pct < min_pct or pct > max_pct:
                warnings.append(f"Sezione {s.index}: pendenza trasversale {pct:.2f}% fuori [{min_pct}, {max_pct}]%")
        return warnings
