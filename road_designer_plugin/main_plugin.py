from __future__ import annotations

import os
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
from .core.terrain_sampler import TerrainSampler
from .core.vertical_profile import VerticalProfileBuilder
from .core.width_analysis import WidthAnalysis
from .export.dxf_exporter import DxfExporter
from .export.tables_exporter import TablesExporter
from .ui.main_dialog import MainDialog


class RoadDesignerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action: Optional[QAction] = None
        self.dialog: Optional[MainDialog] = None

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

            terrain = TerrainSampler(dtm)
            terrain_axis = terrain.sample_many(align.points)
            profile = VerticalProfileBuilder().build(
                align.progressive,
                terrain_axis,
                d.long_slope_max.value(),
                d.vert_radius_min.value(),
                forced,
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
            for w in warn[:20]:
                d.append_log(f"WARNING: {w}")
            d.progress.setValue(80)

            self._run_exports(profile, sections, vol)
            d.progress.setValue(100)
            self._info("Calcolo completato con successo")
        except Exception as exc:
            self._warn(f"Errore durante il calcolo: {exc}")

    def _run_exports(self, profile, sections, vol):
        d = self.dialog
        if not d:
            return
        folder = d.output_folder.text().strip()
        if not folder:
            self._warn("Cartella output non impostata.")
            return
        name = d.project_name.text().strip() or "road_project"
        exp_dxf = DxfExporter()
        if d.chk_dxf_sections.isChecked():
            p = os.path.join(folder, f"{name}_sections.dxf")
            exp_dxf.export_sections(p, sections, d.min_width.value())
            d.append_log(f"DXF sezioni: {p}")
        if d.chk_dxf_profile.isChecked():
            p = os.path.join(folder, f"{name}_profile.dxf")
            exp_dxf.export_profile(p, profile)
            d.append_log(f"DXF profilo: {p}")
        if d.chk_csv.isChecked():
            p = os.path.join(folder, f"{name}_volumes.csv")
            TablesExporter().export_volumes_csv(p, vol)
            d.append_log(f"CSV volumi: {p}")

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
