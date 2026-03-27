from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from ..core.models import ProfileData, SectionData


@dataclass
class SheetSpec:
    width: float = 1189.0
    height: float = 841.0
    margin: float = 15.0
    right_band: float = 210.0

    @property
    def inner_left(self) -> float:
        return self.margin

    @property
    def inner_bottom(self) -> float:
        return self.margin

    @property
    def inner_width(self) -> float:
        return self.width - 2.0 * self.margin

    @property
    def inner_height(self) -> float:
        return self.height - 2.0 * self.margin

    @property
    def usable_width(self) -> float:
        return self.inner_width - self.right_band


class DxfExporter:
    DEFAULT_Z_EXAGGERATION = 2.0
    PROFILE_H_SCALE = 1000.0
    PROFILE_V_SCALE = 200.0
    SECTION_H_SCALE = 200.0
    SHEET_GAP = 120.0

    PROFILE_LAYERS = [
        "PROF_FRAME",
        "PROF_TERRAIN",
        "PROF_PROJECT",
        "PROF_SECTIONS",
        "PROF_TEXT",
        "PROF_TABLE",
    ]
    SECTION_LAYERS = [
        "SEZ_FRAME",
        "SEZ_AXIS",
        "SEZ_TERRAIN",
        "SEZ_PROJECT",
        "SEZ_ROAD_CORE",
        "SEZ_PAD",
        "SEZ_SLOPES",
        "SEZ_TEXT",
        "SEZ_TABLE",
    ]
    LAYER_STYLE = {
        "PROF_FRAME": {"color": 8, "lineweight": 35},
        "PROF_TERRAIN": {"color": 8, "lineweight": 18},
        "PROF_PROJECT": {"color": 1, "lineweight": 35},
        "PROF_SECTIONS": {"color": 4, "lineweight": 18},
        "PROF_TEXT": {"color": 7, "lineweight": 18},
        "PROF_TABLE": {"color": 8, "lineweight": 18},
        "SEZ_FRAME": {"color": 8, "lineweight": 35},
        "SEZ_AXIS": {"color": 7, "lineweight": 18},
        "SEZ_TERRAIN": {"color": 8, "lineweight": 18},
        "SEZ_PROJECT": {"color": 1, "lineweight": 35},
        "SEZ_ROAD_CORE": {"color": 2, "lineweight": 35},
        "SEZ_PAD": {"color": 3, "lineweight": 35},
        "SEZ_SLOPES": {"color": 4, "lineweight": 30},
        "SEZ_TEXT": {"color": 7, "lineweight": 18},
        "SEZ_TABLE": {"color": 8, "lineweight": 18},
    }

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

    def _ensure_layers(self, doc, layers: Iterable[str]) -> None:
        for layer in layers:
            if layer not in doc.layers:
                doc.layers.new(name=layer)
            style = self.LAYER_STYLE.get(layer, {})
            layer_obj = doc.layers.get(layer)
            if "color" in style:
                layer_obj.dxf.color = style["color"]
            if "lineweight" in style:
                layer_obj.dxf.lineweight = style["lineweight"]

    def export_all_layout(
        self,
        path: str,
        profile: Optional[ProfileData],
        sections: List[SectionData],
        quote_step_m: float,
        section_z_exaggeration: float = DEFAULT_Z_EXAGGERATION,
        profile_h_scale: float = PROFILE_H_SCALE,
        profile_v_scale: float = PROFILE_V_SCALE,
        section_h_scale: float = SECTION_H_SCALE,
        min_width: float = 0.0,
    ) -> str:
        doc = self._new_doc()
        msp = doc.modelspace()
        self._ensure_layers(doc, self.PROFILE_LAYERS + self.SECTION_LAYERS)

        sheet = SheetSpec()
        profile_sheet_count = 0
        if profile and profile.progressive:
            profile_sheet_count = self._draw_profile_sheets(
                msp,
                sheet,
                profile,
                sections,
                profile_h_scale=max(1.0, profile_h_scale),
                profile_v_scale=max(1.0, profile_v_scale),
            )

        section_origin_x = profile_sheet_count * (sheet.width + self.SHEET_GAP)
        self._draw_section_sheets(
            msp,
            sheet,
            sections,
            section_origin_x,
            quote_step_m=max(0.1, quote_step_m),
            z_exaggeration=max(0.01, section_z_exaggeration),
            section_h_scale=max(1.0, section_h_scale),
            min_width=min_width,
        )

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(out))
        return str(out)

    def export_sections(
        self,
        path: str,
        sections: List[SectionData],
        min_width: float,
        z_exaggeration: float = DEFAULT_Z_EXAGGERATION,
    ) -> str:
        return self.export_all_layout(
            path=path,
            profile=None,
            sections=sections,
            quote_step_m=1.0,
            section_z_exaggeration=z_exaggeration,
            min_width=min_width,
        )

    def export_profile(self, path: str, profile: ProfileData) -> str:
        return self.export_all_layout(
            path=path,
            profile=profile,
            sections=[],
            quote_step_m=1.0,
            section_z_exaggeration=self.DEFAULT_Z_EXAGGERATION,
        )

    def _draw_sheet_frame(self, msp, base_x: float, base_y: float, sheet: SheetSpec, layer: str) -> None:
        outer = [
            (base_x, base_y),
            (base_x + sheet.width, base_y),
            (base_x + sheet.width, base_y + sheet.height),
            (base_x, base_y + sheet.height),
            (base_x, base_y),
        ]
        inner = [
            (base_x + sheet.inner_left, base_y + sheet.inner_bottom),
            (base_x + sheet.inner_left + sheet.usable_width, base_y + sheet.inner_bottom),
            (base_x + sheet.inner_left + sheet.usable_width, base_y + sheet.inner_bottom + sheet.inner_height),
            (base_x + sheet.inner_left, base_y + sheet.inner_bottom + sheet.inner_height),
            (base_x + sheet.inner_left, base_y + sheet.inner_bottom),
        ]
        band_left = base_x + sheet.inner_left + sheet.usable_width
        band = [
            (band_left, base_y + sheet.inner_bottom),
            (base_x + sheet.inner_left + sheet.inner_width, base_y + sheet.inner_bottom),
            (base_x + sheet.inner_left + sheet.inner_width, base_y + sheet.inner_bottom + sheet.inner_height),
            (band_left, base_y + sheet.inner_bottom + sheet.inner_height),
            (band_left, base_y + sheet.inner_bottom),
        ]
        msp.add_lwpolyline(outer, dxfattribs={"layer": layer, "closed": True})
        msp.add_lwpolyline(inner, dxfattribs={"layer": layer, "closed": True})
        msp.add_lwpolyline(band, dxfattribs={"layer": layer, "closed": True})

    def _draw_profile_sheets(
        self,
        msp,
        sheet: SheetSpec,
        profile: ProfileData,
        sections: List[SectionData],
        profile_h_scale: float,
        profile_v_scale: float,
    ) -> int:
        p0 = profile.progressive[0]
        p1 = profile.progressive[-1]
        span_per_sheet = (sheet.usable_width - 40.0) * profile_h_scale / 1000.0
        span_per_sheet = max(span_per_sheet, 1.0)
        total_span = max(0.0, p1 - p0)
        sheet_count = max(1, int(math.ceil(total_span / span_per_sheet)))

        min_z = min([z for z in profile.terrain_z + profile.project_z if math.isfinite(z)] or [0.0])
        max_z = max([z for z in profile.terrain_z + profile.project_z if math.isfinite(z)] or [1.0])

        for idx in range(sheet_count):
            base_x = idx * (sheet.width + self.SHEET_GAP)
            base_y = 0.0
            self._draw_sheet_frame(msp, base_x, base_y, sheet, "PROF_FRAME")

            usable_left = base_x + sheet.inner_left
            usable_bottom = base_y + sheet.inner_bottom
            usable_top = usable_bottom + sheet.inner_height
            graph_left = usable_left + 20.0
            graph_right = usable_left + sheet.usable_width - 20.0
            table_top = usable_bottom + 140.0
            graph_bottom = table_top + 15.0
            graph_top = usable_top - 110.0

            s_prog = p0 + idx * span_per_sheet
            e_prog = min(p1, s_prog + span_per_sheet)
            title = f"Profilo longitudinale | Tavola {idx + 1}/{sheet_count}"
            scale_txt = f"Scale H 1:{int(profile_h_scale)}  V 1:{int(profile_v_scale)}"
            msp.add_text(title, dxfattribs={"height": 6.0, "layer": "PROF_TEXT"}).set_placement((graph_left, usable_top - 20.0))
            msp.add_text(scale_txt, dxfattribs={"height": 4.0, "layer": "PROF_TEXT"}).set_placement((graph_left, usable_top - 33.0))
            msp.add_text(f"Prog {s_prog:.2f} - {e_prog:.2f}", dxfattribs={"height": 3.5, "layer": "PROF_TEXT"}).set_placement((graph_left, usable_top - 44.0))

            gx_span = max(1e-6, e_prog - s_prog)
            vertical_mm_per_m = 1000.0 / max(1.0, profile_v_scale)
            y_base_ref = min_z
            clipped_profile = False

            def map_point(p: float, z: float) -> tuple[float, float]:
                nonlocal clipped_profile
                x = graph_left + (p - s_prog) / gx_span * (graph_right - graph_left)
                y_raw = graph_bottom + (z - y_base_ref) * vertical_mm_per_m
                y = max(graph_bottom, min(graph_top, y_raw))
                if abs(y - y_raw) > 1e-9:
                    clipped_profile = True
                return x, y

            terr_pts = [map_point(p, z) for p, z in zip(profile.progressive, profile.terrain_z) if s_prog <= p <= e_prog]
            proj_pts = [map_point(p, z) for p, z in zip(profile.progressive, profile.project_z) if s_prog <= p <= e_prog]
            if len(terr_pts) >= 2:
                msp.add_lwpolyline(terr_pts, dxfattribs={"layer": "PROF_TERRAIN"})
            if len(proj_pts) >= 2:
                msp.add_lwpolyline(proj_pts, dxfattribs={"layer": "PROF_PROJECT"})
            msp.add_lwpolyline(
                [(graph_left, graph_bottom), (graph_right, graph_bottom), (graph_right, graph_top), (graph_left, graph_top), (graph_left, graph_bottom)],
                dxfattribs={"layer": "PROF_FRAME", "closed": True},
            )
            if clipped_profile:
                msp.add_text(
                    "ATTENZIONE: profilo ritagliato in verticale (scala V richiesta)",
                    dxfattribs={"height": 2.2, "layer": "PROF_TEXT"},
                ).set_placement((graph_left, graph_bottom - 6.0))

            marks = []
            for sec in [s for s in sections if s_prog <= s.progressive <= e_prog]:
                terr = self._interp_piecewise(profile.progressive, profile.terrain_z, sec.progressive)
                proj = self._interp_piecewise(profile.progressive, profile.project_z, sec.progressive)
                x, y_terr = map_point(sec.progressive, terr)
                _, y_proj = map_point(sec.progressive, proj)
                marks.append(
                    {
                        "section": sec,
                        "x": x,
                        "terrain_z": terr,
                        "project_z": proj,
                        "y_terrain": y_terr,
                        "y_project": y_proj,
                    }
                )
                msp.add_line((x, graph_bottom), (x, graph_top), dxfattribs={"layer": "PROF_SECTIONS"})
                msp.add_text(f"S{sec.index}", dxfattribs={"height": 2.5, "layer": "PROF_TEXT"}).set_placement((x + 1.0, graph_top + 3.0))
                msp.add_text(f"{sec.progressive:.2f}", dxfattribs={"height": 2.3, "layer": "PROF_TEXT"}).set_placement((x + 1.0, y_proj + 2.5))
                msp.add_text(f"T {terr:.2f}", dxfattribs={"height": 2.0, "layer": "PROF_TEXT"}).set_placement((x + 1.0, y_terr - 2.5))
                msp.add_text(f"P {proj:.2f}", dxfattribs={"height": 2.0, "layer": "PROF_TEXT"}).set_placement((x + 1.0, y_proj - 2.5))

            self._draw_profile_table(msp, marks, graph_left, graph_right, table_top, usable_bottom + 20.0)
        return sheet_count

    def _draw_profile_table(self, msp, marks: List[dict], left: float, right: float, top: float, bottom: float) -> None:
        rows = ["PROGRESSIVA", "QUOTA TERRENO", "QUOTA PROGETTO"]
        height = top - bottom
        row_h = height / max(1, len(rows))
        label_w = 45.0
        table_left = left
        col_left = table_left + label_w
        table_right = right
        msp.add_lwpolyline(
            [(table_left, top), (table_right, top), (table_right, bottom), (table_left, bottom), (table_left, top)],
            dxfattribs={"layer": "PROF_TABLE", "closed": True},
        )
        msp.add_line((col_left, top), (col_left, bottom), dxfattribs={"layer": "PROF_TABLE"})
        for ridx in range(1, len(rows)):
            y = top - ridx * row_h
            msp.add_line((table_left, y), (table_right, y), dxfattribs={"layer": "PROF_TABLE"})

        if marks:
            x_positions = [max(col_left, min(table_right, m["x"])) for m in marks]
            bounds = [col_left]
            for i in range(1, len(x_positions)):
                bounds.append((x_positions[i - 1] + x_positions[i]) / 2.0)
            bounds.append(table_right)
            for x in bounds[1:-1]:
                msp.add_line((x, top), (x, bottom), dxfattribs={"layer": "PROF_TABLE"})

        for ridx, label in enumerate(rows):
            y = top - (ridx + 0.7) * row_h
            msp.add_text(label, dxfattribs={"height": 2.2, "layer": "PROF_TEXT"}).set_placement((table_left + 1.5, y))

        for m in marks:
            sec = m["section"]
            x = max(col_left, min(table_right, m["x"]))
            values = [f"{sec.progressive:.2f}", f"{m['terrain_z']:.2f}", f"{m['project_z']:.2f}"]
            for ridx, val in enumerate(values):
                y = top - (ridx + 0.7) * row_h
                msp.add_text(val, dxfattribs={"height": 2.2, "layer": "PROF_TEXT"}).set_placement((x, y), align="MIDDLE_CENTER")

    def _draw_section_sheets(
        self,
        msp,
        sheet: SheetSpec,
        sections: List[SectionData],
        origin_x: float,
        quote_step_m: float,
        z_exaggeration: float,
        section_h_scale: float,
        min_width: float,
    ) -> None:
        if not sections:
            return
        prepared = [self._prepare_section_layout(s, quote_step_m, z_exaggeration, section_h_scale) for s in sections]
        prepared = [p for p in prepared if p]
        if not prepared:
            return

        sheet_idx = 0
        col_x = origin_x + sheet.inner_left + 10.0
        y_cursor = sheet.height - sheet.margin - 10.0
        col_width = 0.0
        frame_drawn_for_sheet: set[int] = set()

        for item in prepared:
            w = item["cart_w"]
            h = item["cart_h"]

            if y_cursor - h < sheet.margin + 10.0:
                col_x += col_width + 12.0
                y_cursor = sheet.height - sheet.margin - 10.0
                col_width = 0.0

            max_usable_x = origin_x + sheet.inner_left + sheet.usable_width - 10.0
            if col_x + w > max_usable_x:
                sheet_idx += 1
                origin_x = origin_x + sheet.width + self.SHEET_GAP
                col_x = origin_x + sheet.inner_left + 10.0
                y_cursor = sheet.height - sheet.margin - 10.0
                col_width = 0.0

            if sheet_idx not in frame_drawn_for_sheet:
                self._draw_sheet_frame(msp, origin_x, 0.0, sheet, "SEZ_FRAME")
                title = f"Sezioni trasversali | Tavola {sheet_idx + 1}"
                msp.add_text(title, dxfattribs={"height": 6.0, "layer": "SEZ_TEXT"}).set_placement(
                    (origin_x + sheet.inner_left + 12.0, sheet.height - sheet.margin - 6.0)
                )
                frame_drawn_for_sheet.add(sheet_idx)

            x0 = col_x
            y0 = y_cursor - h
            self._draw_single_section_cartiglio(msp, item, x0, y0, min_width)
            y_cursor = y0 - 10.0
            col_width = max(col_width, w)

    def _prepare_section_layout(
        self, section: SectionData, quote_step_m: float, z_exaggeration: float, section_h_scale: float
    ) -> Optional[dict]:
        if not section.offsets or not section.terrain_z or not section.project_z:
            return None
        x_min = min(section.offsets)
        x_max = max(section.offsets)
        z_vals = [z for z in section.terrain_z + section.project_z if math.isfinite(z)]
        if not z_vals:
            return None
        z_min = min(z_vals)
        z_max = max(z_vals)

        graph_w = max(120.0, (x_max - x_min) * 1000.0 / section_h_scale + 20.0)
        graph_h = max(70.0, (z_max - z_min) * 1000.0 / section_h_scale * z_exaggeration + 20.0)
        head_h = 22.0
        table_h = 44.0
        cart_w = graph_w + 16.0
        cart_h = head_h + graph_h + table_h + 12.0
        points = self._build_quote_points(section, quote_step_m)
        return {
            "section": section,
            "x_min": x_min,
            "x_max": x_max,
            "z_min": z_min,
            "z_max": z_max,
            "graph_w": graph_w,
            "graph_h": graph_h,
            "head_h": head_h,
            "table_h": table_h,
            "cart_w": cart_w,
            "cart_h": cart_h,
            "z_exaggeration": z_exaggeration,
            "section_h_scale": section_h_scale,
            "points": points,
        }

    def _draw_single_section_cartiglio(self, msp, item: dict, x0: float, y0: float, min_width: float) -> None:
        sec = item["section"]
        x1 = x0 + item["cart_w"]
        y1 = y0 + item["cart_h"]
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], dxfattribs={"layer": "SEZ_FRAME", "closed": True})

        graph_left = x0 + 8.0
        graph_right = x1 - 8.0
        graph_bottom = y0 + item["table_h"] + 6.0
        graph_top = y1 - item["head_h"] - 4.0
        msp.add_lwpolyline(
            [(graph_left, graph_bottom), (graph_right, graph_bottom), (graph_right, graph_top), (graph_left, graph_top), (graph_left, graph_bottom)],
            dxfattribs={"layer": "SEZ_FRAME", "closed": True},
        )

        axis_i = min(range(len(sec.offsets)), key=lambda i: abs(sec.offsets[i]))
        axis_t = sec.terrain_z[axis_i]
        axis_p = sec.project_z[axis_i]
        hdr = (
            f"Sez {sec.index} | Prog {sec.progressive:.2f} | Tasse {axis_t:.2f} | Passe {axis_p:.2f} | "
            f"Scala H 1:{int(item['section_h_scale'])} Vx{item['z_exaggeration']:.2f}"
        )
        msp.add_text(hdr, dxfattribs={"height": 2.4, "layer": "SEZ_TEXT"}).set_placement((x0 + 4.0, y1 - 7.0))
        if min_width > 0:
            msp.add_text(f"Wmin {min_width:.2f}", dxfattribs={"height": 2.0, "layer": "SEZ_TEXT"}).set_placement((x1 - 35.0, y1 - 12.0))

        x_span = max(1e-6, item["x_max"] - item["x_min"])
        z_span = max(1e-6, item["z_max"] - item["z_min"])

        def map_pt(off: float, z: float) -> tuple[float, float]:
            x = graph_left + (off - item["x_min"]) / x_span * (graph_right - graph_left)
            y = graph_bottom + (z - item["z_min"]) / z_span * (graph_top - graph_bottom)
            return x, y

        terr = [map_pt(o, z) for o, z in zip(sec.offsets, sec.terrain_z)]
        proj = [map_pt(o, z) for o, z in zip(sec.offsets, sec.project_z)]
        core = [map_pt(o, z) for o, z in zip(sec.offsets, sec.road_core_z)] if sec.road_core_z else []
        if len(terr) >= 2:
            msp.add_lwpolyline(terr, dxfattribs={"layer": "SEZ_TERRAIN"})
        if len(proj) >= 2:
            msp.add_lwpolyline(proj, dxfattribs={"layer": "SEZ_PROJECT"})
        if len(core) >= 2:
            msp.add_lwpolyline(core, dxfattribs={"layer": "SEZ_ROAD_CORE"})

        pad = self._build_pad_polyline(sec)
        if len(pad) >= 2:
            msp.add_lwpolyline([map_pt(o, z) for o, z in pad], dxfattribs={"layer": "SEZ_PAD"})
        ls = self._build_slope_segment(sec, left=True)
        rs = self._build_slope_segment(sec, left=False)
        if len(ls) == 2:
            msp.add_lwpolyline([map_pt(*ls[0]), map_pt(*ls[1])], dxfattribs={"layer": "SEZ_SLOPES"})
        if len(rs) == 2:
            msp.add_lwpolyline([map_pt(*rs[0]), map_pt(*rs[1])], dxfattribs={"layer": "SEZ_SLOPES"})

        ax0, ay0 = map_pt(0.0, item["z_min"])
        _, ay1 = map_pt(0.0, item["z_max"])
        msp.add_line((ax0, ay0), (ax0, ay1), dxfattribs={"layer": "SEZ_AXIS"})

        table_top = y0 + item["table_h"] + 2.0
        table_bottom = y0 + 3.0
        table_data = self._draw_section_table(msp, item["points"], x0 + 8.0, x1 - 8.0, table_top, table_bottom)
        point_anchor = {round(p["offset"], 6): p["x"] for p in table_data["points"]}
        for p in item["points"]:
            anchor_x = point_anchor.get(round(p["offset"], 6))
            if anchor_x is None:
                continue
            z_ref = p["project_z"] if math.isfinite(p["project_z"]) else p["terrain_z"]
            if not math.isfinite(z_ref):
                continue
            px, py = map_pt(p["offset"], z_ref)
            if abs(anchor_x - px) <= 1e-6:
                msp.add_line((px, py), (px, table_top), dxfattribs={"layer": "SEZ_TABLE"})
            else:
                msp.add_lwpolyline([(px, py), (px, table_top), (anchor_x, table_top)], dxfattribs={"layer": "SEZ_TABLE"})

    def _draw_section_table(self, msp, points: List[dict], left: float, right: float, top: float, bottom: float) -> dict:
        rows = ["OFFSET", "TERRENO", "PROGETTO"]
        label_w = 22.0
        available_w = max(10.0, right - left - label_w)
        points = self._reduce_quote_points_for_width(points, available_w)
        n = max(1, len(points))
        row_h = (top - bottom) / len(rows)
        col_w = available_w / n
        table_right = left + label_w + available_w
        text_h = max(1.2, min(1.8, col_w * 0.28))

        msp.add_lwpolyline(
            [(left, top), (table_right, top), (table_right, bottom), (left, bottom), (left, top)],
            dxfattribs={"layer": "SEZ_TABLE", "closed": True},
        )
        msp.add_line((left + label_w, top), (left + label_w, bottom), dxfattribs={"layer": "SEZ_TABLE"})
        for ridx in range(1, len(rows)):
            y = top - ridx * row_h
            msp.add_line((left, y), (table_right, y), dxfattribs={"layer": "SEZ_TABLE"})
        for c in range(1, n):
            x = left + label_w + c * col_w
            msp.add_line((x, top), (x, bottom), dxfattribs={"layer": "SEZ_TABLE"})

        for ridx, row in enumerate(rows):
            y = top - (ridx + 0.7) * row_h
            msp.add_text(row, dxfattribs={"height": text_h, "layer": "SEZ_TEXT"}).set_placement((left + 0.8, y))

        point_positions = []
        for cidx, p in enumerate(points):
            x = left + label_w + (cidx + 0.5) * col_w
            point_positions.append({"offset": p["offset"], "x": x})
            vals = [
                f"{p['offset']:.2f}",
                f"{p['terrain_z']:.2f}" if math.isfinite(p["terrain_z"]) else "-",
                f"{p['project_z']:.2f}" if math.isfinite(p["project_z"]) else "-",
            ]
            for ridx, val in enumerate(vals):
                y = top - (ridx + 0.7) * row_h
                msp.add_text(val, dxfattribs={"height": text_h, "layer": "SEZ_TEXT"}).set_placement((x, y), align="MIDDLE_CENTER")
        return {"points": point_positions}

    def _reduce_quote_points_for_width(self, points: List[dict], available_w: float) -> List[dict]:
        if not points:
            return points
        min_col_w = 8.0
        max_points = max(1, int(available_w / min_col_w))
        if len(points) <= max_points:
            return points
        axis_idx = min(range(len(points)), key=lambda i: abs(points[i]["offset"]))
        stride = int(math.ceil(len(points) / max_points))
        keep_idx = {0, len(points) - 1, axis_idx}
        keep_idx.update(range(0, len(points), stride))
        reduced = [p for idx, p in enumerate(points) if idx in keep_idx]
        reduced.sort(key=lambda p: p["offset"])
        return reduced

    def _build_quote_points(self, section: SectionData, quote_step_m: float) -> List[dict]:
        if not section.offsets:
            return []
        left = section.offsets[0]
        right = section.offsets[-1]
        offsets = {0.0, left, right}
        if section.width_info is not None:
            offsets.update(
                {
                    -section.width_info.left_width,
                    section.width_info.right_width,
                }
            )
        for extra in (
            section.side_slope_left_outer_offset,
            section.side_slope_right_outer_offset,
            section.left_slope_hit_offset,
            section.right_slope_hit_offset,
        ):
            if extra is not None and math.isfinite(extra):
                offsets.add(extra)

        off = 0.0
        while off <= right:
            offsets.add(round(off, 6))
            off += quote_step_m
        off = 0.0
        while off >= left:
            offsets.add(round(off, 6))
            off -= quote_step_m

        result = []
        for off in sorted(o for o in offsets if left <= o <= right):
            terr = self._interp_piecewise(section.offsets, section.terrain_z, off)
            proj = self._interp_piecewise(section.offsets, section.project_z, off)
            result.append({"offset": off, "terrain_z": terr, "project_z": proj})
        return result

    def _build_slope_segment(self, section: SectionData, left: bool) -> list[tuple[float, float]]:
        if not section.offsets or not section.project_z or section.width_info is None:
            return []
        edge_off = -section.width_info.left_width if left else section.width_info.right_width
        outer_off = section.side_slope_left_outer_offset if left else section.side_slope_right_outer_offset
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
        return [(edge_off, edge_z), (outer_off, outer_z)]

    def _build_pad_polyline(self, section: SectionData) -> list[tuple[float, float]]:
        if not section.offsets or not section.project_z or section.width_info is None:
            return []
        left = -section.width_info.left_width
        right = section.width_info.right_width
        return [(off, z) for off, z in zip(section.offsets, section.project_z) if left <= off <= right and math.isfinite(z)]

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
