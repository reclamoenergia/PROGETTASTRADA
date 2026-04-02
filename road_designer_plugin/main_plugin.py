from __future__ import annotations

import os
import traceback
import warnings
from typing import Optional

from qgis.PyQt.QtWidgets import QAction, QFileDialog
from qgis.core import QgsProject, Qgis

from .core.alignment import AlignmentBuilder
from .core.constraints import ConstraintChecker
from .core.cross_sections import CrossSectionGenerator
from .core.earthworks import EarthworksCalculator
from .core.input_manager import InputManager
from .core.road_model import RoadModelBuilder
from .core.settings_manager import SettingsManager
from .core.raster_terrain_provider import RasterTerrainProvider
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
        self.tin_builder = TinBuilder()

    def initGui(self):
        self.action = QAction("Road Designer Plugin", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&Road Designer", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Road Designer", self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        if self.dialog is None:
            self.dialog = MainDialog(self.iface.mainWindow())
            self.dialog.btn_calculate.clicked.connect(self.calculate)
            self.dialog.btn_save_json.clicked.connect(self.save_json)
            self.dialog.btn_load_json.clicked.connect(self.load_json)
        self.refresh_layers()
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
        self.dialog.cmb_forced.addItem("")
        for lyr in all_layers:
            if lyr.type() == lyr.RasterLayer:
                self.dialog.cmb_dtm.addItem(lyr.name())
            else:
                wkb = lyr.wkbType()
                if lyr.geometryType() == 1:
                    self.dialog.cmb_axis.addItem(lyr.name())
                elif lyr.geometryType() == 2:
                    self.dialog.cmb_polygon.addItem(lyr.name())
                elif lyr.geometryType() == 0:
                    self.dialog.cmb_forced.addItem(lyr.name())

    def _layer(self, name: str):
        layers = QgsProject.instance().mapLayersByName(name)
        return layers[0] if layers else None

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
            if hasattr(terrain, "sample_many"):
                terrain_axis = terrain.sample_many(align.points)
            else:
                terrain_axis = terrain.sample_along_points(align.points)
            profile = VerticalProfileBuilder().build(
                align.progressive,
                terrain_axis,
                d.long_slope_max.value(),
                d.vert_radius_min.value(),
                forced,
                align.points,
            )
            d.append_log("Profilo longitudinale di progetto calcolato")
            d.progress.setValue(45)

            sections = CrossSectionGenerator().generate(
                align,
                terrain,
                d.section_step.value(),
                d.section_length.value(),
                d.section_sample_step.value(),
            )
            wa = WidthAnalysis(polygon, d.min_width.value())
            sec_gen = CrossSectionGenerator()
            model = RoadModelBuilder()
            ew = EarthworksCalculator()
            for sec in sections:
                sec.width_info = wa.analyze(sec_gen.as_geometry(sec), sec.axis_point)
                model.build_section_profile(sec, profile, d.min_width.value(), d.crossfall_nominal.value(), d.pad_slope.value())
                model.add_side_slopes(sec, d.cut_slope.value(), d.fill_slope.value())
                ew.compute_section_areas(sec)
            d.append_log(f"Sezioni generate: {len(sections)}")
            d.progress.setValue(70)

            vol = ew.compute_volumes(sections)
            d.append_log(f"Volumi: Sterro={vol.total_cut:.2f} m3, Riporto={vol.total_fill:.2f} m3")

            warn = ConstraintChecker().check_longitudinal(profile, d.long_slope_max.value())
            warn += ConstraintChecker().check_crossfall(sections, d.crossfall_min.value(), d.crossfall_max.value())
            for sec in sections:
                warn.extend([f"Sezione {sec.index}: {w}" for w in sec.warnings])
            for w in warn[:20]:
                d.append_log(f"WARNING: {w}")
            d.progress.setValue(80)

            self._run_exports(align, axis, profile, sections, vol)
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

    def _run_exports(self, align, axis_layer, profile, sections, vol):
        d = self.dialog
        if not d:
            return
        folder = d.output_folder.text().strip()
        if not folder:
            d.append_log("WARNING: Cartella output non impostata: i layer vettoriali saranno creati solo in memoria.")
        name = d.project_name.text().strip() or "road_project"
        crs_authid = axis_layer.crs().authid() if axis_layer and axis_layer.crs().isValid() else QgsProject.instance().crs().authid()

        def _vector_export():
            vec_result = VectorExporter().export_outputs(align, sections, folder, name, crs_authid)
            d.append_log(
                "Layer QGIS creati: "
                f"{vec_result['axis_layer_name']}, {vec_result['sections_layer_name']}, "
                f"{vec_result['slopes_layer_name']}, {vec_result['surface_layer_name']}"
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
            sm.apply_ui_state(d, sm.load_from_json(path))
            self._info("Parametri caricati")
        except Exception as exc:
            self._warn(f"Caricamento JSON fallito: {exc}")

    def _warn(self, msg: str):
        if self.dialog:
            self.dialog.append_log(f"ERRORE: {msg}")
        self.iface.messageBar().pushMessage("Road Designer", msg, level=Qgis.Warning, duration=8)

    def _info(self, msg: str):
        if self.dialog:
            self.dialog.append_log(msg)
        self.iface.messageBar().pushMessage("Road Designer", msg, level=Qgis.Info, duration=5)
