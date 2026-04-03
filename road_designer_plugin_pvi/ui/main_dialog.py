from __future__ import annotations

from typing import List, Sequence, Tuple

from qgis.PyQt.QtCore import Qt, pyqtSignal
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
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ProfilePreviewWidget(QWidget):
    pviDragged = pyqtSignal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._progressive: List[float] = []
        self._terrain: List[float] = []
        self._project: List[float] = []
        self._pvi: List[Tuple[float, float]] = []
        self._drag_idx: int = -1
        self._drag_hover_idx: int = -1
        self._draw_rect = (0, 0, 0, 0)
        self._z_range = (0.0, 1.0)

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
        self._drag_idx = -1
        self._drag_hover_idx = -1
        self.update()

    def clear_data(self):
        self._progressive = []
        self._terrain = []
        self._project = []
        self._pvi = []
        self._drag_idx = -1
        self._drag_hover_idx = -1
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("white"))

        if not self._progressive or not self._terrain or not self._project:
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Anteprima profilo non disponibile")
            return

        left_margin = 70
        right_margin = 24
        top_margin = 18
        bottom_margin = 48
        draw_w = max(1, self.width() - left_margin - right_margin)
        draw_h = max(1, self.height() - top_margin - bottom_margin)
        self._draw_rect = (left_margin, top_margin, draw_w, draw_h)

        x_min = self._progressive[0]
        x_max = self._progressive[-1]
        z_all = self._terrain + self._project + [z for _, z in self._pvi]
        z_min = min(z_all)
        z_max = max(z_all)
        z_pad = max((z_max - z_min) * 0.06, 0.25)
        z_min -= z_pad
        z_max += z_pad
        self._z_range = (z_min, z_max)
        if abs(x_max - x_min) < 1e-9 or abs(z_max - z_min) < 1e-9:
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Range profilo insufficiente")
            return

        def map_pt(s: float, z: float) -> Tuple[int, int]:
            x = left_margin + int((s - x_min) / (x_max - x_min) * draw_w)
            y = top_margin + int((z_max - z) / (z_max - z_min) * draw_h)
            return x, y

        self._draw_grid_and_axes(
            painter,
            x_min,
            x_max,
            z_min,
            z_max,
            left_margin,
            top_margin,
            draw_w,
            draw_h,
        )

        painter.setPen(QPen(QColor("#dddddd"), 1))
        painter.drawRect(left_margin, top_margin, draw_w, draw_h)

        self._draw_line(painter, self._progressive, self._terrain, QColor("#808080"), map_pt)
        self._draw_line(painter, self._progressive, self._project, QColor("#0d5fb8"), map_pt)
        self._draw_slope_labels(painter, map_pt)

        painter.setPen(QPen(QColor("#cc2d2d"), 2))
        for s, z in self._pvi:
            x, y = map_pt(s, z)
            painter.drawEllipse(x - 3, y - 3, 6, 6)

        if 0 <= self._drag_hover_idx < len(self._pvi):
            hs, hz = self._pvi[self._drag_hover_idx]
            hx, hy = map_pt(hs, hz)
            painter.setPen(QPen(QColor("#8a1414"), 2))
            painter.drawEllipse(hx - 5, hy - 5, 10, 10)
            painter.setPen(QColor("#4a4a4a"))
            painter.drawText(hx + 8, hy - 10, f"s={hs:.2f} m  z={hz:.2f} m")

    def _draw_line(self, painter, x_vals, y_vals, color, mapper):
        painter.setPen(QPen(color, 2))
        for i in range(1, min(len(x_vals), len(y_vals))):
            x0, y0 = mapper(x_vals[i - 1], y_vals[i - 1])
            x1, y1 = mapper(x_vals[i], y_vals[i])
            painter.drawLine(x0, y0, x1, y1)

    def _draw_grid_and_axes(
        self,
        painter: QPainter,
        x_min: float,
        x_max: float,
        z_min: float,
        z_max: float,
        left: int,
        top: int,
        draw_w: int,
        draw_h: int,
    ):
        x_ticks = self._build_ticks(x_min, x_max, 7)
        z_ticks = self._build_ticks(z_min, z_max, 6)

        painter.setPen(QPen(QColor("#efefef"), 1))
        for x_val in x_ticks:
            ratio = (x_val - x_min) / (x_max - x_min)
            x = left + int(ratio * draw_w)
            painter.drawLine(x, top, x, top + draw_h)
        for z_val in z_ticks:
            ratio = (z_max - z_val) / (z_max - z_min)
            y = top + int(ratio * draw_h)
            painter.drawLine(left, y, left + draw_w, y)

        painter.setPen(QPen(QColor("#707070"), 1))
        painter.drawRect(left, top, draw_w, draw_h)

        for x_val in x_ticks:
            ratio = (x_val - x_min) / (x_max - x_min)
            x = left + int(ratio * draw_w)
            painter.drawLine(x, top + draw_h, x, top + draw_h + 4)
            painter.drawText(x - 32, top + draw_h + 18, 64, 16, Qt.AlignHCenter, f"{x_val:.1f}")

        for z_val in z_ticks:
            ratio = (z_max - z_val) / (z_max - z_min)
            y = top + int(ratio * draw_h)
            painter.drawLine(left - 4, y, left, y)
            painter.drawText(4, y - 8, left - 10, 16, Qt.AlignRight | Qt.AlignVCenter, f"{z_val:.2f}")

        painter.setPen(QColor("#444444"))
        painter.drawText(left + (draw_w // 2) - 80, top + draw_h + 34, 160, 16, Qt.AlignCenter, "Progressiva [m]")
        painter.save()
        painter.translate(20, top + draw_h // 2)
        painter.rotate(-90)
        painter.drawText(-70, -6, 140, 16, Qt.AlignCenter, "Quota [m]")
        painter.restore()

    def _build_ticks(self, min_val: float, max_val: float, target_count: int) -> List[float]:
        if target_count < 2 or max_val <= min_val:
            return [min_val, max_val]

        raw_step = (max_val - min_val) / (target_count - 1)
        magnitude = 10 ** int(f"{raw_step:e}".split("e")[1])
        norm = raw_step / magnitude
        if norm <= 1:
            step = 1 * magnitude
        elif norm <= 2:
            step = 2 * magnitude
        elif norm <= 5:
            step = 5 * magnitude
        else:
            step = 10 * magnitude

        first = int(min_val / step) * step
        if first < min_val:
            first += step
        ticks = [min_val]
        val = first
        guard = 0
        while val < max_val and guard < 200:
            ticks.append(val)
            val += step
            guard += 1
        ticks.append(max_val)
        return sorted(set(ticks))

    def _draw_slope_labels(self, painter: QPainter, mapper):
        if len(self._pvi) < 2:
            return

        painter.setPen(QColor("#1f4a8a"))
        min_x_gap = 56
        last_text_x = -10_000
        for i in range(len(self._pvi) - 1):
            s0, z0 = self._pvi[i]
            s1, z1 = self._pvi[i + 1]
            ds = s1 - s0
            if abs(ds) < 1e-6:
                continue
            slope_pct = ((z1 - z0) / ds) * 100.0
            label = f"{slope_pct:+.2f}%"
            xm = (s0 + s1) / 2.0
            zm = (z0 + z1) / 2.0
            x, y = mapper(xm, zm)
            if abs(x - last_text_x) < min_x_gap:
                continue
            painter.drawText(x - 35, y - 16, 70, 14, Qt.AlignCenter, label)
            last_text_x = x

    def _map_y_to_elevation(self, y: float) -> float:
        left, top, _draw_w, draw_h = self._draw_rect
        z_min, z_max = self._z_range
        if draw_h <= 0 or z_max <= z_min:
            return z_min
        y = max(top, min(top + draw_h, y))
        ratio = (y - top) / draw_h
        return z_max - ratio * (z_max - z_min)

    def _find_pvi_at(self, pos) -> int:
        if not self._pvi or not self._progressive:
            return -1
        left, top, draw_w, draw_h = self._draw_rect
        x_min = self._progressive[0]
        x_max = self._progressive[-1]
        z_min, z_max = self._z_range
        if draw_w <= 0 or draw_h <= 0 or x_max <= x_min or z_max <= z_min:
            return -1

        def map_pt(s: float, z: float) -> Tuple[float, float]:
            x = left + ((s - x_min) / (x_max - x_min) * draw_w)
            y = top + ((z_max - z) / (z_max - z_min) * draw_h)
            return x, y

        best_idx = -1
        best_dist = 1.0e9
        for idx, (s, z) in enumerate(self._pvi):
            x, y = map_pt(s, z)
            d2 = (x - pos.x()) ** 2 + (y - pos.y()) ** 2
            if d2 < best_dist:
                best_dist = d2
                best_idx = idx
        return best_idx if best_dist <= 100 else -1

    def _event_pos(self, event):
        return event.position() if hasattr(event, "position") else event.pos()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_idx = self._find_pvi_at(self._event_pos(event))
            self._drag_hover_idx = self._drag_idx
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_idx >= 0:
            ev_pos = self._event_pos(event)
            new_z = self._map_y_to_elevation(ev_pos.y())
            s, _old_z = self._pvi[self._drag_idx]
            self._pvi[self._drag_idx] = (s, new_z)
            self._drag_hover_idx = self._drag_idx
            self.pviDragged.emit(self._drag_idx, new_z)
            self.update()
        else:
            hover_idx = self._find_pvi_at(self._event_pos(event))
            if hover_idx != self._drag_hover_idx:
                self._drag_hover_idx = hover_idx
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_idx = -1
            self.update()
        super().mouseReleaseEvent(event)


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
        self.resize(920, 840)
        root = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.addWidget(self._build_input_group())
        form_layout.addWidget(self._build_geom_group())
        form_layout.addWidget(self._build_sampling_group())
        form_layout.addWidget(self._build_vertical_profile_group())
        form_layout.addWidget(self._build_output_group())
        form_layout.addWidget(self._build_json_group())
        form_layout.addStretch(1)
        scroll_area.setWidget(form_container)
        root.addWidget(scroll_area, 1)
        root.addWidget(self._build_actions_group())
        self._set_parameter_tooltips()

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
        self.btn_add_pvi = QPushButton("Aggiungi PVI")
        self.btn_remove_pvi = QPushButton("Rimuovi PVI selezionato")
        btns.addWidget(self.btn_add_pvi)
        btns.addWidget(self.btn_remove_pvi)
        top.addLayout(btns, 5, 1)
        vl.addLayout(top)

        self.tbl_pvi = QTableWidget(0, len(self.PVI_HEADERS))
        self.tbl_pvi.setHorizontalHeaderLabels(self.PVI_HEADERS)
        self.tbl_pvi.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_pvi.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_pvi.setAlternatingRowColors(True)
        self.tbl_pvi.verticalHeader().setVisible(False)
        self.tbl_pvi.setMinimumHeight(200)
        self.tbl_pvi.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        vl.addWidget(self.tbl_pvi)

        self.preview = ProfilePreviewWidget()
        self.preview.setMinimumHeight(260)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
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
        self.section_buffer = self._spin(5, 0.1, 200)
        self.section_sample_step = self._spin(1, 0.1, 10)
        self.profile_h_scale = self._spin(1000, 50, 20000, 10)
        self.profile_v_scale = self._spin(200, 10, 5000, 10)
        self.section_scale = self._spin(200, 10, 5000, 10)
        self.section_vertical_exaggeration = self._spin(2, 0.1, 20, 0.1)
        self.section_quote_step = self._spin(5, 0.1, 100, 0.1)
        self.max_cartigli_per_sheet = QSpinBox()
        self.max_cartigli_per_sheet.setRange(1, 64)
        self.max_cartigli_per_sheet.setValue(6)
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
        gl.addWidget(QLabel("LUNGHEZZA MAX SEZIONE"), 2, 0)
        gl.addWidget(self.section_length, 2, 1)
        gl.addWidget(QLabel("BUFFER LATERALE SEZIONE [m]"), 3, 0)
        gl.addWidget(self.section_buffer, 3, 1)
        gl.addWidget(QLabel("Passo campionamento sezione"), 4, 0)
        gl.addWidget(self.section_sample_step, 4, 1)
        gl.addWidget(QLabel("Scala profilo orizzontale (1:n)"), 5, 0)
        gl.addWidget(self.profile_h_scale, 5, 1)
        gl.addWidget(QLabel("Scala profilo verticale (1:n)"), 6, 0)
        gl.addWidget(self.profile_v_scale, 6, 1)
        gl.addWidget(QLabel("Scala sezioni (1:n)"), 7, 0)
        gl.addWidget(self.section_scale, 7, 1)
        gl.addWidget(QLabel("Esagerazione verticale sezioni"), 8, 0)
        gl.addWidget(self.section_vertical_exaggeration, 8, 1)
        gl.addWidget(QLabel("Passo quotazione sezione [m]"), 9, 0)
        gl.addWidget(self.section_quote_step, 9, 1)
        gl.addWidget(QLabel("NUMERO MASSIMO CARTIGLI PER FOGLIO"), 10, 0)
        gl.addWidget(self.max_cartigli_per_sheet, 10, 1)
        gl.addWidget(QLabel("Sorgente terreno"), 11, 0)
        gl.addWidget(self.cmb_terrain_source, 11, 1)

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
        gl.addWidget(self.tin_group, 12, 0, 1, 2)

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

    def _set_parameter_tooltips(self):
        self.cmb_dtm.setToolTip(
            "Seleziona il raster DTM da usare come superficie del terreno. "
            "Influisce sulle quote campionate lungo asse, profilo e sezioni."
        )
        self.cmb_axis.setToolTip(
            "Scegli il layer lineare dell'asse stradale. "
            "Definisce la geometria di riferimento per tutto il progetto."
        )
        self.cmb_polygon.setToolTip(
            "Layer poligonale dell'area viabile da analizzare. "
            "Serve per vincolare le elaborazioni spaziali locali."
        )
        self.cmb_forced.setToolTip(
            "Layer punti quota automatici da usare come vincoli altimetrici. "
            "I punti selezionati influenzano la ricostruzione del profilo."
        )

        self.min_width.setToolTip(
            "Larghezza minima della piattaforma stradale in metri [m]. "
            "Valori maggiori aumentano l'area occupata."
        )
        self.crossfall_nominal.setToolTip(
            "Pendenza trasversale nominale in percentuale [%]. "
            "È il valore obiettivo usato nel modello geometrico."
        )
        self.crossfall_min.setToolTip(
            "Limite minimo della pendenza trasversale [%]. "
            "Valori troppo bassi possono peggiorare il drenaggio."
        )
        self.crossfall_max.setToolTip(
            "Limite massimo della pendenza trasversale [%]. "
            "Valori alti aumentano l'inclinazione laterale."
        )
        self.long_slope_max.setToolTip(
            "Pendenza longitudinale massima ammessa [%]. "
            "Controlla il gradiente massimo del profilo di progetto."
        )
        self.plan_radius_min.setToolTip(
            "Raggio minimo planimetrico in metri [m]. "
            "Valori maggiori producono curve orizzontali più ampie."
        )
        self.vert_radius_min.setToolTip(
            "Raggio minimo verticale in metri [m]. "
            "Valori maggiori rendono i raccordi verticali più dolci."
        )
        self.cut_slope.setToolTip(
            "Pendenza di sterro espressa come rapporto H:V. "
            "Influisce sulla geometria delle scarpate in scavo."
        )
        self.fill_slope.setToolTip(
            "Pendenza di rilevato espressa come rapporto H:V. "
            "Influisce sulla geometria delle scarpate in riporto."
        )
        self.pad_slope.setToolTip(
            "Pendenza della piazzola in percentuale [%]. "
            "Valori maggiori aumentano l'inclinazione della superficie."
        )

        self.axis_step.setToolTip(
            "Passo di campionamento lungo asse in metri [m]. "
            "Un passo più piccolo aumenta dettaglio e tempi di calcolo."
        )
        self.section_step.setToolTip(
            "Distanza tra sezioni consecutive in metri [m]. "
            "Valori minori generano più sezioni."
        )
        self.section_length.setToolTip(
            "Lunghezza massima della sezione in metri [m]. "
            "Usata come limite superiore/fallback quando la scarpata non viene intercettata."
        )
        self.section_buffer.setToolTip(
            "Buffer laterale simmetrico della sezione in metri [m]. "
            "Viene aggiunto a sinistra e destra oltre ai punti di intercettazione della scarpata."
        )
        self.section_sample_step.setToolTip(
            "Passo di campionamento interno alla sezione in metri [m]. "
            "Valori piccoli aumentano la risoluzione del profilo trasversale."
        )
        self.profile_h_scale.setToolTip(
            "Scala orizzontale del profilo nel formato 1:n. "
            "n più alto riduce la dimensione grafica in orizzontale."
        )
        self.profile_v_scale.setToolTip(
            "Scala verticale del profilo nel formato 1:n. "
            "n più basso enfatizza le variazioni altimetriche."
        )
        self.section_scale.setToolTip(
            "Scala grafica delle sezioni nel formato 1:n. "
            "Determina la dimensione di esportazione delle sezioni."
        )
        self.section_vertical_exaggeration.setToolTip(
            "Fattore di esagerazione verticale delle sezioni. "
            "Valori maggiori accentuano i dislivelli visualizzati."
        )
        self.section_quote_step.setToolTip(
            "Passo delle quotazioni in sezione in metri [m]. "
            "Valori minori mostrano quote più frequenti."
        )
        self.max_cartigli_per_sheet.setToolTip(
            "Numero massimo di cartigli sezione da impaginare in ogni foglio DXF."
        )
        self.cmb_terrain_source.setToolTip(
            "Sorgente dati terreno per il campionamento. "
            "Raster DTM usa il raster selezionato, TIN usa un modello locale."
        )
        self.tin_contour_interval.setToolTip(
            "Intervallo altimetrico tra curve di livello locali [m]. "
            "Valori minori creano curve più dense."
        )
        self.tin_processing_buffer.setToolTip(
            "Buffer locale attorno all'asse per costruire il TIN [m]. "
            "Valori maggiori includono più territorio."
        )
        self.tin_simplify_tolerance.setToolTip(
            "Tolleranza di semplificazione delle curve [m]. "
            "Valori più alti riducono dettaglio e peso del TIN."
        )
        self.chk_tin_add_contours.setToolTip(
            "Se attivo, aggiunge in QGIS le curve locali usate per il TIN."
        )
        self.chk_tin_add_triangles.setToolTip(
            "Se attivo, aggiunge in QGIS i triangoli del TIN locale."
        )
        self.chk_tin_cache.setToolTip(
            "Riusa il TIN già calcolato nella sessione corrente. "
            "Riduce i tempi se i parametri non cambiano."
        )

        self.cmb_profile_mode.setToolTip(
            "Modalità di costruzione del profilo verticale. "
            "Automatico usa il comportamento corrente, PVI usa punti geometrici."
        )
        self.cmb_pvi_layer.setToolTip(
            "Layer punti contenente i PVI da usare nel profilo verticale."
        )
        self.cmb_pvi_elev_field.setToolTip(
            "Campo attributo con la quota dei PVI in metri [m]. "
            "Valori errati alterano il tracciato altimetrico."
        )
        self.cmb_pvi_curve_field.setToolTip(
            "Campo attributo con lunghezza curva verticale [m]. "
            "Se vuoto, viene usata la lunghezza curva di default."
        )
        self.default_curve_length.setToolTip(
            "Lunghezza curva verticale predefinita in metri [m]. "
            "Si applica ai PVI senza valore specifico."
        )

        self.output_folder.setToolTip(
            "Cartella di destinazione dei file esportati. "
            "Tutti gli output verranno scritti in questo percorso."
        )
        self.project_name.setToolTip(
            "Nome base del progetto usato nei file di output."
        )
        self.chk_dxf_sections.setToolTip(
            "Abilita l'esportazione DXF delle sezioni trasversali."
        )
        self.chk_dxf_profile.setToolTip(
            "Abilita l'esportazione DXF del profilo verticale."
        )
        self.chk_csv.setToolTip(
            "Abilita l'esportazione CSV dei volumi e dei risultati tabellari."
        )

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona cartella output")
        if folder:
            self.output_folder.setText(folder)

    def append_log(self, text: str):
        self.log.appendPlainText(text)

    def _toggle_tin_group(self):
        self.tin_group.setVisible(self.cmb_terrain_source.currentIndex() == 1)

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
        self.btn_add_pvi.setEnabled(enabled)
        self.btn_remove_pvi.setEnabled(enabled)
        self.tbl_pvi.setEnabled(enabled)
        self.preview.setEnabled(enabled)
