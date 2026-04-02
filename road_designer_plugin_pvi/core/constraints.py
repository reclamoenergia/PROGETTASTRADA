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
            if not s.project_z or not s.offsets:
                continue
            left = s.road_core_left_offset if s.road_core_left_offset is not None else min(s.offsets)
            crown = s.crown_offset
            right = s.road_core_right_offset if s.road_core_right_offset is not None else max(s.offsets)
            if left >= crown or crown >= right:
                continue
            z_left = self._value_at_offset(s.offsets, s.road_core_z or s.project_z, left)
            z_crown = self._value_at_offset(s.offsets, s.road_core_z or s.project_z, crown)
            z_right = self._value_at_offset(s.offsets, s.road_core_z or s.project_z, right)

            pct_left = abs((z_crown - z_left) / (crown - left)) * 100.0
            pct_right = abs((z_right - z_crown) / (right - crown)) * 100.0
            bad_left = pct_left < min_pct or pct_left > max_pct
            bad_right = pct_right < min_pct or pct_right > max_pct
            if bad_left or bad_right:
                warnings.append(
                    f"Sezione {s.index}: pendenza trasversale sx={pct_left:.2f}% dx={pct_right:.2f}% fuori [{min_pct}, {max_pct}]%"
                )
        return warnings

    def _value_at_offset(self, offsets: List[float], values: List[float], target: float) -> float:
        if len(offsets) == 1:
            return values[0]
        idx = min(range(len(offsets)), key=lambda i: abs(offsets[i] - target))
        if abs(offsets[idx] - target) <= 1e-9:
            return values[idx]
        if offsets[idx] < target and idx + 1 < len(offsets):
            i0, i1 = idx, idx + 1
        elif offsets[idx] > target and idx - 1 >= 0:
            i0, i1 = idx - 1, idx
        else:
            return values[idx]
        x0, x1 = offsets[i0], offsets[i1]
        if abs(x1 - x0) <= 1e-9:
            return values[idx]
        t = (target - x0) / (x1 - x0)
        return values[i0] + (values[i1] - values[i0]) * t
