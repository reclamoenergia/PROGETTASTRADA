from __future__ import annotations

from pathlib import Path
from typing import List

import ezdxf

from ..core.models import ProfileData, SectionData


class DxfExporter:
    def export_sections(self, path: str, sections: List[SectionData], min_width: float) -> str:
        doc = ezdxf.new(setup=True)
        msp = doc.modelspace()
        for layer in [
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
        spacing = 30.0
        for s in sections:
            terr = [(x, z + y_shift) for x, z in zip(s.offsets, s.terrain_z)]
            proj = [(x, z + y_shift) for x, z in zip(s.offsets, s.project_z)]
            core = [(x, z + y_shift) for x, z in zip(s.offsets, s.road_core_z)]
            msp.add_lwpolyline(terr, dxfattribs={"layer": "SEZ_TERRAIN"})
            msp.add_lwpolyline(core, dxfattribs={"layer": "SEZ_ROAD_CORE"})
            msp.add_lwpolyline(proj, dxfattribs={"layer": "SEZ_PROJECT"})
            msp.add_line((0, y_shift - 5), (0, y_shift + 5), dxfattribs={"layer": "SEZ_AXIS"})
            txt = (
                f"Prog {s.progressive:.2f} | Zproj {s.project_z[len(s.project_z)//2]:.2f} | "
                f"Wmin {min_width:.2f} | Wreal {s.width_info.total_width if s.width_info else min_width:.2f} | "
                f"Cut {s.cut_area:.2f} | Fill {s.fill_area:.2f}"
            )
            msp.add_text(txt, dxfattribs={"height": 1.5, "layer": "SEZ_TEXT"}).set_placement((0, y_shift + 8))
            y_shift -= spacing
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(out))
        return str(out)

    def export_profile(self, path: str, profile: ProfileData) -> str:
        doc = ezdxf.new(setup=True)
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
