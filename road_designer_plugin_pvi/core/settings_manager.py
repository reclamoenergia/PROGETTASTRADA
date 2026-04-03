from __future__ import annotations

import json
from typing import Dict

from .models import PluginSettings


class SettingsManager:
    NUMERIC_KEYS = {
        "min_platform_width",
        "crossfall_nominal_pct",
        "crossfall_min_pct",
        "crossfall_max_pct",
        "max_longitudinal_slope_pct",
        "min_plan_radius",
        "min_vertical_radius",
        "cut_slope_hv",
        "fill_slope_hv",
        "pad_slope_pct",
        "axis_sample_step",
        "section_step",
        "section_length",
        "section_buffer",
        "section_sample_step",
        "profile_h_scale",
        "profile_v_scale",
        "section_scale",
        "section_vertical_exaggeration",
        "section_quote_step",
        "max_cartigli_per_sheet",
        "tin_contour_interval",
        "tin_processing_buffer",
        "tin_simplify_tolerance",
        "pvi_default_curve_length",
    }

    def collect_ui_state(self, dialog) -> Dict[str, object]:
        settings = PluginSettings(
            min_platform_width=dialog.min_width.value(),
            crossfall_nominal_pct=dialog.crossfall_nominal.value(),
            crossfall_min_pct=dialog.crossfall_min.value(),
            crossfall_max_pct=dialog.crossfall_max.value(),
            max_longitudinal_slope_pct=dialog.long_slope_max.value(),
            min_plan_radius=dialog.plan_radius_min.value(),
            min_vertical_radius=dialog.vert_radius_min.value(),
            cut_slope_hv=dialog.cut_slope.value(),
            fill_slope_hv=dialog.fill_slope.value(),
            pad_slope_pct=dialog.pad_slope.value(),
            axis_sample_step=dialog.axis_step.value(),
            section_step=dialog.section_step.value(),
            section_length=dialog.section_length.value(),
            section_buffer=dialog.section_buffer.value(),
            section_sample_step=dialog.section_sample_step.value(),
            profile_h_scale=dialog.profile_h_scale.value(),
            profile_v_scale=dialog.profile_v_scale.value(),
            section_scale=dialog.section_scale.value(),
            section_vertical_exaggeration=dialog.section_vertical_exaggeration.value(),
            section_quote_step=dialog.section_quote_step.value(),
            max_cartigli_per_sheet=dialog.max_cartigli_per_sheet.value(),
            output_folder=dialog.output_folder.text(),
            project_name=dialog.project_name.text(),
            export_sections_dxf=dialog.chk_dxf_sections.isChecked(),
            export_profile_dxf=dialog.chk_dxf_profile.isChecked(),
            export_csv=dialog.chk_csv.isChecked(),
            dtm_layer_name=dialog.cmb_dtm.currentText(),
            axis_layer_name=dialog.cmb_axis.currentText(),
            polygon_layer_name=dialog.cmb_polygon.currentText(),
            forced_points_layer_name=dialog.cmb_forced.currentText(),
            terrain_source_mode="tin" if dialog.cmb_terrain_source.currentIndex() == 1 else "raster",
            tin_contour_interval=dialog.tin_contour_interval.value(),
            tin_processing_buffer=dialog.tin_processing_buffer.value(),
            tin_simplify_tolerance=dialog.tin_simplify_tolerance.value(),
            tin_add_contours_layer=dialog.chk_tin_add_contours.isChecked(),
            tin_add_triangles_layer=dialog.chk_tin_add_triangles.isChecked(),
            tin_use_session_cache=dialog.chk_tin_cache.isChecked(),
            profile_mode=str(dialog.cmb_profile_mode.currentData() or "automatic"),
            pvi_layer_name=dialog.cmb_pvi_layer.currentText(),
            pvi_elevation_field=dialog.cmb_pvi_elev_field.currentText(),
            pvi_curve_length_field=dialog.cmb_pvi_curve_field.currentText(),
            pvi_default_curve_length=dialog.default_curve_length.value(),
        )
        return settings.to_dict()

    def apply_ui_state(self, dialog, data: Dict[str, object]) -> None:
        s = PluginSettings.from_dict(self._validate_and_normalize(data))
        dialog.min_width.setValue(float(s.min_platform_width))
        dialog.crossfall_nominal.setValue(float(s.crossfall_nominal_pct))
        dialog.crossfall_min.setValue(float(s.crossfall_min_pct))
        dialog.crossfall_max.setValue(float(s.crossfall_max_pct))
        dialog.long_slope_max.setValue(float(s.max_longitudinal_slope_pct))
        dialog.plan_radius_min.setValue(float(s.min_plan_radius))
        dialog.vert_radius_min.setValue(float(s.min_vertical_radius))
        dialog.cut_slope.setValue(float(s.cut_slope_hv))
        dialog.fill_slope.setValue(float(s.fill_slope_hv))
        dialog.pad_slope.setValue(float(s.pad_slope_pct))
        dialog.axis_step.setValue(float(s.axis_sample_step))
        dialog.section_step.setValue(float(s.section_step))
        dialog.section_length.setValue(float(s.section_length))
        dialog.section_buffer.setValue(float(s.section_buffer))
        dialog.section_sample_step.setValue(float(s.section_sample_step))
        dialog.profile_h_scale.setValue(float(s.profile_h_scale))
        dialog.profile_v_scale.setValue(float(s.profile_v_scale))
        dialog.section_scale.setValue(float(s.section_scale))
        dialog.section_vertical_exaggeration.setValue(float(s.section_vertical_exaggeration))
        dialog.section_quote_step.setValue(float(s.section_quote_step))
        dialog.max_cartigli_per_sheet.setValue(int(s.max_cartigli_per_sheet))
        dialog.output_folder.setText(str(s.output_folder))
        dialog.project_name.setText(str(s.project_name))
        dialog.chk_dxf_sections.setChecked(bool(s.export_sections_dxf))
        dialog.chk_dxf_profile.setChecked(bool(s.export_profile_dxf))
        dialog.chk_csv.setChecked(bool(s.export_csv))
        dialog.select_combo_by_text(dialog.cmb_dtm, s.dtm_layer_name)
        dialog.select_combo_by_text(dialog.cmb_axis, s.axis_layer_name)
        dialog.select_combo_by_text(dialog.cmb_polygon, s.polygon_layer_name)
        dialog.select_combo_by_text(dialog.cmb_forced, s.forced_points_layer_name)
        dialog.cmb_terrain_source.setCurrentIndex(1 if str(s.terrain_source_mode).lower() == "tin" else 0)
        dialog.tin_contour_interval.setValue(float(s.tin_contour_interval))
        dialog.tin_processing_buffer.setValue(float(s.tin_processing_buffer))
        dialog.tin_simplify_tolerance.setValue(float(s.tin_simplify_tolerance))
        dialog.chk_tin_add_contours.setChecked(bool(s.tin_add_contours_layer))
        dialog.chk_tin_add_triangles.setChecked(bool(s.tin_add_triangles_layer))
        dialog.chk_tin_cache.setChecked(bool(s.tin_use_session_cache))
        idx = dialog.cmb_profile_mode.findData(s.profile_mode)
        if idx >= 0:
            dialog.cmb_profile_mode.setCurrentIndex(idx)
        dialog.select_combo_by_text(dialog.cmb_pvi_layer, s.pvi_layer_name)
        dialog.select_combo_by_text(dialog.cmb_pvi_elev_field, s.pvi_elevation_field)
        dialog.select_combo_by_text(dialog.cmb_pvi_curve_field, s.pvi_curve_length_field)
        dialog.default_curve_length.setValue(float(s.pvi_default_curve_length))

    def save_to_json(self, path: str, data: Dict[str, object]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_from_json(self, path: str) -> Dict[str, object]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Il contenuto JSON deve essere un oggetto.")
        clean: Dict[str, object] = PluginSettings().to_dict()
        for k, v in data.items():
            if k in self.NUMERIC_KEYS:
                try:
                    clean[k] = float(v)
                except Exception as exc:
                    raise ValueError(f"Valore non numerico per {k}: {v}") from exc
            else:
                clean[k] = v
        return self._validate_and_normalize(clean)

    def _validate_and_normalize(self, data: Dict[str, object]) -> Dict[str, object]:
        clean = dict(data)
        def _require_positive(key: str) -> None:
            val = float(clean.get(key, 0.0))
            if val <= 0:
                raise ValueError(f"Il parametro '{key}' deve essere positivo.")

        for key in (
            "min_platform_width",
            "min_plan_radius",
            "min_vertical_radius",
            "axis_sample_step",
            "section_step",
            "section_length",
            "section_buffer",
            "section_sample_step",
            "profile_h_scale",
            "profile_v_scale",
            "section_scale",
            "section_vertical_exaggeration",
            "section_quote_step",
            "cut_slope_hv",
            "fill_slope_hv",
            "tin_contour_interval",
            "tin_processing_buffer",
        ):
            _require_positive(key)
        if int(clean.get("max_cartigli_per_sheet", 0)) <= 0:
            raise ValueError("max_cartigli_per_sheet deve essere positivo.")

        crossfall_min = float(clean.get("crossfall_min_pct", 0.0))
        crossfall_max = float(clean.get("crossfall_max_pct", 0.0))
        crossfall_nom = float(clean.get("crossfall_nominal_pct", 0.0))
        if crossfall_min <= 0 or crossfall_max <= 0 or crossfall_nom <= 0:
            raise ValueError("Le pendenze trasversali devono essere positive.")
        if crossfall_min > crossfall_max:
            raise ValueError("crossfall_min_pct non può superare crossfall_max_pct.")
        if not (crossfall_min <= crossfall_nom <= crossfall_max):
            raise ValueError("crossfall_nominal_pct deve ricadere tra minimo e massimo.")

        max_long = float(clean.get("max_longitudinal_slope_pct", 0.0))
        if max_long <= 0 or max_long > 100:
            raise ValueError("max_longitudinal_slope_pct deve essere compreso tra 0 e 100.")
        pad = float(clean.get("pad_slope_pct", 0.0))
        if abs(pad) > 100:
            raise ValueError("pad_slope_pct non plausibile (|valore| > 100%).")

        pvi_default_curve = float(clean.get("pvi_default_curve_length", 0.0))
        if pvi_default_curve < 0:
            raise ValueError("pvi_default_curve_length non può essere negativo.")
        if float(clean.get("tin_simplify_tolerance", 0.0)) < 0:
            raise ValueError("tin_simplify_tolerance deve essere >= 0.")
        return clean
