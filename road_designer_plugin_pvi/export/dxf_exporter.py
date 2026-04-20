from __future__ import annotations

import math
import traceback
import logging
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
    _logger = logging.getLogger(__name__)
    DEFAULT_Z_EXAGGERATION = 2.0
    PROFILE_H_SCALE = 1000.0
    PROFILE_V_SCALE = 200.0
    SECTION_H_SCALE = 200.0
    SHEET_GAP = 120.0
    OFFSET_DUPLICATE_TOL = 1e-4

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
        max_cartigli_per_sheet: int = 6,
    ) -> str:
        doc = self._new_doc()
        msp = doc.modelspace()
        self._ensure_layers(doc, self.PROFILE_LAYERS + self.SECTION_LAYERS)

        sheet = SheetSpec()
        profile_sheet_count = 0
        if profile and profile.progressive:
            try:
                profile_sheet_count = self._draw_profile_sheets(
                    msp,
                    sheet,
                    profile,
                    sections,
                    profile_h_scale=max(1.0, profile_h_scale),
                    profile_v_scale=max(1.0, profile_v_scale),
                )
            except Exception as exc:
                self._log_export_exception(
                    phase="draw_profile_sheets",
                    sheet_type="profile",
                    sheet_index=None,
                    section=None,
                    exc=exc,
                )

        section_origin_x = profile_sheet_count * (sheet.width + self.SHEET_GAP)
        try:
            self._draw_section_sheets(
                msp,
                sheet,
                sections,
                section_origin_x,
                quote_step_m=max(0.1, quote_step_m),
                z_exaggeration=max(0.01, section_z_exaggeration),
                section_h_scale=max(1.0, section_h_scale),
                min_width=min_width,
                max_cartigli_per_sheet=max(1, int(max_cartigli_per_sheet)),
            )
        except Exception as exc:
            self._log_export_exception(
                phase="draw_section_sheets",
                sheet_type="sections",
                sheet_index=None,
                section=None,
                exc=exc,
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
        max_cartigli_per_sheet: int = 6,
    ) -> str:
        return self.export_all_layout(
            path=path,
            profile=None,
            sections=sections,
            quote_step_m=1.0,
            section_z_exaggeration=z_exaggeration,
            min_width=min_width,
            max_cartigli_per_sheet=max_cartigli_per_sheet,
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
        msp.add_lwpolyline(outer, close=True, dxfattribs={"layer": layer})
        msp.add_lwpolyline(inner, close=True, dxfattribs={"layer": layer})
        msp.add_lwpolyline(band, close=True, dxfattribs={"layer": layer})

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
            graph_top = usable_top - 90.0

            s_prog = p0 + idx * span_per_sheet
            e_prog = min(p1, s_prog + span_per_sheet)
            title = f"PROFILO LONGITUDINALE - Tavola {idx + 1}/{sheet_count}"
            scale_txt = f"Scala H 1:{int(profile_h_scale)}   V 1:{int(profile_v_scale)}"
            msp.add_text(title, dxfattribs={"height": 6.4, "layer": "PROF_TEXT"}).set_placement((graph_left, usable_top - 20.0))
            msp.add_text(scale_txt, dxfattribs={"height": 3.8, "layer": "PROF_TEXT"}).set_placement((graph_left, usable_top - 33.0))
            msp.add_text(
                f"Progressive {s_prog:.2f} - {e_prog:.2f} m",
                dxfattribs={"height": 3.2, "layer": "PROF_TEXT"},
            ).set_placement((graph_left, usable_top - 43.0))

            horizontal_mm_per_m = 1000.0 / max(1.0, profile_h_scale)
            vertical_mm_per_m = 1000.0 / max(1.0, profile_v_scale)
            local_terr = [z for p, z in zip(profile.progressive, profile.terrain_z) if s_prog <= p <= e_prog and math.isfinite(z)]
            local_proj = [z for p, z in zip(profile.progressive, profile.project_z) if s_prog <= p <= e_prog and math.isfinite(z)]
            local_z = local_terr + local_proj
            if local_z:
                z_min_local = min(local_z)
                z_max_local = max(local_z)
            else:
                z_min_local = min_z
                z_max_local = min_z + 1.0
            # Trasformazione metrica reale: nessun fit verticale al box.
            # z_ref serve solo come traslazione; la scala V resta fissa (1:profile_v_scale).
            vertical_capacity_m = (graph_top - graph_bottom) / max(1e-9, vertical_mm_per_m)
            z_ref = math.floor(z_min_local * 2.0) / 2.0
            if z_max_local - z_ref > vertical_capacity_m:
                z_ref = z_max_local - vertical_capacity_m

            def map_point(p: float, z: float) -> tuple[float, float]:
                x, y = self._map_profile_point_to_sheet(
                    progressive=p,
                    elevation=z,
                    sheet_prog_start=s_prog,
                    z_ref=z_ref,
                    graph_left=graph_left,
                    graph_bottom=graph_bottom,
                    h_mm_per_m=horizontal_mm_per_m,
                    v_mm_per_m=vertical_mm_per_m,
                )
                return x, max(graph_bottom, min(graph_top, y))

            terr_pts = [map_point(p, z) for p, z in zip(profile.progressive, profile.terrain_z) if s_prog <= p <= e_prog]
            proj_pts = [map_point(p, z) for p, z in zip(profile.progressive, profile.project_z) if s_prog <= p <= e_prog]
            if len(terr_pts) >= 2:
                msp.add_lwpolyline(terr_pts, dxfattribs={"layer": "PROF_TERRAIN"})
            if len(proj_pts) >= 2:
                msp.add_lwpolyline(proj_pts, dxfattribs={"layer": "PROF_PROJECT"})
            msp.add_lwpolyline(
                [(graph_left, graph_bottom), (graph_right, graph_bottom), (graph_right, graph_top), (graph_left, graph_top), (graph_left, graph_bottom)],
                close=True,
                dxfattribs={"layer": "PROF_FRAME"},
            )

            marks = []
            for sec in sorted((s for s in sections if s_prog <= s.progressive <= e_prog), key=lambda item: item.progressive):
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
                msp.add_text(f"S{sec.index}", dxfattribs={"height": 2.4, "layer": "PROF_TEXT"}).set_placement((x + 1.0, graph_top + 3.0))

            self._draw_profile_table(msp, marks, graph_left, graph_right, table_top, usable_bottom + 20.0)
        return sheet_count

    def _map_profile_point_to_sheet(
        self,
        progressive: float,
        elevation: float,
        sheet_prog_start: float,
        z_ref: float,
        graph_left: float,
        graph_bottom: float,
        h_mm_per_m: float,
        v_mm_per_m: float,
    ) -> tuple[float, float]:
        x = graph_left + (progressive - sheet_prog_start) * h_mm_per_m
        y = graph_bottom + (elevation - z_ref) * v_mm_per_m
        return x, y

    def _draw_profile_table(self, msp, marks: List[dict], left: float, right: float, top: float, bottom: float) -> None:
        rows = ["SEZIONE", "PROGRESSIVA", "QUOTA TERRENO", "QUOTA PROGETTO"]
        height = top - bottom
        row_h = max(6.0, height / max(1, len(rows)))
        label_w = 52.0
        table_left = left
        col_left = table_left + label_w
        table_right = right
        text_h = max(2.4, min(3.2, row_h * 0.42))

        msp.add_lwpolyline(
            [
                (table_left, top),
                (table_right, top),
                (table_right, bottom),
                (table_left, bottom),
                (table_left, top),
            ],
            close=True,
            dxfattribs={"layer": "PROF_TABLE"},
        )
        msp.add_line((col_left, top), (col_left, bottom), dxfattribs={"layer": "PROF_TABLE"})

        for ridx in range(1, len(rows)):
            y = top - ridx * row_h
            msp.add_line((table_left, y), (table_right, y), dxfattribs={"layer": "PROF_TABLE"})

        x_positions = sorted([max(col_left, min(table_right, m["x"])) for m in marks])
        boundaries = [col_left]
        if x_positions:
            boundaries.extend((x_positions[i] + x_positions[i + 1]) * 0.5 for i in range(len(x_positions) - 1))
            boundaries.append(table_right)
            for x in boundaries[1:-1]:
                msp.add_line((x, top), (x, bottom), dxfattribs={"layer": "PROF_TABLE"})
        else:
            boundaries.append(table_right)

        for ridx, label in enumerate(rows):
            y = top - (ridx + 0.68) * row_h
            try:
                txt = msp.add_text(label, dxfattribs={"height": text_h, "layer": "PROF_TEXT"})
                txt.set_placement((table_left + 1.5, y))
            except Exception:
                pass

        for idx, m in enumerate(marks):
            sec = m["section"]
            if idx < len(boundaries) - 1:
                x = (boundaries[idx] + boundaries[idx + 1]) * 0.5
            else:
                x = max(col_left, min(table_right, m["x"]))

            values = [
                f"S{sec.index}",
                f"{sec.progressive:.2f}",
                f"{m['terrain_z']:.2f}",
                f"{m['project_z']:.2f}",
            ]

            for ridx, val in enumerate(values):
                y = top - (ridx + 0.68) * row_h
                try:
                    txt = msp.add_text(val, dxfattribs={"height": text_h, "layer": "PROF_TEXT"})
                    txt.set_placement((x - text_h * 1.0, y))
                except Exception:
                    pass

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
        max_cartigli_per_sheet: int,
    ) -> None:
        if not sections:
            return

        prepared = [self._prepare_section_layout(s, quote_step_m, z_exaggeration, section_h_scale) for s in sections]
        prepared = [p for p in prepared if p]
        if not prepared:
            self._logger.warning("No section layouts available after preparation; no section sheets will be drawn.")
            return

        content_pad = 12.0
        row_gap = 18.0
        sheet_idx = 0

        def sheet_origin(idx: int) -> float:
            return origin_x + idx * (sheet.width + self.SHEET_GAP)

        def draw_sheet(idx: int) -> None:
            current_origin_x = sheet_origin(idx)
            self._draw_sheet_frame(msp, current_origin_x, 0.0, sheet, "SEZ_FRAME")
            title = f"Sezioni trasversali | Tavola {idx + 1}"
            msp.add_text(title, dxfattribs={"height": 6.0, "layer": "SEZ_TEXT"}).set_placement(
                (current_origin_x + sheet.inner_left + 12.0, sheet.height - sheet.margin - 6.0)
            )

        i = 0
        while i < len(prepared):
            draw_sheet(sheet_idx)
            current_origin_x = sheet_origin(sheet_idx)
            usable_left = current_origin_x + sheet.inner_left + content_pad
            usable_right = current_origin_x + sheet.inner_left + sheet.usable_width - content_pad
            usable_top = sheet.inner_bottom + sheet.inner_height - content_pad - 16.0
            usable_bottom = sheet.inner_bottom + content_pad
            usable_width = usable_right - usable_left
            usable_height = usable_top - usable_bottom
            page_plan = self._build_section_page_plan(
                prepared=prepared,
                start_idx=i,
                usable_left=usable_left,
                usable_right=usable_right,
                usable_bottom=usable_bottom,
                usable_top=usable_top,
                row_gap=row_gap,
                max_cartigli_per_sheet=max_cartigli_per_sheet,
            )
            if not page_plan["placements"]:
                sec = prepared[i].get("section")
                self._logger.warning(
                    "Section cartiglio still too large after compaction; skipped | section=%s | cart=(%.2f, %.2f) | usable=(%.2f, %.2f)",
                    getattr(sec, "index", None),
                    prepared[i]["cart_w"],
                    prepared[i]["cart_h"],
                    usable_width,
                    usable_height,
                )
                i += 1
                sheet_idx += 1
                continue

            for placement in page_plan["placements"]:
                item = placement["item"]
                sec = item.get("section")
                x0 = placement["x0"]
                y0 = placement["y0"]
                if (
                    x0 < usable_left
                    or (x0 + item["cart_w"]) > usable_right
                    or y0 < usable_bottom
                    or (y0 + item["cart_h"]) > usable_top
                ):
                    self._logger.error(
                        "Page-plan bounds violation blocked | section=%s | x0=%.2f y0=%.2f w=%.2f h=%.2f | usable=[%.2f, %.2f, %.2f, %.2f]",
                        getattr(sec, "index", None),
                        x0,
                        y0,
                        item["cart_w"],
                        item["cart_h"],
                        usable_left,
                        usable_right,
                        usable_bottom,
                        usable_top,
                    )
                    continue
                try:
                    self._draw_single_section_cartiglio(msp, item, x0, y0, min_width)
                except Exception as exc:
                    self._log_section_exception(
                        section=sec,
                        step="section_cartiglio",
                        phase="draw_section_sheet",
                        sheet_type="sections",
                        sheet_index=sheet_idx,
                        exc=exc,
                    )
            i = page_plan["next_idx"]
            sheet_idx += 1

    def _build_section_page_plan(
        self,
        prepared: List[dict],
        start_idx: int,
        usable_left: float,
        usable_right: float,
        usable_bottom: float,
        usable_top: float,
        row_gap: float,
        max_cartigli_per_sheet: int,
    ) -> dict:
        usable_width = max(1.0, usable_right - usable_left)
        usable_height = max(1.0, usable_top - usable_bottom)
        max_items = max(1, max_cartigli_per_sheet)
        candidate_items: List[dict] = []
        idx = start_idx
        while idx < len(prepared) and len(candidate_items) < max_items:
            src_item = prepared[idx]
            item, resized = self._compact_layout_to_fit(src_item, usable_width, usable_height)
            if not item:
                if not candidate_items:
                    self._logger.warning(
                        "Forced dedicated sheet but cartiglio cannot fit even after width reduction | section=%s | usable=(%.2f, %.2f)",
                        getattr(src_item.get("section"), "index", None),
                        usable_width,
                        usable_height,
                    )
                    return {"placements": [], "next_idx": idx + 1}
                self._logger.info(
                    "Section moved to dedicated sheet due to size overflow in current plan | section=%s",
                    getattr(src_item.get("section"), "index", None),
                )
                break
            if resized:
                self._logger.info(
                    "Section cartiglio width reduced for pagination | section=%s | old=(%.2f, %.2f) new=(%.2f, %.2f)",
                    getattr(src_item.get("section"), "index", None),
                    src_item["cart_w"],
                    src_item["cart_h"],
                    item["cart_w"],
                    item["cart_h"],
                )
            candidate_items.append(item)
            idx += 1

        if not candidate_items:
            return {"placements": [], "next_idx": start_idx}

        valid_plans: List[dict] = []
        max_cols_reasonable = min(3, len(candidate_items))
        for n in range(1, len(candidate_items) + 1):
            subset = candidate_items[:n]
            for cols in range(1, min(n, max_cols_reasonable) + 1):
                rows = int(math.ceil(n / cols))
                slot_w = usable_width / cols
                slot_h = (usable_height - row_gap * (rows - 1)) / rows
                if slot_w <= 0.0 or slot_h <= 0.0:
                    continue
                if any(item["cart_w"] > slot_w or item["cart_h"] > slot_h for item in subset):
                    continue

                placements = []
                for k, item in enumerate(subset):
                    r = k // cols
                    c = k % cols
                    slot_left = usable_left + c * slot_w
                    slot_top = usable_top - r * (slot_h + row_gap)
                    x0 = slot_left + (slot_w - item["cart_w"]) * 0.5
                    y0 = slot_top - slot_h + (slot_h - item["cart_h"]) * 0.5
                    placements.append({"item": item, "x0": x0, "y0": y0})

                occupied_w = max(item["cart_w"] for item in subset) * cols
                occupied_h = max(item["cart_h"] for item in subset) * rows + row_gap * (rows - 1)
                occupancy = (occupied_w * occupied_h) / max(1.0, usable_width * usable_height)
                valid_plans.append(
                    {
                        "n": n,
                        "rows": rows,
                        "cols": cols,
                        "slot_w": slot_w,
                        "slot_h": slot_h,
                        "placements": placements,
                        "occupancy": occupancy,
                    }
                )

        self._logger.debug(
            "Section page-plan candidates | start_idx=%s | candidate_cartigli=%s | valid_solutions=%s",
            start_idx,
            len(candidate_items),
            len(valid_plans),
        )
        if not valid_plans:
            return {"placements": [], "next_idx": start_idx}

        def plan_score(plan: dict) -> tuple:
            single_col_penalty = 1 if (plan["cols"] == 1 and any(p["cols"] >= 2 and p["n"] == plan["n"] for p in valid_plans)) else 0
            return (
                plan["n"],
                -single_col_penalty,
                plan["cols"],
                plan["occupancy"],
                -abs(plan["rows"] - plan["cols"]),
            )

        best = max(valid_plans, key=plan_score)
        reason = (
            f"preferred cols={best['cols']} with n={best['n']} and occupancy={best['occupancy']:.3f}; "
            f"balanced grid rows={best['rows']}"
        )
        self._logger.debug(
            "Section page-plan chosen | rows=%s cols=%s slot_w=%.2f slot_h=%.2f | reason=%s",
            best["rows"],
            best["cols"],
            best["slot_w"],
            best["slot_h"],
            reason,
        )
        return {"placements": best["placements"], "next_idx": start_idx + best["n"]}

    def _compact_layout_to_fit(self, item: dict, max_w: float, max_h: float) -> tuple[Optional[dict], bool]:
        if item["cart_w"] <= max_w and item["cart_h"] <= max_h:
            return item, False
        variants = [
            (26.0, 10.0, 7.0),
            (22.0, 8.0, 6.0),
            (18.0, 7.0, 5.0),
        ]
        for table_label_w, table_col_min_w, min_anchor_dx in variants:
            candidate = self._rebuild_item_layout(item, table_label_w, table_col_min_w, min_anchor_dx)
            if candidate["cart_w"] <= max_w and candidate["cart_h"] <= max_h:
                return candidate, True
        return None, False

    def _rebuild_item_layout(self, item: dict, table_label_w: float, table_col_min_w: float, min_anchor_dx: float) -> dict:
        rebuilt = dict(item)
        layout = self._build_section_cartiglio_layout_model(
            x_min=item["x_min"],
            x_max=item["x_max"],
            z_min=item["z_min"],
            z_max=item["z_max"],
            points=item["points"],
            section_h_scale=item["section_h_scale"],
            z_exaggeration=item["z_exaggeration"],
            table_label_w=table_label_w,
            table_col_min_w=table_col_min_w,
            min_anchor_dx=min_anchor_dx,
        )
        rebuilt.update(
            {
                "graph_w": layout["graph_w"],
                "graph_h": layout["graph_h"],
                "head_h": layout["head_h"],
                "table_h": layout["table_h"],
                "table_w": layout["table_w"],
                "cart_w": layout["cart_w"],
                "cart_h": layout["cart_h"],
                "layout": layout,
            }
        )
        return rebuilt

    def _prepare_section_layout(
        self, section: SectionData, quote_step_m: float, z_exaggeration: float, section_h_scale: float
    ) -> Optional[dict]:
        if not section.offsets or not section.terrain_z or not section.project_z:
            self._logger.warning(
                "Section discarded during layout preparation: missing mandatory arrays | section=%s",
                getattr(section, "index", None),
            )
            return None
        offsets = [o for o in section.offsets if math.isfinite(o)]
        if len(offsets) < 2:
            self._logger.warning(
                "Section discarded during layout preparation: less than 2 finite offsets | section=%s",
                getattr(section, "index", None),
            )
            return None
        x_min = min(offsets)
        x_max = max(offsets)
        z_vals = [z for z in section.terrain_z + section.project_z if math.isfinite(z)]
        if not z_vals:
            self._logger.warning(
                "Section discarded during layout preparation: no finite elevations | section=%s",
                getattr(section, "index", None),
            )
            return None
        z_min = min(z_vals)
        z_max = max(z_vals)
        points = self._build_quote_points(section, quote_step_m)
        layout = self._build_section_cartiglio_layout_model(
            x_min=x_min,
            x_max=x_max,
            z_min=z_min,
            z_max=z_max,
            points=points,
            section_h_scale=section_h_scale,
            z_exaggeration=z_exaggeration,
        )
        graph_w = layout["graph_w"]
        graph_h = layout["graph_h"]
        table_w = layout["table_w"]
        table_h = layout["table_h"]
        cart_w = layout["cart_w"]
        cart_h = layout["cart_h"]
        if not all(math.isfinite(v) and v > 0 for v in (graph_w, graph_h, table_h, table_w, cart_w, cart_h)):
            self._logger.warning(
                "Section discarded during layout preparation: non-positive/non-finite layout dimensions | section=%s | dims=%s",
                getattr(section, "index", None),
                (graph_w, graph_h, table_h, table_w, cart_w, cart_h),
            )
            return None
        return {
            "section": section,
            "x_min": x_min,
            "x_max": x_max,
            "z_min": z_min,
            "z_max": z_max,
            "graph_w": graph_w,
            "graph_h": graph_h,
            "head_h": layout["head_h"],
            "table_h": table_h,
            "table_w": table_w,
            "cart_w": cart_w,
            "cart_h": cart_h,
            "z_exaggeration": z_exaggeration,
            "section_h_scale": section_h_scale,
            "points": points,
            "layout": layout,
        }

    def _draw_single_section_cartiglio(self, msp, item: dict, x0: float, y0: float, min_width: float) -> None:
        sec = item["section"]
        current_step = "frame/cartiglio drawing"
        x1 = x0 + item["cart_w"]
        y1 = y0 + item["cart_h"]
        self._safe_add_polyline(
            msp,
            [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
            layer="SEZ_FRAME",
            closed=True,
            section=sec,
            step=current_step,
        )

        layout = item.get("layout", {})
        side_pad = float(layout.get("side_pad", 12.0))
        top_pad = float(layout.get("top_pad", 8.0))
        bottom_pad = float(layout.get("bottom_pad", 8.0))
        inter_block_gap = float(layout.get("inter_block_gap", 6.0))
        graph_extra_bottom = float(layout.get("graph_extra_bottom", 8.0))
        content_w = float(layout.get("content_w", max(item["graph_w"], item.get("table_w", item["graph_w"]))))
        table_w = float(layout.get("table_w", item.get("table_w", item["graph_w"])))
        table_h = float(layout.get("table_h", item["table_h"]))
        graph_w = float(layout.get("graph_w", item["graph_w"]))
        graph_h = float(layout.get("graph_h", item["graph_h"]))
        plot_w = float(layout.get("plot_w", graph_w))
        plot_h = float(layout.get("plot_h", graph_h))

        content_left = x0 + side_pad
        content_right = min(x1 - side_pad, content_left + content_w)
        table_bottom = y0 + bottom_pad
        table_top = table_bottom + table_h
        min_table_h = 20.0
        if (table_top - table_bottom) < min_table_h:
            table_top = table_bottom + min_table_h
        graph_bottom = table_top + inter_block_gap + graph_extra_bottom
        graph_top = graph_bottom + graph_h
        max_graph_top = y1 - top_pad - layout.get("head_h", item["head_h"]) - inter_block_gap
        if graph_top > max_graph_top:
            graph_top = max(graph_bottom + 20.0, max_graph_top)
        available_graph_h = max(20.0, graph_top - graph_bottom)
        if abs(available_graph_h - graph_h) > 1e-6:
            graph_h = available_graph_h
            graph_top = graph_bottom + graph_h
        graph_left = content_left
        graph_right = min(content_right, graph_left + graph_w)
        graph_w = max(1e-6, graph_right - graph_left)
        plot_w = min(plot_w, graph_w)
        plot_h = min(plot_h, graph_h)
        plot_left = graph_left + (graph_w - plot_w) * 0.5
        plot_bottom = graph_bottom + (graph_h - plot_h) * 0.5
        plot_right = plot_left + plot_w
        plot_top = plot_bottom + plot_h
        self._logger.debug(
            "Section cartiglio layout sec=%s table_bottom=%.2f table_top=%.2f graph_bottom=%.2f graph_top=%.2f plot_w=%.2f plot_h=%.2f",
            sec.index,
            table_bottom,
            table_top,
            graph_bottom,
            graph_top,
            plot_w,
            plot_h,
        )

        self._safe_add_polyline(
            msp,
            [(graph_left, graph_bottom), (graph_right, graph_bottom), (graph_right, graph_top), (graph_left, graph_top), (graph_left, graph_bottom)],
            layer="SEZ_FRAME",
            closed=True,
            section=sec,
            step=current_step,
        )
        self._safe_add_polyline(
            msp,
            [(plot_left, plot_bottom), (plot_right, plot_bottom), (plot_right, plot_top), (plot_left, plot_top), (plot_left, plot_bottom)],
            layer="SEZ_AXIS",
            closed=True,
            section=sec,
            step=current_step,
        )

        axis_i = min(range(len(sec.offsets)), key=lambda i: abs(sec.offsets[i]))
        axis_t = sec.terrain_z[axis_i]
        axis_p = sec.project_z[axis_i]
        v_scale = float(layout.get("v_scale", item["section_h_scale"] / max(1e-6, item["z_exaggeration"])))
        current_step = "text drawing"
        header_y = y1 - top_pad - 3.0
        line1 = f"SEZIONE {sec.index}    PROG {sec.progressive:.2f} m"
        line2 = (
            f"T terreno {axis_t:.2f}   P progetto {axis_p:.2f}   "
            f"Scala H 1:{int(item['section_h_scale'])}   V 1:{int(round(v_scale))}"
        )
        try:
            msp.add_text(line1, dxfattribs={"height": 3.0, "layer": "SEZ_TEXT"}).set_placement((content_left, header_y))
            msp.add_text(line2, dxfattribs={"height": 2.2, "layer": "SEZ_TEXT"}).set_placement((content_left, header_y - 4.5))
        except Exception as exc:
            self._log_section_exception(section=sec, step="header_text", exc=exc)

        if min_width > 0:
            wmin_x = x1 - side_pad - 42.0
            wmin_y = max(graph_top + 2.0, header_y - 6.0)
            try:
                msp.add_text(f"Wmin {min_width:.2f}", dxfattribs={"height": 2.0, "layer": "SEZ_TEXT"}).set_placement((wmin_x, wmin_y))
            except Exception as exc:
                self._log_section_exception(section=sec, step="wmin_text", exc=exc)

        x_span = max(1e-6, item["x_max"] - item["x_min"])
        z_span = max(1e-6, item["z_max"] - item["z_min"])

        def map_pt(off: float, z: float) -> tuple[float, float]:
            x = plot_left + (off - item["x_min"]) / x_span * plot_w
            y = plot_bottom + (z - item["z_min"]) / z_span * plot_h
            return x, y

        current_step = "terrain polyline drawing"
        terr_raw = self._sanitize_offset_polyline(sec, sec.offsets, sec.terrain_z, "terrain")
        terr = [map_pt(o, z) for o, z in terr_raw]
        self._safe_add_polyline(msp, terr, layer="SEZ_TERRAIN", section=sec, step=current_step)

        current_step = "project polyline drawing"
        proj_raw = self._sanitize_offset_polyline(sec, sec.offsets, sec.project_z, "project")
        proj = [map_pt(o, z) for o, z in proj_raw]
        self._safe_add_polyline(msp, proj, layer="SEZ_PROJECT", section=sec, step=current_step)

        current_step = "road core polyline drawing"
        core_raw = self._sanitize_offset_polyline(sec, sec.offsets, sec.road_core_z, "road_core") if sec.road_core_z else []
        core = [map_pt(o, z) for o, z in core_raw]
        self._safe_add_polyline(msp, core, layer="SEZ_ROAD_CORE", section=sec, step=current_step)

        current_step = "slopes drawing"
        pad = self._build_pad_polyline(sec)
        self._safe_add_polyline(
            msp,
            [map_pt(o, z) for o, z in pad if math.isfinite(o) and math.isfinite(z)],
            layer="SEZ_PAD",
            section=sec,
            step=current_step,
        )
        ls = self._get_slope_segment_points(sec, left=True)
        rs = self._get_slope_segment_points(sec, left=False)
        self._safe_add_polyline(
            msp,
            [map_pt(o, z) for o, z in ls],
            layer="SEZ_SLOPES",
            section=sec,
            step=current_step,
        )
        self._safe_add_polyline(
            msp,
            [map_pt(o, z) for o, z in rs],
            layer="SEZ_SLOPES",
            section=sec,
            step=current_step,
        )

        current_step = "axis drawing"
        ax0, ay0 = map_pt(0.0, item["z_min"])
        _, ay1 = map_pt(0.0, item["z_max"])
        if self._is_valid_point((ax0, ay0)) and self._is_valid_point((ax0, ay1)):
            msp.add_line((ax0, ay0), (ax0, ay1), dxfattribs={"layer": "SEZ_AXIS"})
            msp.add_line((ax0, ay0), (ax0, ay1), dxfattribs={"layer": "SEZ_PROJECT"})
        try:
            msp.add_text("OFFSET [m]", dxfattribs={"height": 2.0, "layer": "SEZ_TEXT"}).set_placement(
                ((plot_left + plot_right) * 0.5, plot_bottom - 5.0)
            )
            msp.add_text("QUOTA [m]", dxfattribs={"height": 2.0, "layer": "SEZ_TEXT"}).set_placement(
                (plot_left - 2.0, (plot_bottom + plot_top) * 0.5)
            )
        except Exception as exc:
            self._log_section_exception(section=sec, step="axis_labels", exc=exc)

        table_left = content_left
        table_right = min(content_right, table_left + table_w)
        current_step = "table drawing"
        table_data = self._draw_section_table(
            msp,
            item["points"],
            table_left,
            table_right,
            table_top,
            table_bottom,
            x_mapper=lambda off: map_pt(off, item["z_min"])[0],
            highlight_offsets=[
                0.0,
                -sec.width_info.left_width if sec.width_info else float("nan"),
                sec.width_info.right_width if sec.width_info else float("nan"),
            ],
        )

        current_step = "quote/candle drawing"
        point_anchor = {round(p["offset"], 6): p["x"] for p in table_data["points"]}
        for p in item["points"]:
            anchor_x = point_anchor.get(round(p["offset"], 6))
            if anchor_x is None:
                continue
            z_ref = p["project_z"] if math.isfinite(p["project_z"]) else p["terrain_z"]
            if not math.isfinite(z_ref):
                continue
            px, py = map_pt(p["offset"], z_ref)
            if not self._is_valid_point((px, py)) or not math.isfinite(anchor_x):
                continue
            try:
                if abs(anchor_x - px) <= 1e-6:
                    msp.add_line((px, py), (px, table_top), dxfattribs={"layer": "SEZ_TABLE"})
                else:
                    self._safe_add_polyline(
                        msp,
                        [(px, py), (px, table_top), (anchor_x, table_top)],
                        layer="SEZ_TABLE",
                        section=sec,
                        step=current_step,
                    )
                msp.add_circle((px, py), radius=0.8, dxfattribs={"layer": "SEZ_TABLE"})
            except Exception as exc:
                self._log_section_exception(section=sec, step="single_candle", exc=exc)

    def _build_section_cartiglio_layout_model(
        self,
        x_min: float,
        x_max: float,
        z_min: float,
        z_max: float,
        points: List[dict],
        section_h_scale: float,
        z_exaggeration: float,
        table_label_w: float = 30.0,
        table_col_min_w: float = 12.0,
        min_anchor_dx: float = 8.0,
    ) -> dict:
        side_pad = 12.0
        top_pad = 8.0
        bottom_pad = 8.0
        inter_block_gap = 6.0
        graph_extra_bottom = 8.0
        head_h = 32.0
        min_graph_w = 140.0
        min_graph_h = 95.0

        quote_rows = 3
        table_border_pad = 4.0

        plot_w = max(1.0, (x_max - x_min) * 1000.0 / section_h_scale)
        v_scale = section_h_scale / max(1e-6, z_exaggeration)
        plot_h = max(1.0, (z_max - z_min) * 1000.0 / v_scale)

        graph_w = max(min_graph_w, plot_w)
        graph_h = max(min_graph_h, plot_h)

        table_row_h = max(10.0, graph_h * 0.12)
        table_h = quote_rows * table_row_h + 12.0

        n_points_raw = max(1, len(points))
        n_points_anchor = max(1, int(max(graph_w, table_col_min_w) / min_anchor_dx))
        n_points_effective = min(n_points_raw, n_points_anchor)

        table_data_w = max(table_col_min_w * n_points_effective, graph_w)
        table_w = table_label_w + table_border_pad + table_data_w + 4.0

        content_w = max(graph_w, table_w)
        cart_w = content_w + 2.0 * side_pad
        cart_h = (
            top_pad
            + head_h
            + inter_block_gap
            + graph_h
            + graph_extra_bottom
            + inter_block_gap
            + table_h
            + bottom_pad
        )

        cart_w += 8.0
        cart_h += 12.0

        return {
            "side_pad": side_pad,
            "top_pad": top_pad,
            "bottom_pad": bottom_pad,
            "inter_block_gap": inter_block_gap,
            "head_h": head_h,
            "graph_extra_bottom": graph_extra_bottom,
            "plot_w": plot_w,
            "plot_h": plot_h,
            "v_scale": v_scale,
            "graph_w": graph_w,
            "graph_h": graph_h,
            "table_h": table_h,
            "table_w": table_w,
            "content_w": content_w,
            "cart_w": cart_w,
            "cart_h": cart_h,
        }

    def _draw_section_table(
        self,
        msp,
        points: List[dict],
        left: float,
        right: float,
        top: float,
        bottom: float,
        x_mapper,
        highlight_offsets: Optional[List[float]] = None,
    ) -> dict:
        rows = ["OFFSET", "TERRENO", "PROGETTO"]
        label_w = 30.0
        available_w = max(10.0, right - left - label_w - 2.0)
        if top <= bottom:
            top = bottom + 6.0
        points = self._reduce_quote_points_for_width(points, available_w)
        n = max(1, len(points))
        row_h = max(6.0, (top - bottom) / max(1, len(rows)))
        min_table_h = row_h * len(rows)
        if (top - bottom) < min_table_h:
            top = bottom + min_table_h
        table_right = right
        data_left = left + label_w + 1.5
        data_right = table_right - 1.5
        data_w = max(1e-6, data_right - data_left)
        text_h = max(2.6, min(3.4, row_h * 0.45, data_w / max(1.0, n) * 0.32))

        self._safe_add_polyline(
            msp,
            [(left, top), (table_right, top), (table_right, bottom), (left, bottom), (left, top)],
            layer="SEZ_TABLE",
            closed=True,
            section=None,
            step="section_table_frame",
        )
        try:
            msp.add_line((data_left, top), (data_left, bottom), dxfattribs={"layer": "SEZ_TABLE"})
        except Exception:
            pass
        for ridx in range(1, len(rows)):
            y = top - ridx * row_h
            try:
                msp.add_line((left, y), (table_right, y), dxfattribs={"layer": "SEZ_TABLE"})
            except Exception:
                pass

        for ridx, row in enumerate(rows):
            y = top - (ridx + 0.7) * row_h
            try:
                msp.add_text(row, dxfattribs={"height": text_h, "layer": "SEZ_TEXT"}).set_placement((left + 1.0, y))
            except Exception:
                pass

        point_positions = []
        anchors = []
        for p in points:
            x_anchor = float(x_mapper(p["offset"]))
            if not math.isfinite(x_anchor):
                continue
            x_anchor = max(data_left, min(data_right, x_anchor))
            anchors.append({"offset": p["offset"], "x": x_anchor, "terrain_z": p["terrain_z"], "project_z": p["project_z"]})
        anchors.sort(key=lambda point: point["x"])

        compact: List[dict] = []
        min_dx = max(18.0, text_h * 5.5)
        for anchor in anchors:
            if not compact or abs(anchor["x"] - compact[-1]["x"]) >= min_dx:
                compact.append(anchor)
            elif abs(anchor["offset"]) < abs(compact[-1]["offset"]):
                compact[-1] = anchor
        anchors = compact

        boundaries = [data_left]
        if anchors:
            boundaries.extend((anchors[i - 1]["x"] + anchors[i]["x"]) / 2.0 for i in range(1, len(anchors)))
        boundaries.append(data_right)

        for bx in boundaries[1:-1]:
            try:
                msp.add_line((bx, top), (bx, bottom), dxfattribs={"layer": "SEZ_TABLE"})
            except Exception:
                pass

        if highlight_offsets:
            for off in highlight_offsets:
                if not math.isfinite(off):
                    continue
                hx = float(x_mapper(off))
                if not math.isfinite(hx):
                    continue
                hx = max(data_left, min(data_right, hx))
                try:
                    msp.add_line((hx, top), (hx, bottom), dxfattribs={"layer": "SEZ_PROJECT"})
                except Exception:
                    pass

        for i, p in enumerate(anchors):
            cell_left = boundaries[i]
            cell_right = boundaries[i + 1]
            xc = (cell_left + cell_right) * 0.5
            point_positions.append({"offset": p["offset"], "x": xc})
            vals = [
                f"{p['offset']:.2f}",
                f"{p['terrain_z']:.2f}" if math.isfinite(p["terrain_z"]) else "-",
                f"{p['project_z']:.2f}" if math.isfinite(p["project_z"]) else "-",
            ]
            for ridx, val in enumerate(vals):
                y = top - (ridx + 0.7) * row_h
                try:
                    txt = msp.add_text(val, dxfattribs={"height": text_h, "layer": "SEZ_TEXT"})
                    txt.set_placement((xc - text_h * max(0.6, min(1.8, len(val) * 0.28)), y))
                except Exception:
                    pass

        return {"points": point_positions}

    def _reduce_quote_points_for_width(self, points: List[dict], available_w: float) -> List[dict]:
        if not points:
            return points
        min_col_w = 22.0
        max_points = max(1, int(available_w / min_col_w))
        if len(points) <= max_points:
            return points
        axis_idx = min(range(len(points)), key=lambda i: abs(points[i]["offset"]))
        stride = int(math.ceil(len(points) / max_points))
        keep_idx = {0, len(points) - 1, axis_idx}
        keep_idx.update(i for i, p in enumerate(points) if p.get("is_key"))
        keep_idx.update(range(0, len(points), stride))
        reduced = [dict(p, _must_keep=(idx in keep_idx and (idx in {0, len(points) - 1, axis_idx} or p.get("is_key")))) for idx, p in enumerate(points) if idx in keep_idx]
        reduced.sort(key=lambda p: p["offset"])
        while len(reduced) > max_points:
            removable = [i for i, p in enumerate(reduced) if not p.get("_must_keep")]
            if not removable:
                break
            drop_i = min(removable, key=lambda i: abs(reduced[i]["offset"]))
            reduced.pop(drop_i)
        for p in reduced:
            p.pop("_must_keep", None)
        return reduced

    def _build_quote_points(self, section: SectionData, quote_step_m: float) -> List[dict]:
        if not section.offsets:
            return []
        left = section.offsets[0]
        right = section.offsets[-1]
        offsets = {0.0, left, right}
        key_offsets = {left, right}
        if left <= 0.0 <= right:
            key_offsets.add(0.0)
        if section.width_info is not None:
            offsets.update(
                {
                    -section.width_info.left_width,
                    section.width_info.right_width,
                }
            )
            key_offsets.update(
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
                key_offsets.add(extra)

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
            result.append(
                {
                    "offset": off,
                    "terrain_z": terr,
                    "project_z": proj,
                    "is_key": any(abs(off - ko) <= 1e-6 for ko in key_offsets),
                }
            )
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

    def _get_slope_segment_points(self, section: SectionData, left: bool) -> list[tuple[float, float]]:
        """
        Restituisce i 2 vertici geometrici della scarpata:
        - start: bordo piattaforma
        - end: intercetto terreno

        Il model è la fonte primaria (left_slope_segment/right_slope_segment).
        Fallback legacy mantenuto per retrocompatibilità su dati preesistenti.
        """
        raw_segment = section.left_slope_segment if left else section.right_slope_segment
        if raw_segment and len(raw_segment) == 2:
            start, end = raw_segment
            if self._is_valid_point(start) and self._is_valid_point(end):
                return [start, end]
        return self._build_slope_segment(section, left)

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

    def _is_valid_point(self, point: tuple[float, float]) -> bool:
        return len(point) == 2 and math.isfinite(point[0]) and math.isfinite(point[1])

    def _sanitize_offset_polyline(
        self,
        section: SectionData,
        offsets: List[float],
        elevations: List[float],
        label: str,
    ) -> list[tuple[float, float]]:
        pairs = [(off, z) for off, z in zip(offsets, elevations) if math.isfinite(off) and math.isfinite(z)]
        return self._sanitize_offset_points(pairs, section, label)

    def _sanitize_offset_points(
        self,
        pairs: List[tuple[float, float]],
        section: Optional[SectionData],
        label: str,
    ) -> list[tuple[float, float]]:
        if not pairs:
            return []
        section_idx = getattr(section, "index", None)
        sorted_pairs = sorted(pairs, key=lambda pair: pair[0])
        clean: List[tuple[float, float]] = []
        dropped_duplicates = 0
        for off, z in sorted_pairs:
            if clean and abs(off - clean[-1][0]) <= self.OFFSET_DUPLICATE_TOL:
                clean[-1] = (off, z)
                dropped_duplicates += 1
            else:
                clean.append((off, z))
        if dropped_duplicates:
            self._logger.debug(
                "Removed duplicate/nearly-duplicate offsets | section=%s | profile=%s | dropped=%s | tol=%.6f",
                section_idx,
                label,
                dropped_duplicates,
                self.OFFSET_DUPLICATE_TOL,
            )
        return clean

    def _safe_add_polyline(
        self,
        msp,
        points: List[tuple[float, float]],
        layer: str,
        section: Optional[SectionData] = None,
        step: str = "polyline drawing",
        closed: bool = False,
    ) -> bool:
        valid_points = [pt for pt in points if self._is_valid_point(pt)]
        if len(valid_points) < 2:
            return False
        try:
            msp.add_lwpolyline(valid_points, close=closed, dxfattribs={"layer": layer})
            return True
        except Exception as exc:
            self._log_section_exception(section=section, step=step, exc=exc)
            return False

    def _log_export_exception(
        self,
        phase: str,
        sheet_type: str,
        sheet_index: Optional[int],
        section: Optional[SectionData],
        exc: Exception,
    ) -> None:
        section_index = getattr(section, "index", None)
        section_id = getattr(section, "id", None)
        self._logger.error(
            "DXF export error | phase=%s | sheet_type=%s | sheet_index=%s | section_index=%s | section_id=%s | repr=%s\n%s",
            phase,
            sheet_type,
            sheet_index,
            section_index,
            section_id,
            repr(exc),
            traceback.format_exc(),
        )

    def _log_section_exception(
        self,
        section: Optional[SectionData],
        step: str,
        exc: Exception,
        phase: str = "draw_section",
        sheet_type: str = "sections",
        sheet_index: Optional[int] = None,
    ) -> None:
        self._log_export_exception(
            phase=f"{phase}:{step}",
            sheet_type=sheet_type,
            sheet_index=sheet_index,
            section=section,
            exc=exc,
        )
