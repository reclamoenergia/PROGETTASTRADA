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
        "section_sample_step",
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
            section_sample_step=dialog.section_sample_step.value(),
            output_folder=dialog.output_folder.text(),
            project_name=dialog.project_name.text(),
            export_sections_dxf=dialog.chk_dxf_sections.isChecked(),
            export_profile_dxf=dialog.chk_dxf_profile.isChecked(),
            export_csv=dialog.chk_csv.isChecked(),
            dtm_layer_name=dialog.cmb_dtm.currentText(),
            axis_layer_name=dialog.cmb_axis.currentText(),
            polygon_layer_name=dialog.cmb_polygon.currentText(),
            forced_points_layer_name=dialog.cmb_forced.currentText(),
        )
        return settings.to_dict()

    def apply_ui_state(self, dialog, data: Dict[str, object]) -> None:
        s = PluginSettings.from_dict(data)
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
        dialog.section_sample_step.setValue(float(s.section_sample_step))
        dialog.output_folder.setText(str(s.output_folder))
        dialog.project_name.setText(str(s.project_name))
        dialog.chk_dxf_sections.setChecked(bool(s.export_sections_dxf))
        dialog.chk_dxf_profile.setChecked(bool(s.export_profile_dxf))
        dialog.chk_csv.setChecked(bool(s.export_csv))
        dialog.select_combo_by_text(dialog.cmb_dtm, s.dtm_layer_name)
        dialog.select_combo_by_text(dialog.cmb_axis, s.axis_layer_name)
        dialog.select_combo_by_text(dialog.cmb_polygon, s.polygon_layer_name)
        dialog.select_combo_by_text(dialog.cmb_forced, s.forced_points_layer_name)

    def save_to_json(self, path: str, data: Dict[str, object]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_from_json(self, path: str) -> Dict[str, object]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Il contenuto JSON deve essere un oggetto.")
        clean: Dict[str, object] = {}
        for k, v in data.items():
            if k in self.NUMERIC_KEYS:
                try:
                    clean[k] = float(v)
                except Exception as exc:
                    raise ValueError(f"Valore non numerico per {k}: {v}") from exc
            else:
                clean[k] = v
        return clean
