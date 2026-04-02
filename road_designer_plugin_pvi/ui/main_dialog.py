from __future__ import annotations

from typing import List, Sequence, Tuple

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ProfilePreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._progressive: List[float] = []
        self._terrain: List[float] = []
        self._project: List[float] = []
        self._pvi: List[Tuple[float, float]] = []

    def set_data(
        self,
        progressive: Sequence[float],
        terrain_z: Sequence[float],
        project_z: Sequence[float],
        pvi_points: Sequence[Tuple[float, float]],
    ):
        self._progressive = list(progressive)
        self._terrain = list(terrain_z)
        self._project = list(project_z)
        self._pvi = list(pvi_points)
        self.update()

    def clear_data(self):
        self._progressive = []
        self._terrain = []
        self._project = []
        self._pvi = []
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))

        if not self._progressive or not self._terrain or not self._project:
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Anteprima profilo non disponibile")
            return

        margin = 26
        draw_w = max(1, self.width() - margin * 2)
        draw_h = max(1, self.height() - margin * 2)

        x_min = self._progressive[0]
        x_max = self._progressive[-1]
        z_all = self._terrain + self._project + [z for _, z in self._pvi]
        z_min = min(z_all)
        z_max = max(z_all)
        if abs(x_max - x_min) < 1e-9 or abs(z_max - z_min) < 1e-9:
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Range profilo insufficiente")
            return

        def map_pt(s: float, z: float) -> Tuple[int, int]:
            x = margin + int((s - x_min) / (x_max - x_min) * draw_w)
            y = margin + int((z_max - z) / (z_max - z_min) * draw_h)
            return x, y

        painter.setPen(QPen(QColor("#dddddd"), 1))
        painter.drawRect(margin, margin, draw_w, draw_h)

        self._draw_line(painter, self._progressive, self._terrain, QColor("#808080"), map_pt)
        self._draw_line(painter, self._progressive, self._project, QColor("#0d5fb8"), map_pt)

        painter.setPen(QPen(QColor("#cc2d2d"), 2))
        for s, z in self._pvi:
            x, y = map_pt(s, z)
            painter.drawEllipse(x - 3, y - 3, 6, 6)

    def _draw_line(self, painter, x_vals, y_vals, color, mapper):
        painter.setPen(QPen(color, 2))
        for i in range(1, min(len(x_vals), len(y_vals))):
            x0, y0 = mapper(x_vals[i - 1], y_vals[i - 1])
            x1, y1 = mapper(x_vals[i], y_vals[i])
            painter.drawLine(x0, y0, x1, y1)


class MainDialog(QDialog):
    PVI_HEADERS = [
        "#",
        "Progressiva",
        "Quota",
        "L curva [m]",
        "Pendenza in [%]",
        "Pendenza out [%]",
        "Stato",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Road Designer Plugin PVI")
        self.resize(920, 960)
        root = QVBoxLayout(self)
        root.addWidget(self._build_input_group())
        root.addWidget(self._build_vertical_profile_group())
        root.addWidget(self._build_geom_group())
        root.addWidget(self._build_sampling_group())
        root.addWidget(self._build_output_group())
        root.addWidget(self._build_json_group())
        root.addWidget(self._build_actions_group())

    def _build_input_group(self):
        gb = QGroupBox("INPUT")
        gl = QGridLayout(gb)
        self.cmb_dtm = QComboBox()
        self.cmb_axis = QComboBox()
        self.cmb_polygon = QComboBox()
        self.cmb_forced = QComboBox()
        gl.addWidget(QLabel("DTM raster"), 0, 0)
        gl.addWidget(self.cmb_dtm, 0, 1)
        gl.addWidget(QLabel("Asse lineare"), 1, 0)
        gl.addWidget(self.cmb_axis, 1, 1)
        gl.addWidget(QLabel("Poligono viabilità"), 2, 0)
        gl.addWidget(self.cmb_polygon, 2, 1)
        gl.addWidget(QLabel("Punti quota (z) automatico"), 3, 0)
        gl.addWidget(self.cmb_forced, 3, 1)
        return gb

    def _spin(self, value, mn, mx, step=0.1):
        s = QDoubleSpinBox()
        s.setDecimals(3)
        s.setRange(mn, mx)
        s.setSingleStep(step)
        s.setValue(value)
        return s

    def _build_vertical_profile_group(self):
        gb = QGroupBox("PROFILO VERTICALE")
        vl = QVBoxLayout(gb)

        top = QGridLayout()
        self.cmb_profile_mode = QComboBox()
        self.cmb_profile_mode.addItem("Automatico (attuale)", "automatic")
        self.cmb_profile_mode.addItem("Profilo da PVI geometrici", "pvi")
        self.cmb_pvi_layer = QComboBox()
        self.cmb_pvi_elev_field = QComboBox()
        self.cmb_pvi_curve_field = QComboBox()
        self.cmb_pvi_curve_field.addItem("")
        self.default_curve_length = self._spin(0.0, 0.0, 10000.0, 1.0)
        self.btn_reload_pvi = QPushButton("Ricarica PVI da layer")
        self.btn_reset_pvi = QPushButton("Reset modifiche PVI")

        top.addWidget(QLabel("Modalità"), 0, 0)
        top.addWidget(self.cmb_profile_mode, 0, 1)
        top.addWidget(QLabel("Layer punti PVI"), 1, 0)
        top.addWidget(self.cmb_pvi_layer, 1, 1)
        top.addWidget(QLabel("Campo quota"), 2, 0)
        top.addWidget(self.cmb_pvi_elev_field, 2, 1)
        top.addWidget(QLabel("Campo lunghezza curva"), 3, 0)
        top.addWidget(self.cmb_pvi_curve_field, 3, 1)
        top.addWidget(QLabel("Lunghezza curva default [m]"), 4, 0)
        top.addWidget(self.default_curve_length, 4, 1)
        btns = QHBoxLayout()
        btns.addWidget(self.btn_reload_pvi)
        btns.addWidget(self.btn_reset_pvi)
        top.addLayout(btns, 5, 1)
        vl.addLayout(top)

        self.tbl_pvi = QTableWidget(0, len(self.PVI_HEADERS))
        self.tbl_pvi.setHorizontalHeaderLabels(self.PVI_HEADERS)
        self.tbl_pvi.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_pvi.setAlternatingRowColors(True)
        self.tbl_pvi.verticalHeader().setVisible(False)
        vl.addWidget(self.tbl_pvi)

        self.preview = ProfilePreviewWidget()
        vl.addWidget(self.preview)

        self.lbl_pvi_status = QLabel("")
        vl.addWidget(self.lbl_pvi_status)
        return gb

    def _build_geom_group(self):
        gb = QGroupBox("PARAMETRI GEOMETRICI")
        gl = QGridLayout(gb)
        self.min_width = self._spin(5, 1, 200)
        self.crossfall_nominal = self._spin(3, 0, 30)
        self.crossfall_min = self._spin(2, 0, 30)
        self.crossfall_max = self._spin(6, 0, 30)
        self.long_slope_max = self._spin(12, 0, 100)
        self.plan_radius_min = self._spin(40, 1, 10000)
        self.vert_radius_min = self._spin(250, 1, 100000)
        self.cut_slope = self._spin(1.5, 0.1, 100)
        self.fill_slope = self._spin(1.8, 0.1, 100)
        self.pad_slope = self._spin(2, 0, 30)
        widgets = [
            ("Larghezza minima piattaforma", self.min_width),
            ("Pendenza trasv. nominale %", self.crossfall_nominal),
            ("Pendenza trasv. minima %", self.crossfall_min),
            ("Pendenza trasv. massima %", self.crossfall_max),
            ("Pendenza longitudinale max %", self.long_slope_max),
            ("Raggio minimo planimetrico", self.plan_radius_min),
            ("Raggio minimo verticale", self.vert_radius_min),
            ("Pendenza sterro (H:V)", self.cut_slope),
            ("Pendenza rilevato (H:V)", self.fill_slope),
            ("Pendenza piazzola %", self.pad_slope),
        ]
        for r, (label, w) in enumerate(widgets):
            gl.addWidget(QLabel(label), r, 0)
            gl.addWidget(w, r, 1)
        return gb

    def _build_sampling_group(self):
        gb = QGroupBox("CAMPIONAMENTO")
        gl = QGridLayout(gb)
        self.axis_step = self._spin(5, 0.5, 1000)
        self.section_step = self._spin(20, 1, 1000)
        self.section_length = self._spin(80, 5, 1000)
        self.section_sample_step = self._spin(1, 0.1, 10)
        self.profile_h_scale = self._spin(1000, 50, 20000, 10)
        self.profile_v_scale = self._spin(200, 10, 5000, 10)
        self.section_scale = self._spin(200, 10, 5000, 10)
        self.section_vertical_exaggeration = self._spin(2, 0.1, 20, 0.1)
        self.section_quote_step = self._spin(5, 0.1, 100, 0.1)
        gl.addWidget(QLabel("Passo lungo asse"), 0, 0)
        gl.addWidget(self.axis_step, 0, 1)
        gl.addWidget(QLabel("Passo sezioni"), 1, 0)
        gl.addWidget(self.section_step, 1, 1)
        gl.addWidget(QLabel("Lunghezza sezione"), 2, 0)
        gl.addWidget(self.section_length, 2, 1)
        gl.addWidget(QLabel("Passo campionamento sezione"), 3, 0)
        gl.addWidget(self.section_sample_step, 3, 1)
        gl.addWidget(QLabel("Scala profilo orizzontale (1:n)"), 4, 0)
        gl.addWidget(self.profile_h_scale, 4, 1)
        gl.addWidget(QLabel("Scala profilo verticale (1:n)"), 5, 0)
        gl.addWidget(self.profile_v_scale, 5, 1)
        gl.addWidget(QLabel("Scala sezioni (1:n)"), 6, 0)
        gl.addWidget(self.section_scale, 6, 1)
        gl.addWidget(QLabel("Esagerazione verticale sezioni"), 7, 0)
        gl.addWidget(self.section_vertical_exaggeration, 7, 1)
        gl.addWidget(QLabel("Passo quotazione sezione [m]"), 8, 0)
        gl.addWidget(self.section_quote_step, 8, 1)
        return gb

    def _build_output_group(self):
        gb = QGroupBox("OUTPUT")
        gl = QGridLayout(gb)
        self.output_folder = QLineEdit()
        self.project_name = QLineEdit("road_project")
        self.btn_browse = QPushButton("Sfoglia...")
        self.chk_dxf_sections = QCheckBox("Export DXF sezioni")
        self.chk_dxf_sections.setChecked(True)
        self.chk_dxf_profile = QCheckBox("Export DXF profilo")
        self.chk_dxf_profile.setChecked(True)
        self.chk_csv = QCheckBox("Export CSV volumi")
        self.chk_csv.setChecked(True)
        self.btn_browse.clicked.connect(self._choose_folder)
        gl.addWidget(QLabel("Cartella output"), 0, 0)
        gl.addWidget(self.output_folder, 0, 1)
        gl.addWidget(self.btn_browse, 0, 2)
        gl.addWidget(QLabel("Nome progetto"), 1, 0)
        gl.addWidget(self.project_name, 1, 1)
        gl.addWidget(self.chk_dxf_sections, 2, 0, 1, 2)
        gl.addWidget(self.chk_dxf_profile, 3, 0, 1, 2)
        gl.addWidget(self.chk_csv, 4, 0, 1, 2)
        return gb

    def _build_json_group(self):
        gb = QGroupBox("PARAMETRI JSON")
        hl = QHBoxLayout(gb)
        self.btn_load_json = QPushButton("Carica parametri JSON")
        self.btn_save_json = QPushButton("Salva parametri JSON")
        hl.addWidget(self.btn_load_json)
        hl.addWidget(self.btn_save_json)
        return gb

    def _build_actions_group(self):
        gb = QGroupBox("AZIONI")
        vl = QVBoxLayout(gb)
        self.btn_calculate = QPushButton("Calcola")
        self.progress = QProgressBar()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        vl.addWidget(self.btn_calculate)
        vl.addWidget(self.progress)
        vl.addWidget(self.log)
        return gb

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona cartella output")
        if folder:
            self.output_folder.setText(folder)

    def append_log(self, text: str):
        self.log.appendPlainText(text)

    def select_combo_by_text(self, combo: QComboBox, text: str):
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def set_pvi_table_enabled(self, enabled: bool):
        self.cmb_pvi_layer.setEnabled(enabled)
        self.cmb_pvi_elev_field.setEnabled(enabled)
        self.cmb_pvi_curve_field.setEnabled(enabled)
        self.default_curve_length.setEnabled(enabled)
        self.btn_reload_pvi.setEnabled(enabled)
        self.btn_reset_pvi.setEnabled(enabled)
        self.tbl_pvi.setEnabled(enabled)
