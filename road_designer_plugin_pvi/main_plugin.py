from __future__ import annotations

import os
import random
import time
import traceback
import warnings
from typing import Dict, List, Optional, Tuple

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QTableWidgetItem
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, Qgis

from .core.alignment import AlignmentBuilder
from .core.constraints import ConstraintChecker
from .core.cross_sections import CrossSectionGenerator
from .core.earthworks import EarthworksCalculator
from .core.input_manager import InputManager
from .core.models import PviRow
from .core.raster_terrain_provider import RasterTerrainProvider
from .core.road_model import RoadModelBuilder
from .core.settings_manager import SettingsManager
from .core.tin_builder import TinBuilder
from .core.tin_terrain_provider import TinTerrainProvider
from .core.vertical_profile import VerticalProfileBuilder
from .core.width_analysis import WidthAnalysis
from .export.dxf_exporter import DxfExporter
from .export.tables_exporter import TablesExporter
from .export.vector_exporter import VectorExporter
from .ui.main_dialog import MainDialog


class RoadDesignerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action: Optional[QAction] = None
        self.dialog: Optional[MainDialog] = None
        self.vp_builder = VerticalProfileBuilder()
        self.tin_builder = TinBuilder()
        self.pvi_rows: List[PviRow] = []
        self.pvi_rows_original: List[PviRow] = []
        self._pvi_table_updating = False
        self.active_profile = None
        self.suggested_pvi_rows: List[PviRow] = []
        self.suggested_profile = None

    def initGui(self):
        self.action = QAction("Road Designer Plugin PVI", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&Road Designer PVI", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Road Designer PVI", self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        if self.dialog is None:
            self.dialog = MainDialog(self.iface.mainWindow())
            self.dialog.btn_calculate.clicked.connect(self.calculate)
            self.dialog.btn_preview_earthworks.clicked.connect(self.preview_earthworks)
            self.dialog.btn_suggest_profile.clicked.connect(self.suggest_minimum_earthworks_profile)
            self.dialog.btn_apply_suggested.clicked.connect(self.apply_suggested_profile)
            self.dialog.btn_save_json.clicked.connect(self.save_json)
            self.dialog.btn_load_json.clicked.connect(self.load_json)
            self.dialog.cmb_profile_mode.currentIndexChanged.connect(self._on_mode_changed)
            self.dialog.cmb_pvi_layer.currentIndexChanged.connect(self._on_pvi_layer_changed)
            self.dialog.btn_reload_pvi.clicked.connect(self.reload_pvi_from_layer)
            self.dialog.btn_reset_pvi.clicked.connect(self.reset_pvi_edits)
            self.dialog.btn_add_pvi.clicked.connect(self.add_pvi)
            self.dialog.btn_remove_pvi.clicked.connect(self.remove_selected_pvi)
            self.dialog.tbl_pvi.itemChanged.connect(self._on_pvi_table_item_changed)
            self.dialog.tbl_pvi.currentCellChanged.connect(self._on_pvi_table_selection_changed)
            self.dialog.preview.pviDragged.connect(self._on_preview_pvi_dragged)
            self.dialog.preview.pviSelected.connect(self._on_preview_pvi_selected)
        self.refresh_layers()
        self._on_mode_changed()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def refresh_layers(self):
        if not self.dialog:
            return
        all_layers = list(QgsProject.instance().mapLayers().values())
        self.dialog.cmb_dtm.clear()
        self.dialog.cmb_axis.clear()
        self.dialog.cmb_polygon.clear()
        self.dialog.cmb_forced.clear()
        self.dialog.cmb_pvi_layer.clear()
        self.dialog.cmb_forced.addItem("")
        self.dialog.cmb_pvi_layer.addItem("")
        for lyr in all_layers:
            if lyr.type() == lyr.RasterLayer:
                self.dialog.cmb_dtm.addItem(lyr.name())
            else:
                if lyr.geometryType() == 1:
                    self.dialog.cmb_axis.addItem(lyr.name())
                elif lyr.geometryType() == 2:
                    self.dialog.cmb_polygon.addItem(lyr.name())
                elif lyr.geometryType() == 0:
                    self.dialog.cmb_forced.addItem(lyr.name())
                    self.dialog.cmb_pvi_layer.addItem(lyr.name())
        self._on_pvi_layer_changed()

    def _layer(self, name: str):
        layers = QgsProject.instance().mapLayersByName(name)
        return layers[0] if layers else None

    def _profile_mode(self) -> str:
        if not self.dialog:
            return "automatic"
        return str(self.dialog.cmb_profile_mode.currentData() or "automatic")

    def _on_mode_changed(self):
        if not self.dialog:
            return
        is_pvi = self._profile_mode() == "pvi"
        self.dialog.set_pvi_table_enabled(is_pvi)
        if is_pvi:
            self.rebuild_preview_profile()

    def _on_pvi_layer_changed(self, _index=None, preferred_elev_field: Optional[str] = None, preferred_curve_field: Optional[str] = None):
        d = self.dialog
        if not d:
            return
        layer = self._layer(d.cmb_pvi_layer.currentText())
        self._populate_pvi_field_combos(
            layer,
            preferred_elev_field=preferred_elev_field,
            preferred_curve_field=preferred_curve_field,
        )

    def _populate_pvi_field_combos(
        self,
        layer,
        preferred_elev_field: Optional[str] = None,
        preferred_curve_field: Optional[str] = None,
    ) -> None:
        d = self.dialog
        if not d:
            return
        current_elev = d.cmb_pvi_elev_field.currentText()
        current_curve = d.cmb_pvi_curve_field.currentText()
        d.cmb_pvi_elev_field.clear()
        d.cmb_pvi_curve_field.clear()
        d.cmb_pvi_curve_field.addItem("")
        if not layer:
            return
        fields = list(layer.fields())
        for field in fields:
            name = field.name()
            d.cmb_pvi_elev_field.addItem(name)
            d.cmb_pvi_curve_field.addItem(name)
        available_names = [f.name() for f in fields]
        elev_target = self._choose_preferred_field(
            available_names,
            preferred=preferred_elev_field,
            current=current_elev,
            fallback=self._default_elevation_field_name(fields),
        )
        curve_target = self._choose_preferred_field(
            available_names,
            preferred=preferred_curve_field,
            current=current_curve,
            fallback="",
            allow_blank=True,
        )
        d.select_combo_by_text(d.cmb_pvi_elev_field, elev_target)
        d.select_combo_by_text(d.cmb_pvi_curve_field, curve_target)

    def _choose_preferred_field(
        self,
        available_names: List[str],
        preferred: Optional[str],
        current: Optional[str],
        fallback: str,
        allow_blank: bool = False,
    ) -> str:
        for candidate in (preferred, current):
            if candidate and candidate in available_names:
                return candidate
        if allow_blank and not preferred and not current:
            return ""
        if fallback and fallback in available_names:
            return fallback
        return ""

    def _default_elevation_field_name(self, fields) -> str:
        names = [f.name() for f in fields]
        if "z" in names:
            return "z"
        for field in fields:
            try:
                if field.isNumeric():
                    return field.name()
            except Exception:
                continue
        return names[0] if names else ""

    def reload_pvi_from_layer(self):
        d = self.dialog
        if not d:
            return
        axis = self._layer(d.cmb_axis.currentText())
        if not axis:
            self._warn("Selezionare il layer asse per caricare i PVI.")
            return
        align = AlignmentBuilder().build(axis, d.plan_radius_min.value(), d.axis_step.value())
        pvi_layer = self._layer(d.cmb_pvi_layer.currentText())
        result = self.vp_builder.load_pvi_rows(
            pvi_layer,
            align.points,
            d.cmb_pvi_elev_field.currentText(),
            d.cmb_pvi_curve_field.currentText(),
            d.default_curve_length.value(),
        )
        lock_map = {r.feature_id: r.locked for r in self.pvi_rows}
        for row in result.rows:
            row.locked = lock_map.get(row.feature_id, False)
        self.pvi_rows = self.vp_builder.recompute_pvi_diagnostics(
            result.rows,
            d.long_slope_max.value(),
            d.default_curve_length.value(),
        )
        self.pvi_rows_original = [PviRow(**vars(r)) for r in self.pvi_rows]
        self._refresh_pvi_table()
        self.rebuild_preview_profile(log_warnings=result.warnings)

    def reset_pvi_edits(self):
        self.pvi_rows = [PviRow(**vars(r)) for r in self.pvi_rows_original]
        self.pvi_rows = (
            self.vp_builder.recompute_pvi_diagnostics(
                self.pvi_rows,
                self.dialog.long_slope_max.value(),
                self.dialog.default_curve_length.value(),
            )
            if self.dialog
            else self.pvi_rows
        )
        self._refresh_pvi_table()
        self.rebuild_preview_profile()

    def _refresh_pvi_table(self):
        d = self.dialog
        if not d:
            return
        self._pvi_table_updating = True
        try:
            tbl = d.tbl_pvi
            tbl.blockSignals(True)
            tbl.setRowCount(len(self.pvi_rows))
            for i, row in enumerate(self.pvi_rows):
                in_s = self.vp_builder.incoming_slope_pct(self.pvi_rows, i)
                out_s = self.vp_builder.outgoing_slope_pct(self.pvi_rows, i)
                values = [
                    str(i + 1),
                    f"{row.progressive:.3f}",
                    f"{row.elevation:.3f}",
                    f"{row.curve_length:.3f}",
                    "" if in_s is None else f"{in_s:.3f}",
                    "" if out_s is None else f"{out_s:.3f}",
                ]
                for c, v in enumerate(values):
                    item = QTableWidgetItem(v)
                    if c not in (2, 3):
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    tbl.setItem(i, c, item)
                chk = QTableWidgetItem("")
                chk.setFlags((chk.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                chk.setCheckState(Qt.Checked if row.locked else Qt.Unchecked)
                tbl.setItem(i, 6, chk)
                tbl.setItem(i, 7, QTableWidgetItem(row.warning))
            tbl.resizeColumnsToContents()
            d.preview.set_selected_index(tbl.currentRow())
        finally:
            tbl.blockSignals(False)
            self._pvi_table_updating = False

    def _on_pvi_table_item_changed(self, item):
        if self._pvi_table_updating or not self.dialog:
            return
        r, c = item.row(), item.column()
        if r < 0 or r >= len(self.pvi_rows) or c not in (2, 3, 6):
            return
        if c == 6:
            self.pvi_rows[r].locked = item.checkState() == Qt.Checked
            return
        txt = (item.text() or "").strip().replace(",", ".")
        try:
            val = float(txt)
        except Exception:
            self._warn("Valore PVI non numerico.")
            self._refresh_pvi_table()
            return
        if c == 2:
            self.pvi_rows[r].elevation = val
            if not self._write_pvi_row_to_layer(self.pvi_rows[r], update_geometry=False):
                self._refresh_pvi_table()
                return
        else:
            self.pvi_rows[r].curve_length = max(0.0, val)
            if not self._write_pvi_row_to_layer(self.pvi_rows[r], update_geometry=False):
                self._refresh_pvi_table()
                return
        self.pvi_rows = self.vp_builder.recompute_pvi_diagnostics(
            self.pvi_rows,
            self.dialog.long_slope_max.value(),
            self.dialog.default_curve_length.value(),
        )
        self._refresh_pvi_table()
        self.rebuild_preview_profile()

    def _on_preview_pvi_dragged(self, row_idx: int, new_elevation: float):
        if not self.dialog or row_idx < 0 or row_idx >= len(self.pvi_rows):
            return
        if self.pvi_rows[row_idx].locked:
            return
        self.pvi_rows[row_idx].elevation = float(new_elevation)
        if not self._write_pvi_row_to_layer(self.pvi_rows[row_idx], update_geometry=False):
            return
        self.pvi_rows = self.vp_builder.recompute_pvi_diagnostics(
            self.pvi_rows,
            self.dialog.long_slope_max.value(),
            self.dialog.default_curve_length.value(),
        )
        self._refresh_pvi_table()
        self.rebuild_preview_profile()

    def _on_pvi_table_selection_changed(self, current_row, _current_col, _prev_row, _prev_col):
        if not self.dialog:
            return
        self.dialog.preview.set_selected_index(current_row)

    def _on_preview_pvi_selected(self, row_idx: int):
        d = self.dialog
        if not d:
            return
        if 0 <= row_idx < d.tbl_pvi.rowCount():
            d.tbl_pvi.setCurrentCell(row_idx, 0)

    def add_pvi(self):
        d = self.dialog
        if not d:
            return
        if self._profile_mode() != "pvi":
            self._warn("Attivare la modalità profilo PVI per aggiungere punti.")
            return
        align = self._build_alignment()
        if not align:
            return
        pvi_layer = self._layer(d.cmb_pvi_layer.currentText())
        if not pvi_layer:
            self._warn("Selezionare il layer PVI.")
            return
        if not self._ensure_pvi_layer_editable(pvi_layer):
            return
        if len(self.pvi_rows) < 2:
            self.reload_pvi_from_layer()
        if len(self.pvi_rows) < 2:
            self._warn("Servono almeno 2 PVI esistenti per interpolare il nuovo punto.")
            return

        selected = d.tbl_pvi.currentRow()
        if 0 <= selected < len(self.pvi_rows) - 1:
            s0 = self.pvi_rows[selected].progressive
            s1 = self.pvi_rows[selected + 1].progressive
            new_prog = (s0 + s1) / 2.0
        else:
            new_prog = (self.pvi_rows[0].progressive + self.pvi_rows[-1].progressive) / 2.0
        new_elev = self.vp_builder.interpolate_pvi_elevation(self.pvi_rows, new_prog)

        xy = self.vp_builder.progressive_to_axis_point(new_prog, align.points)
        if not xy:
            self._warn("Impossibile determinare la posizione XY del nuovo PVI.")
            return
        feat = QgsFeature(pvi_layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(xy[0], xy[1])))
        e_idx = pvi_layer.fields().indexFromName(d.cmb_pvi_elev_field.currentText())
        c_idx = pvi_layer.fields().indexFromName(d.cmb_pvi_curve_field.currentText()) if d.cmb_pvi_curve_field.currentText() else -1
        if e_idx < 0:
            self._warn("Campo quota PVI non valido.")
            return
        feat.setAttribute(e_idx, float(new_elev))
        if c_idx >= 0:
            feat.setAttribute(c_idx, float(max(0.0, d.default_curve_length.value())))

        if not pvi_layer.addFeature(feat):
            self._warn("Inserimento feature PVI fallito nel layer selezionato.")
            return
        pvi_layer.triggerRepaint()
        self.reload_pvi_from_layer()

    def remove_selected_pvi(self):
        d = self.dialog
        if not d:
            return
        if len(self.pvi_rows) <= 2:
            self._warn("Non è possibile scendere sotto 2 PVI.")
            return
        row_idx = d.tbl_pvi.currentRow()
        if row_idx < 0 or row_idx >= len(self.pvi_rows):
            self._warn("Selezionare una riga PVI da rimuovere.")
            return
        pvi_layer = self._layer(d.cmb_pvi_layer.currentText())
        if not pvi_layer:
            self._warn("Selezionare il layer PVI.")
            return
        if not self._ensure_pvi_layer_editable(pvi_layer):
            return
        feature_id = self.pvi_rows[row_idx].feature_id
        if not pvi_layer.deleteFeature(feature_id):
            self._warn("Cancellazione feature PVI fallita nel layer selezionato.")
            return
        pvi_layer.triggerRepaint()
        self.reload_pvi_from_layer()

    def _build_alignment(self):
        if not self.dialog:
            return None
        axis = self._layer(self.dialog.cmb_axis.currentText())
        if not axis:
            self._warn("Selezionare il layer asse.")
            return None
        return AlignmentBuilder().build(axis, self.dialog.plan_radius_min.value(), self.dialog.axis_step.value())

    def _ensure_pvi_layer_editable(self, layer) -> bool:
        if layer.isEditable():
            return True
        if layer.startEditing():
            if self.dialog:
                self.dialog.append_log(f"Layer PVI '{layer.name()}' messo in modifica.")
            return True
        self._warn(f"Il layer PVI '{layer.name()}' non è modificabile.")
        return False

    def _write_pvi_row_to_layer(self, row: PviRow, update_geometry: bool = False) -> bool:
        d = self.dialog
        if not d:
            return False
        pvi_layer = self._layer(d.cmb_pvi_layer.currentText())
        if not pvi_layer:
            self._warn("Layer PVI non selezionato.")
            return False
        if not self._ensure_pvi_layer_editable(pvi_layer):
            return False
        e_idx = pvi_layer.fields().indexFromName(d.cmb_pvi_elev_field.currentText())
        c_idx = pvi_layer.fields().indexFromName(d.cmb_pvi_curve_field.currentText()) if d.cmb_pvi_curve_field.currentText() else -1
        if e_idx < 0:
            self._warn("Campo quota PVI non valido.")
            return False
        if not pvi_layer.changeAttributeValue(row.feature_id, e_idx, float(row.elevation)):
            self._warn("Aggiornamento quota PVI sul layer fallito.")
            return False
        if c_idx >= 0 and not pvi_layer.changeAttributeValue(row.feature_id, c_idx, float(max(0.0, row.curve_length))):
            self._warn("Aggiornamento lunghezza curva PVI sul layer fallito.")
            return False
        if update_geometry:
            align = self._build_alignment()
            if not align:
                return False
            xy = self.vp_builder.progressive_to_axis_point(row.progressive, align.points)
            if not xy:
                self._warn("Impossibile aggiornare geometria PVI (progressiva->XY).")
                return False
            if not pvi_layer.changeGeometry(row.feature_id, QgsGeometry.fromPointXY(QgsPointXY(xy[0], xy[1]))):
                self._warn("Aggiornamento geometria PVI sul layer fallito.")
                return False
        pvi_layer.triggerRepaint()
        return True

    def rebuild_preview_profile(self, log_warnings: Optional[List[str]] = None):
        d = self.dialog
        if not d or self._profile_mode() != "pvi":
            return
        axis = self._layer(d.cmb_axis.currentText())
        dtm = self._layer(d.cmb_dtm.currentText())
        if not axis or not dtm:
            d.preview.clear_data()
            d.lbl_pvi_status.setText("Selezionare asse e DTM per l'anteprima PVI")
            return
        try:
            align = AlignmentBuilder().build(axis, d.plan_radius_min.value(), d.axis_step.value())
            terrain = self._build_terrain_provider(dtm, align.points)
            terrain_axis = terrain.sample_many(align.points)
            if len(self.pvi_rows) < 2:
                d.preview.clear_data()
                d.lbl_pvi_status.setText("Servono almeno 2 PVI validi")
                return
            profile = self.vp_builder.build_from_pvi(
                align.progressive,
                terrain_axis,
                self.pvi_rows,
                d.default_curve_length.value(),
            )
            self.active_profile = profile
            pvi_points = [(r.progressive, r.elevation) for r in self.pvi_rows if r.enabled]
            d.preview.set_data(profile.progressive, profile.terrain_z, profile.project_z, pvi_points)
            if self.suggested_profile and len(self.suggested_profile.progressive) == len(profile.progressive):
                d.preview.set_data(
                    profile.progressive,
                    profile.terrain_z,
                    profile.project_z,
                    pvi_points,
                    suggested_z=self.suggested_profile.project_z,
                )
            msg = f"PVI caricati: {len(self.pvi_rows)}"
            state_warnings = [r.warning for r in self.pvi_rows if r.warning]
            if state_warnings:
                msg += f" | stati critici: {len(state_warnings)}"
            if log_warnings:
                msg += " | warning: " + " | ".join(log_warnings[:3])
            d.lbl_pvi_status.setText(msg)
            for w in (log_warnings or []):
                d.append_log(f"WARNING PVI: {w}")
        except Exception as exc:
            d.preview.clear_data()
            d.lbl_pvi_status.setText(f"Anteprima PVI non disponibile: {exc}")

    def calculate(self):
        d = self.dialog
        if not d:
            return
        d.progress.setValue(0)
        d.log.clear()
        try:
            inputs = InputManager(self.iface)
            dtm = self._layer(d.cmb_dtm.currentText())
            axis = self._layer(d.cmb_axis.currentText())
            polygon = self._layer(d.cmb_polygon.currentText())
            forced = self._layer(d.cmb_forced.currentText()) if d.cmb_forced.currentText() else None
            ok, msg = inputs.validate(dtm, axis, polygon, forced)
            if not ok:
                self._warn(msg)
                return
            d.append_log("Input validati")
            d.progress.setValue(10)

            align = AlignmentBuilder().build(axis, d.plan_radius_min.value(), d.axis_step.value())
            d.append_log(f"Asse raccordato: L={align.length:.2f} m, campioni={len(align.points)}")
            d.progress.setValue(25)

            terrain = self._build_terrain_provider(dtm, align.points)
            terrain_axis = terrain.sample_many(align.points)
            if self._profile_mode() == "pvi":
                if len(self.pvi_rows) < 2:
                    self.reload_pvi_from_layer()
                profile = self.vp_builder.build_from_pvi(
                    align.progressive,
                    terrain_axis,
                    self.pvi_rows,
                    d.default_curve_length.value(),
                )
                d.append_log("Profilo longitudinale da PVI con curve verticali paraboliche")
            else:
                profile = self.vp_builder.build(
                    align.progressive,
                    terrain_axis,
                    d.long_slope_max.value(),
                    d.vert_radius_min.value(),
                    forced,
                    align.points,
                )
                d.append_log("Profilo longitudinale di progetto calcolato (automatico)")
            self.active_profile = profile
            d.progress.setValue(45)

            sections, _vol_sections, _summary_sections = self._compute_earthworks_for_profile(align, terrain, polygon, profile)
            d.append_log(f"Sezioni analisi/DXF generate: {len(sections)}")
            surface_step = self._surface_section_step()
            surface_sections, vol, summary = self._compute_earthworks_for_profile(
                align,
                terrain,
                polygon,
                profile,
                section_step=surface_step,
            )
            d.append_log(
                "Sezioni road surface (volumi/slopes/project surface): "
                f"{len(surface_sections)} | passo={surface_step:.3f} m"
            )
            d.progress.setValue(70)
            d.append_log(
                f"Volumi terreno@base: Sterro={vol.total_cut:.2f} m3, "
                f"Riporto={vol.total_fill:.2f} m3, Massicciata={vol.total_foundation:.2f} m3"
            )
            d.set_earthworks_summary(self._format_summary(summary))

            warn = ConstraintChecker().check_longitudinal(profile, d.long_slope_max.value())
            warn += ConstraintChecker().check_crossfall(sections, d.crossfall_min.value(), d.crossfall_max.value())
            for sec in sections:
                warn.extend([f"Sezione {sec.index}: {w}" for w in sec.warnings])
            for w in warn[:20]:
                d.append_log(f"WARNING: {w}")
            d.progress.setValue(80)

            self._run_exports(align, axis, profile, sections, surface_sections, vol)
            d.progress.setValue(100)
            self._info("Calcolo completato con successo")
        except Exception as exc:
            self._warn(f"Errore durante il calcolo: {exc}")

    def _build_terrain_provider(self, dtm, align_points):
        d = self.dialog
        if not d:
            return RasterTerrainProvider(dtm)
        mode = "tin" if d.cmb_terrain_source.currentIndex() == 1 else "raster"
        if mode == "raster":
            d.append_log("Sorgente terreno: Raster DTM")
            return RasterTerrainProvider(dtm)

        d.append_log("Sorgente terreno: TIN da curve locali")
        try:
            tin_result = self.tin_builder.build_from_local_contours(
                dtm_layer=dtm,
                axis_points=align_points,
                contour_interval=d.tin_contour_interval.value(),
                processing_buffer=d.tin_processing_buffer.value(),
                simplify_tolerance=d.tin_simplify_tolerance.value(),
                add_contours_layer=d.chk_tin_add_contours.isChecked(),
                add_triangles_layer=d.chk_tin_add_triangles.isChecked(),
                use_cache=d.chk_tin_cache.isChecked(),
            )
        except Exception as exc:
            raise ValueError(f"Generazione TIN locale fallita: {exc}") from exc

        d.append_log(
            "TIN locale pronto: "
            f"triangoli={len(tin_result.surface.triangles)}, "
            f"vertici={len(tin_result.surface.vertices)}, "
            f"extent={tin_result.local_extent.toString()}"
        )
        return TinTerrainProvider(tin_result.surface)

    def _run_exports(self, align, axis_layer, profile, sections, surface_sections, vol):
        d = self.dialog
        if not d:
            return
        folder = d.output_folder.text().strip()
        if not folder:
            d.append_log("WARNING: Cartella output non impostata: i layer vettoriali saranno creati solo in memoria.")
        name = d.project_name.text().strip() or "road_project"
        crs_authid = axis_layer.crs().authid() if axis_layer and axis_layer.crs().isValid() else QgsProject.instance().crs().authid()
        def _vector_export():
            vec_result = VectorExporter().export_outputs(
                align,
                sections,
                folder,
                name,
                crs_authid,
                surface_sections=surface_sections,
            )
            d.append_log(
                "Layer QGIS creati: "
                f"{vec_result['axis_layer_name']}, {vec_result['sections_layer_name']}, "
                f"{vec_result['slopes_layer_name']}, {vec_result['surface_layer_name']}, "
                f"{vec_result['footprint_layer_name']}"
            )
            for path in vec_result["saved_paths"]:
                d.append_log(f"Vettoriale salvato: {path}")

        self._run_export_step(phase="vector_export", sheet_type="n/a", fn=_vector_export)

        exp_dxf = DxfExporter()
        export_profile = folder and d.chk_dxf_profile.isChecked()
        export_sections = folder and d.chk_dxf_sections.isChecked()
        profile_path = os.path.join(folder, f"{name}_layout_profile.dxf") if export_profile and export_sections else os.path.join(folder, f"{name}_layout.dxf")
        sections_path = os.path.join(folder, f"{name}_layout_sections.dxf") if export_profile and export_sections else os.path.join(folder, f"{name}_layout.dxf")
        if export_profile:
            def _profile_dxf_export():
                prof_data = profile if d.chk_dxf_profile.isChecked() else None
                exp_dxf.export_all_layout(
                    profile_path,
                    profile=prof_data,
                    sections=sections,
                    quote_step_m=d.section_quote_step.value(),
                    section_z_exaggeration=d.section_vertical_exaggeration.value(),
                    profile_h_scale=d.profile_h_scale.value(),
                    profile_v_scale=d.profile_v_scale.value(),
                    section_h_scale=d.section_scale.value(),
                    min_width=d.min_width.value(),
                    max_cartigli_per_sheet=d.max_cartigli_per_sheet.value(),
                )
                d.append_log(f"DXF profilo: {profile_path}")
            self._run_export_step(phase="dxf_export", sheet_type="profile", fn=_profile_dxf_export)
        if export_sections:
            def _sections_dxf_export():
                exp_dxf.export_all_layout(
                    sections_path,
                    profile=None,
                    sections=sections,
                    quote_step_m=d.section_quote_step.value(),
                    section_z_exaggeration=d.section_vertical_exaggeration.value(),
                    profile_h_scale=d.profile_h_scale.value(),
                    profile_v_scale=d.profile_v_scale.value(),
                    section_h_scale=d.section_scale.value(),
                    min_width=d.min_width.value(),
                    max_cartigli_per_sheet=d.max_cartigli_per_sheet.value(),
                )
                d.append_log(f"DXF sezioni: {sections_path}")
            self._run_export_step(phase="dxf_export", sheet_type="sections", fn=_sections_dxf_export)
        if folder and d.chk_csv.isChecked():
            p = os.path.join(folder, f"{name}_volumes.csv")
            def _csv_export():
                TablesExporter().export_volumes_csv(p, vol)
                d.append_log(f"CSV volumi: {p}")
            self._run_export_step(phase="csv_export", sheet_type="n/a", fn=_csv_export)

    def _run_export_step(self, phase: str, sheet_type: str, fn):
        d = self.dialog
        if not d:
            return
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                fn()
            except Exception as exc:
                d.append_log(
                    "ERROR: export failed "
                    f"| phase={phase} | sheet_type={sheet_type} | section_index=n/a | section_id=n/a "
                    f"| repr={exc!r}\n{traceback.format_exc()}"
                )
                return
        if caught_warnings:
            dep_count = sum(1 for w in caught_warnings if issubclass(w.category, DeprecationWarning))
            if dep_count:
                d.append_log(f"WARNING: {phase} generated {dep_count} deprecated warnings (suppressed).")

    def save_json(self):
        d = self.dialog
        if not d:
            return
        path, _ = QFileDialog.getSaveFileName(d, "Salva parametri", "", "JSON (*.json)")
        if not path:
            return
        try:
            sm = SettingsManager()
            sm.save_to_json(path, sm.collect_ui_state(d))
            self._info("Parametri salvati")
        except Exception as exc:
            self._warn(f"Salvataggio JSON fallito: {exc}")

    def load_json(self):
        d = self.dialog
        if not d:
            return
        path, _ = QFileDialog.getOpenFileName(d, "Carica parametri", "", "JSON (*.json)")
        if not path:
            return
        try:
            sm = SettingsManager()
            state = sm.load_from_json(path)
            sm.apply_ui_state(d, state)
            self._on_mode_changed()
            self._on_pvi_layer_changed(
                preferred_elev_field=str(state.get("pvi_elevation_field", "") or ""),
                preferred_curve_field=str(state.get("pvi_curve_length_field", "") or ""),
            )
            self._info("Parametri caricati")
        except Exception as exc:
            self._warn(f"Caricamento JSON fallito: {exc}")

    def _warn(self, msg: str):
        if self.dialog:
            self.dialog.append_log(f"ERRORE: {msg}")
        self.iface.messageBar().pushMessage("Road Designer PVI", msg, level=Qgis.Warning, duration=8)

    def _info(self, msg: str):
        if self.dialog:
            self.dialog.append_log(msg)
        self.iface.messageBar().pushMessage("Road Designer PVI", msg, level=Qgis.Info, duration=5)

    def _compute_earthworks_for_profile(
        self,
        align,
        terrain,
        polygon,
        profile,
        section_step: Optional[float] = None,
        section_sample_step: Optional[float] = None,
    ):
        d = self.dialog
        section_step_val = float(section_step) if section_step is not None else d.section_step.value()
        section_sample_step_val = (
            float(section_sample_step) if section_sample_step is not None else d.section_sample_step.value()
        )
        sections = CrossSectionGenerator().generate(
            align,
            terrain,
            section_step_val,
            d.section_length.value(),
            section_sample_step_val,
        )
        wa = WidthAnalysis(polygon, d.min_width.value())
        sec_gen = CrossSectionGenerator()
        model = RoadModelBuilder()
        ew = EarthworksCalculator()
        for sec in sections:
            sec.width_info = wa.analyze(sec_gen.as_geometry(sec), sec.axis_point)
            model.build_section_profile(sec, profile, d.min_width.value(), d.crossfall_nominal.value(), d.pad_slope.value())
            model.add_side_slopes(sec, d.cut_slope.value(), d.fill_slope.value())
            model.apply_effective_section_window(
                sec,
                max_section_width=d.section_length.value(),
                section_buffer=d.section_buffer.value(),
            )
            model.apply_foundation_offset(sec, d.foundation_thickness.value())
            ew.compute_section_areas(sec)
        vol = ew.compute_volumes(sections)
        approx_count = sum(1 for s in sections if not s.left_slope_resolved or not s.right_slope_resolved)
        summary = {
            "total_cut": vol.total_cut,
            "total_fill": vol.total_fill,
            "total_movement": vol.total_cut + vol.total_fill,
            "net_balance": vol.total_cut - vol.total_fill,
            "abs_balance": abs(vol.total_cut - vol.total_fill),
            "total_foundation": vol.total_foundation,
            "sections_count": len(sections),
            "approx_count": approx_count,
        }
        return sections, vol, summary

    def _format_summary(self, summary: Dict[str, float], title: str = "Anteprima movimenti terra") -> str:
        warn = ""
        if summary.get("approx_count", 0):
            warn = f"\nWarning: {int(summary['approx_count'])} sezioni con scarpata approssimata."
        return (
            f"{title}\n"
            f"- Volume totale scavo terreno: {summary['total_cut']:.2f} m³\n"
            f"- Volume totale rilevato terreno: {summary['total_fill']:.2f} m³\n"
            f"- Movimento terra complessivo: {summary['total_movement']:.2f} m³\n"
            f"- Bilancio netto scavo-rilevato: {summary['net_balance']:.2f} m³\n"
            f"- Differenza assoluta scavo-rilevato: {summary['abs_balance']:.2f} m³\n"
            f"- Volume totale massicciata: {summary['total_foundation']:.2f} m³\n"
            f"- Numero sezioni utilizzate: {int(summary['sections_count'])}{warn}"
        )

    def preview_earthworks(self):
        d = self.dialog
        if not d:
            return
        try:
            align = self._build_alignment()
            if not align:
                return
            dtm = self._layer(d.cmb_dtm.currentText())
            polygon = self._layer(d.cmb_polygon.currentText())
            if not dtm or not polygon:
                self._warn("Selezionare DTM e poligono viabilità per l'anteprima.")
                return
            terrain = self._build_terrain_provider(dtm, align.points)
            profile = self._build_active_profile_for_alignment(align, terrain)
            _sections, _vol, summary = self._compute_earthworks_for_profile(
                align,
                terrain,
                polygon,
                profile,
                section_step=self._surface_section_step(),
            )
            d.set_earthworks_summary(self._format_summary(summary))
            d.append_log("Anteprima movimenti terra aggiornata (nessun export).")
        except Exception as exc:
            self._warn(f"Anteprima movimenti terra fallita: {exc}")

    def _build_active_profile_for_alignment(self, align, terrain):
        d = self.dialog
        terrain_axis = terrain.sample_many(align.points)
        if self._profile_mode() == "pvi":
            if len(self.pvi_rows) < 2:
                self.reload_pvi_from_layer()
            return self.vp_builder.build_from_pvi(
                align.progressive,
                terrain_axis,
                self.pvi_rows,
                d.default_curve_length.value(),
            )
        return self.vp_builder.build(
            align.progressive,
            terrain_axis,
            d.long_slope_max.value(),
            d.vert_radius_min.value(),
            self._layer(d.cmb_forced.currentText()) if d.cmb_forced.currentText() else None,
            align.points,
        )

    def _surface_section_step(self) -> float:
        d = self.dialog
        if not d:
            return 1.0
        surface_step = float(d.surface_section_step.value() or 0.0)
        if surface_step > 0:
            return surface_step
        return max(0.01, float(d.section_step.value() or 1.0))

    def suggest_minimum_earthworks_profile(self):
        d = self.dialog
        if not d:
            return
        if self._profile_mode() != "pvi":
            self._warn("Il suggerimento profilo è disponibile solo in modalità PVI.")
            return
        unlocked = [i for i, r in enumerate(self.pvi_rows) if not r.locked]
        if not unlocked:
            self._warn("Tutti i PVI sono bloccati: impossibile ottimizzare il profilo.")
            return
        try:
            align = self._build_alignment()
            if not align:
                return
            dtm = self._layer(d.cmb_dtm.currentText())
            polygon = self._layer(d.cmb_polygon.currentText())
            if not dtm or not polygon:
                self._warn("Selezionare DTM e poligono viabilità per il suggerimento profilo.")
                return
            terrain = self._build_terrain_provider(dtm, align.points)
            terrain_axis = terrain.sample_many(align.points)
            current_profile = self.vp_builder.build_from_pvi(align.progressive, terrain_axis, self.pvi_rows, d.default_curve_length.value())
            _s0, _v0, current_summary = self._compute_earthworks_for_profile(
                align,
                terrain,
                polygon,
                current_profile,
                section_step=self._surface_section_step(),
            )
            best_rows, best_summary = self._run_two_stage_optimizer(align, terrain_axis, terrain, polygon, unlocked)
            self.suggested_pvi_rows = best_rows
            self.suggested_profile = self.vp_builder.build_from_pvi(align.progressive, terrain_axis, best_rows, d.default_curve_length.value())
            self.rebuild_preview_profile()
            d.set_earthworks_summary(self._format_comparison_summary(current_summary, best_summary))
            d.append_log("Profilo suggerito a minimo movimento terra calcolato (non applicato).")
        except Exception as exc:
            self._warn(f"Suggerimento profilo fallito: {exc}")

    def _run_two_stage_optimizer(self, align, terrain_axis, terrain, polygon, unlocked_indices: List[int]) -> Tuple[List[PviRow], Dict[str, float]]:
        d = self.dialog
        base_rows = [PviRow(**vars(r)) for r in self.pvi_rows]
        rand = random.Random(42)
        candidates: List[Tuple[float, List[PviRow], Dict[str, float]]] = []
        restarts = min(5, max(2, len(unlocked_indices)))
        shortlist_size = min(3, restarts)
        quant_step = 0.20
        fine_quant_step = 0.10
        min_improvement = 0.10
        fast_sample_step = max(d.section_step.value() * 4.0, 8.0)
        fast_cache: Dict[Tuple[float, ...], Tuple[float, Dict[str, float]]] = {}
        full_cache: Dict[Tuple[float, ...], Tuple[float, Dict[str, float]]] = {}
        fast_eval_count = 0
        fast_cache_hits = 0
        full_eval_count = 0
        full_cache_hits = 0
        fast_context = self._build_fast_surrogate_context(align, terrain_axis, sample_step=fast_sample_step)

        d.append_log("Ottimizzazione: ricerca veloce in corso (surrogato longitudinale).")
        fast_start = time.perf_counter()
        best_fast_score = float("inf")
        no_restart_gain = 0
        for restart_idx in range(restarts):
            candidate = [PviRow(**vars(r)) for r in base_rows]
            for idx in unlocked_indices:
                jitter = rand.uniform(-0.8, 0.8) if restart_idx else 0.0
                candidate[idx].elevation += jitter
                candidate[idx].elevation = self._quantize_value(candidate[idx].elevation, quant_step)
            candidate = self.vp_builder.recompute_pvi_diagnostics(candidate, d.long_slope_max.value(), d.default_curve_length.value())
            score, summary, from_cache = self._evaluate_candidate_fast_surrogate(
                candidate,
                align,
                terrain_axis,
                fast_context,
                unlocked_indices,
                fast_cache,
                quant_step,
            )
            if from_cache:
                fast_cache_hits += 1
            else:
                fast_eval_count += 1
            descent_steps = [quant_step, fine_quant_step]
            for step in descent_steps:
                improved = True
                cycles_without_gain = 0
                max_cycles = max(2, len(unlocked_indices))
                while improved and cycles_without_gain < 2:
                    improved = False
                    cycle_gain = 0.0
                    for idx in unlocked_indices:
                        best_local = (score, [PviRow(**vars(r)) for r in candidate], summary)
                        for direction in (-1.0, 1.0):
                            trial = [PviRow(**vars(r)) for r in candidate]
                            trial[idx].elevation = self._quantize_value(trial[idx].elevation + direction * step, step)
                            trial = self.vp_builder.recompute_pvi_diagnostics(
                                trial, d.long_slope_max.value(), d.default_curve_length.value()
                            )
                            val, sm, from_cache = self._evaluate_candidate_fast_surrogate(
                                trial,
                                align,
                                terrain_axis,
                                fast_context,
                                unlocked_indices,
                                fast_cache,
                                step,
                            )
                            if from_cache:
                                fast_cache_hits += 1
                            else:
                                fast_eval_count += 1
                            if val < best_local[0]:
                                best_local = (val, trial, sm)
                        if best_local[0] < (score - min_improvement):
                            cycle_gain += score - best_local[0]
                            score, candidate, summary = best_local
                            improved = True
                    cycles_without_gain = cycles_without_gain + 1 if not improved else 0
                    if cycle_gain < min_improvement:
                        break
                    if max_cycles <= 0:
                        break
                    max_cycles -= 1
            candidates.append((score, candidate, summary))
            if score < (best_fast_score - min_improvement):
                best_fast_score = score
                no_restart_gain = 0
            else:
                no_restart_gain += 1
            if no_restart_gain >= 2:
                d.append_log("Ottimizzazione fast: arresto anticipato (restart senza miglioramenti).")
                break
        fast_elapsed = time.perf_counter() - fast_start
        candidates.sort(key=lambda x: x[0])
        top = candidates[: min(shortlist_size, len(candidates))]

        d.append_log(
            "Ottimizzazione coarse completata | candidati=%s | eval_fast=%s | cache_fast_hits=%s | "
            "cache_fast_size=%s | shortlist=%s | tempo=%.2fs | best_cost_fast=%.3f"
            % (len(candidates), fast_eval_count, fast_cache_hits, len(fast_cache), len(top), fast_elapsed, best_fast_score)
        )
        d.append_log(
            "Ottimizzazione: verifica finale accurata con sezioni complete sui migliori candidati."
        )

        fine_start = time.perf_counter()
        refined: List[Tuple[float, List[PviRow], Dict[str, float]]] = []
        for _score, rows, _summary in top:
            final_score, final_summary, from_cache = self._evaluate_candidate_full(
                [PviRow(**vars(r)) for r in rows],
                align,
                terrain_axis,
                terrain,
                polygon,
                unlocked_indices,
                full_cache,
            )
            if from_cache:
                full_cache_hits += 1
            else:
                full_eval_count += 1
            refined.append((final_score, rows, final_summary))
        refined.sort(key=lambda x: x[0])
        fine_elapsed = time.perf_counter() - fine_start
        d.append_log(
            "Ottimizzazione fine completata | eval_full=%s | cache_full_hits=%s | tempo=%.2fs | best_cost_final=%.3f"
            % (full_eval_count, full_cache_hits, fine_elapsed, refined[0][0])
        )
        return refined[0][1], refined[0][2]

    def _candidate_cache_key(self, candidate_rows: List[PviRow], unlocked_indices: List[int], rounding_digits: int) -> Tuple[float, ...]:
        return tuple(round(float(candidate_rows[idx].elevation), rounding_digits) for idx in unlocked_indices)

    def _candidate_cache_key_step(self, candidate_rows: List[PviRow], unlocked_indices: List[int], quant_step: float) -> Tuple[float, ...]:
        q = max(quant_step, 0.01)
        return tuple(round(round(float(candidate_rows[idx].elevation) / q) * q, 3) for idx in unlocked_indices)

    def _quantize_value(self, value: float, quant_step: float) -> float:
        q = max(quant_step, 0.01)
        return round(round(float(value) / q) * q, 3)

    def _build_fast_surrogate_context(self, align, terrain_axis: List[float], sample_step: float) -> Dict[str, List[float]]:
        progressive = align.progressive
        if not progressive:
            raise ValueError("Asse non valido per ottimizzazione fast.")
        sample_idx = [0]
        last_prog = progressive[0]
        for i in range(1, len(progressive) - 1):
            if (progressive[i] - last_prog) >= sample_step:
                sample_idx.append(i)
                last_prog = progressive[i]
        if sample_idx[-1] != (len(progressive) - 1):
            sample_idx.append(len(progressive) - 1)
        sample_prog = [progressive[i] for i in sample_idx]
        sample_terrain = [terrain_axis[i] for i in sample_idx]
        segment_ds = [sample_prog[i + 1] - sample_prog[i] for i in range(len(sample_prog) - 1)]
        return {
            "sample_idx": sample_idx,
            "sample_prog": sample_prog,
            "sample_terrain": sample_terrain,
            "segment_ds": segment_ds,
        }

    def _evaluate_candidate_fast_surrogate(
        self,
        candidate_rows: List[PviRow],
        align,
        terrain_axis,
        fast_context: Dict[str, List[float]],
        unlocked_indices: List[int],
        cache: Dict[Tuple[float, ...], Tuple[float, Dict[str, float]]],
        quant_step: float,
    ) -> Tuple[float, Dict[str, float], bool]:
        d = self.dialog
        key = self._candidate_cache_key_step(candidate_rows, unlocked_indices, quant_step)
        if key in cache:
            score, summary = cache[key]
            return score, dict(summary), True
        profile = self.vp_builder.build_from_pvi(align.progressive, terrain_axis, candidate_rows, d.default_curve_length.value())
        platform_width = max(1.0, float(d.min_width.value()))
        foundation_thickness = max(0.0, float(d.foundation_thickness.value()))
        cut_slope = max(0.1, float(d.cut_slope.value()))
        fill_slope = max(0.1, float(d.fill_slope.value()))
        sample_idx = fast_context["sample_idx"]
        sample_terrain = fast_context["sample_terrain"]
        segment_ds = fast_context["segment_ds"]
        sample_project = [profile.project_z[i] for i in sample_idx]
        sample_base = [z - foundation_thickness for z in sample_project]
        cut_vol = 0.0
        fill_vol = 0.0
        for i, ds in enumerate(segment_ds):
            h0 = sample_terrain[i] - sample_base[i]
            h1 = sample_terrain[i + 1] - sample_base[i + 1]
            cut_h0 = max(h0, 0.0)
            cut_h1 = max(h1, 0.0)
            fill_h0 = max(-h0, 0.0)
            fill_h1 = max(-h1, 0.0)
            cut_a0 = (platform_width * cut_h0) + (cut_slope * cut_h0 * cut_h0)
            cut_a1 = (platform_width * cut_h1) + (cut_slope * cut_h1 * cut_h1)
            fill_a0 = (platform_width * fill_h0) + (fill_slope * fill_h0 * fill_h0)
            fill_a1 = (platform_width * fill_h1) + (fill_slope * fill_h1 * fill_h1)
            cut_vol += 0.5 * (cut_a0 + cut_a1) * ds
            fill_vol += 0.5 * (fill_a0 + fill_a1) * ds
        length = max(fast_context["sample_prog"][-1] - fast_context["sample_prog"][0], 0.0)
        foundation_vol = platform_width * foundation_thickness * length
        summary = {
            "total_cut": cut_vol,
            "total_fill": fill_vol,
            "total_movement": cut_vol + fill_vol,
            "net_balance": cut_vol - fill_vol,
            "abs_balance": abs(cut_vol - fill_vol),
            "total_foundation": foundation_vol,
            "sections_count": len(sample_idx),
            "approx_count": 0,
        }
        score = self._score_candidate(candidate_rows, summary)
        cache[key] = (score, dict(summary))
        return score, summary, False

    def _evaluate_candidate_full(
        self,
        candidate_rows: List[PviRow],
        align,
        terrain_axis,
        terrain,
        polygon,
        unlocked_indices: List[int],
        cache: Dict[Tuple[float, ...], Tuple[float, Dict[str, float]]],
    ) -> Tuple[float, Dict[str, float], bool]:
        key = self._candidate_cache_key(candidate_rows, unlocked_indices, rounding_digits=3)
        if key in cache:
            score, summary = cache[key]
            return score, dict(summary), True
        score, summary = self._evaluate_candidate(candidate_rows, align, terrain_axis, terrain, polygon)
        cache[key] = (score, dict(summary))
        return score, summary, False

    def _score_candidate(self, candidate_rows, summary: Dict[str, float]) -> float:
        d = self.dialog
        moved = summary["total_movement"]
        roughness = 0.0
        for i in range(1, len(candidate_rows) - 1):
            g0 = self.vp_builder.incoming_slope_pct(candidate_rows, i) or 0.0
            g1 = self.vp_builder.outgoing_slope_pct(candidate_rows, i) or 0.0
            roughness += abs(g1 - g0)
        warn_pen = sum(1 for r in candidate_rows if r.warning) * 1000.0
        # Obiettivo lessicografico pesato:
        # 1) minimizzare il movimento complessivo terreno
        # 2) solo in seconda battuta minimizzare il disallineamento scavo/rilevato
        w_total = 1.0
        w_balance = 0.03
        score = (w_total * moved) + (w_balance * summary["abs_balance"]) + roughness * 5.0 + warn_pen
        return score

    def _evaluate_candidate(self, candidate_rows, align, terrain_axis, terrain, polygon) -> Tuple[float, Dict[str, float]]:
        d = self.dialog
        profile = self.vp_builder.build_from_pvi(align.progressive, terrain_axis, candidate_rows, d.default_curve_length.value())
        _sections, _vol, summary = self._compute_earthworks_for_profile(
            align,
            terrain,
            polygon,
            profile,
            section_step=self._surface_section_step(),
        )
        return self._score_candidate(candidate_rows, summary), summary

    def _format_comparison_summary(self, current: Dict[str, float], suggested: Dict[str, float]) -> str:
        return (
            "Confronto profilo attuale vs suggerito\n"
            f"- Scavo terreno attuale: {current['total_cut']:.2f} m³\n"
            f"- Rilevato terreno attuale: {current['total_fill']:.2f} m³\n"
            f"- Movimento terra complessivo attuale: {current['total_movement']:.2f} m³\n"
            f"- Bilancio attuale: {current['net_balance']:.2f} m³\n"
            f"- Volume massicciata attuale: {current['total_foundation']:.2f} m³\n\n"
            f"- Scavo terreno suggerito: {suggested['total_cut']:.2f} m³\n"
            f"- Rilevato terreno suggerito: {suggested['total_fill']:.2f} m³\n"
            f"- Movimento terra complessivo suggerito: {suggested['total_movement']:.2f} m³\n"
            f"- Bilancio suggerito: {suggested['net_balance']:.2f} m³\n"
            f"- Volume massicciata suggerito: {suggested['total_foundation']:.2f} m³\n\n"
            f"- Delta miglioramento movimento terra complessivo: "
            f"{(current['total_movement'] - suggested['total_movement']):.2f} m³\n"
            f"- Delta miglioramento bilancio assoluto: "
            f"{(current['abs_balance'] - suggested['abs_balance']):.2f} m³"
        )

    def apply_suggested_profile(self):
        if not self.suggested_pvi_rows:
            self._warn("Nessun profilo suggerito disponibile da applicare.")
            return
        for i, row in enumerate(self.pvi_rows):
            if row.locked:
                continue
            self.pvi_rows[i].elevation = self.suggested_pvi_rows[i].elevation
        if self.dialog:
            self.pvi_rows = self.vp_builder.recompute_pvi_diagnostics(
                self.pvi_rows,
                self.dialog.long_slope_max.value(),
                self.dialog.default_curve_length.value(),
            )
        self._refresh_pvi_table()
        self.rebuild_preview_profile()
        self._info("Profilo suggerito applicato ai PVI non bloccati.")
