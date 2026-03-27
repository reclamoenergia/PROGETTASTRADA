from __future__ import annotations

import math
from pathlib import Path
from typing import List

from ..core.models import ProfileData, SectionData


class DxfExporter:
    DEFAULT_Z_EXAGGERATION = 2.0

    @staticmethod
    def is_ezdxf_available() -> bool:
        try:
            import ezdxf  # type: ignore

            return ezdxf is not None
        except ImportError:
            return False

    def _new_doc(self):
        try:
            import ezdxf  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Libreria opzionale 'ezdxf' non disponibile. Installare 'ezdxf' per esportare DXF."
            ) from exc
        return ezdxf.new(setup=True)

    def export_sections(
        self,
        path: str,
        sections: List[SectionData],
        min_width: float,
        z_exaggeration: float = DEFAULT_Z_EXAGGERATION,
    ) -> str:
        doc = self._new_doc()
        msp = doc.modelspace()
        for layer in [
            "SEZ_FRAME",
            "SEZ_TERRAIN",
            "SEZ_ROAD_CORE",
            "SEZ_PAD",
            "SEZ_PROJECT",
            "SEZ_SLOPES",
            "SEZ_AXIS",
            "SEZ_TEXT",
        ]:
            if layer not in doc.layers:
                doc.layers.new(name=layer)
        y_shift = 0.0
        axis_x = 0.0
        z_scale = max(0.01, float(z_exaggeration))
        frame_margin_x = 3.0
        frame_margin_y = 2.0
        text_gap = 2.0
        text_band = 3.0
        stack_gap = 3.0
        for s in sections:
            if not s.offsets or not s.terrain_z or not s.project_z:
                continue

            values = [z for z in s.terrain_z + s.project_z if math.isfinite(z)]
            if not values:
                continue
            z_min = min(values)
            z_max = max(values)
            vertical_span = max((z_max - z_min) * z_scale, 0.1)

            terr = [(axis_x + x, y_shift + z * z_scale) for x, z in zip(s.offsets, s.terrain_z)]
            proj = [(axis_x + x, y_shift + z * z_scale) for x, z in zip(s.offsets, s.project_z)]
            core = [(axis_x + x, y_shift + z * z_scale) for x, z in zip(s.offsets, s.road_core_z)]

            x_left = axis_x + min(s.offsets)
            x_right = axis_x + max(s.offsets)
            y_geom_min = y_shift + z_min * z_scale
            y_geom_max = y_shift + z_max * z_scale
            y_text = y_geom_max + text_gap
            frame_left = x_left - frame_margin_x
            frame_right = x_right + frame_margin_x
            frame_bottom = y_geom_min - frame_margin_y
            frame_top = y_text + text_band
            frame = [
                (frame_left, frame_bottom),
                (frame_right, frame_bottom),
                (frame_right, frame_top),
                (frame_left, frame_top),
                (frame_left, frame_bottom),
            ]

            # 1) frame
            msp.add_lwpolyline(frame, dxfattribs={"layer": "SEZ_FRAME", "closed": True})
            # 2) terrain
            msp.add_lwpolyline(terr, dxfattribs={"layer": "SEZ_TERRAIN"})
            # 3) project
            msp.add_lwpolyline(proj, dxfattribs={"layer": "SEZ_PROJECT"})
            # 4) road core
            if core:
                msp.add_lwpolyline(core, dxfattribs={"layer": "SEZ_ROAD_CORE"})
            pad_poly = self._build_pad_polyline(s, axis_x=axis_x, y_shift=y_shift, z_scale=z_scale)
            if pad_poly:
                msp.add_lwpolyline(pad_poly, dxfattribs={"layer": "SEZ_PAD"})
            # 5) slopes
            left_slope = self._build_slope_segment(s, left=True, axis_x=axis_x, y_shift=y_shift, z_scale=z_scale)
            right_slope = self._build_slope_segment(s, left=False, axis_x=axis_x, y_shift=y_shift, z_scale=z_scale)
            if left_slope:
                msp.add_lwpolyline(left_slope, dxfattribs={"layer": "SEZ_SLOPES"})
            if right_slope:
                msp.add_lwpolyline(right_slope, dxfattribs={"layer": "SEZ_SLOPES"})
            # 6) axis
            msp.add_line((axis_x, frame_bottom), (axis_x, frame_top), dxfattribs={"layer": "SEZ_AXIS"})

            axis_i = min(range(len(s.offsets)), key=lambda i: abs(s.offsets[i]))
            axis_z = s.project_z[axis_i]
            txt = (
                f"Sez {s.index} | Prog {s.progressive:.2f} | Zproj {axis_z:.2f} | "
                f"Wmin {min_width:.2f} | Wreal {s.width_info.total_width if s.width_info else min_width:.2f} | "
                f"Cut {s.cut_area:.2f} | Fill {s.fill_area:.2f}"
            )
            # 7) text
            msp.add_text(txt, dxfattribs={"height": 1.5, "layer": "SEZ_TEXT"}).set_placement((axis_x, y_text))

            section_height = (frame_top - frame_bottom) * 1.25  # +25% margine dinamico
            y_shift -= section_height + stack_gap + vertical_span * 0.2
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(out))
        return str(out)

    def _build_slope_segment(
        self, section: SectionData, left: bool, axis_x: float, y_shift: float, z_scale: float
    ) -> list[tuple[float, float]]:
        if not section.offsets or not section.project_z:
            return []
        if section.width_info is None:
            return []
        edge_off = -section.width_info.left_width if left else section.width_info.right_width
        outer_off = (
            section.side_slope_left_outer_offset
            if left
            else section.side_slope_right_outer_offset
        )
        if outer_off is None:
            outer_off = section.offsets[0] if left else section.offsets[-1]
        if left and outer_off > edge_off:
            return []
        if (not left) and outer_off < edge_off:
            return []
        edge_z = self._interp_piecewise(section.offsets, section.project_z, edge_off)
        outer_z = self._interp_piecewise(section.offsets, section.project_z, outer_off)
        if not (math.isfinite(edge_z) and math.isfinite(outer_z)):
            return []
        return [
            (axis_x + edge_off, y_shift + edge_z * z_scale),
            (axis_x + outer_off, y_shift + outer_z * z_scale),
        ]

    def _build_pad_polyline(self, section: SectionData, axis_x: float, y_shift: float, z_scale: float) -> list[tuple[float, float]]:
        if not section.offsets or not section.project_z or section.width_info is None:
            return []
        left = -section.width_info.left_width
        right = section.width_info.right_width
        pad = []
        for off, z in zip(section.offsets, section.project_z):
            if left <= off <= right and math.isfinite(z):
                pad.append((axis_x + off, y_shift + z * z_scale))
        return pad

    def _interp_piecewise(self, xs: List[float], ys: List[float], x: float) -> float:
        if not xs or not ys:
            return float("nan")
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        for i in range(1, len(xs)):
            x0, x1 = xs[i - 1], xs[i]
            if x0 <= x <= x1:
                dx = x1 - x0
                if abs(dx) <= 1e-12:
                    return ys[i - 1]
                t = (x - x0) / dx
                return ys[i - 1] + (ys[i] - ys[i - 1]) * t
        return float("nan")

    def export_profile(self, path: str, profile: ProfileData) -> str:
        doc = self._new_doc()
        msp = doc.modelspace()
        for layer in ["PROF_TERRAIN", "PROF_PROJECT", "PROF_AXIS", "PROF_TEXT"]:
            if layer not in doc.layers:
                doc.layers.new(name=layer)
        terr = list(zip(profile.progressive, profile.terrain_z))
        proj = list(zip(profile.progressive, profile.project_z))
        msp.add_lwpolyline(terr, dxfattribs={"layer": "PROF_TERRAIN"})
        msp.add_lwpolyline(proj, dxfattribs={"layer": "PROF_PROJECT"})
        msp.add_line((0, min(profile.terrain_z) - 5), (profile.progressive[-1], min(profile.terrain_z) - 5), dxfattribs={"layer": "PROF_AXIS"})
        msp.add_text("Profilo longitudinale", dxfattribs={"height": 2, "layer": "PROF_TEXT"}).set_placement((0, max(profile.terrain_z) + 5))
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(out))
        return str(out)
