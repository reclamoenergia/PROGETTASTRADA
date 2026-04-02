from __future__ import annotations

from qgis.PyQt.QtWidgets import (
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
    QVBoxLayout,
)


class MainDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Road Designer Plugin")
        self.resize(760, 800)
        root = QVBoxLayout(self)
        root.addWidget(self._build_input_group())
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
        gl.addWidget(QLabel("Punti quota (z)"), 3, 0)
        gl.addWidget(self.cmb_forced, 3, 1)
        return gb

    def _spin(self, value, mn, mx, step=0.1):
        s = QDoubleSpinBox()
        s.setDecimals(3)
        s.setRange(mn, mx)
        s.setSingleStep(step)
        s.setValue(value)
        return s

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
        self.cmb_terrain_source = QComboBox()
        self.cmb_terrain_source.addItems(["Raster DTM", "TIN from local contours"])
        self.tin_contour_interval = self._spin(1.0, 0.1, 100.0, 0.1)
        self.tin_processing_buffer = self._spin(120.0, 5.0, 5000.0, 5.0)
        self.tin_simplify_tolerance = self._spin(0.0, 0.0, 50.0, 0.1)
        self.chk_tin_add_contours = QCheckBox("Aggiungi curve locali a QGIS")
        self.chk_tin_add_triangles = QCheckBox("Aggiungi triangoli TIN a QGIS")
        self.chk_tin_cache = QCheckBox("Riusa TIN in sessione")
        self.chk_tin_cache.setChecked(True)
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
        gl.addWidget(QLabel("Sorgente terreno"), 9, 0)
        gl.addWidget(self.cmb_terrain_source, 9, 1)

        self.tin_group = QGroupBox("Parametri TIN locale")
        tin_gl = QGridLayout(self.tin_group)
        tin_gl.addWidget(QLabel("Intervallo curve [m]"), 0, 0)
        tin_gl.addWidget(self.tin_contour_interval, 0, 1)
        tin_gl.addWidget(QLabel("Buffer area locale [m]"), 1, 0)
        tin_gl.addWidget(self.tin_processing_buffer, 1, 1)
        tin_gl.addWidget(QLabel("Semplificazione curve [m]"), 2, 0)
        tin_gl.addWidget(self.tin_simplify_tolerance, 2, 1)
        tin_gl.addWidget(self.chk_tin_add_contours, 3, 0, 1, 2)
        tin_gl.addWidget(self.chk_tin_add_triangles, 4, 0, 1, 2)
        tin_gl.addWidget(self.chk_tin_cache, 5, 0, 1, 2)
        gl.addWidget(self.tin_group, 10, 0, 1, 2)

        self.cmb_terrain_source.currentIndexChanged.connect(self._toggle_tin_group)
        self._toggle_tin_group()
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

    def _toggle_tin_group(self):
        self.tin_group.setVisible(self.cmb_terrain_source.currentIndex() == 1)

    def append_log(self, text: str):
        self.log.appendPlainText(text)

    def select_combo_by_text(self, combo: QComboBox, text: str):
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
