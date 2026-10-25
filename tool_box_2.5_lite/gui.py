from PyQt5.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                             QSlider, QLabel, QPushButton, QSpinBox, 
                             QDoubleSpinBox, QScrollArea, QGroupBox)
from PyQt5.QtCore import Qt

class AirfoilGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.sliders = []
        self.init_ui_layout()

    def init_ui_layout(self):
        self.setWindowTitle("Airfoil Design Master v2.3")
        self.setGeometry(100, 100, 1500, 950)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # --- Left Side: Graphics Container ---
        left_layout = QVBoxLayout()
        
        # Placeholder for Matplotlib Canvas
        self.canvas_container = QWidget()
        self.canvas_layout = QVBoxLayout(self.canvas_container)
        left_layout.addWidget(self.canvas_container)
        
        # Aerodynamic Data Display
        res_group = QGroupBox("Aero Performance")
        res_l = QHBoxLayout(res_group)
        self.lbl_cl = QLabel("CL: -"); self.lbl_cd = QLabel("CD: -")
        self.lbl_ld = QLabel("L/D: -"); self.lbl_sep = QLabel("Separation: -")
        for l in [self.lbl_cl, self.lbl_cd, self.lbl_ld, self.lbl_sep]: res_l.addWidget(l)
        left_layout.addWidget(res_group)
        main_layout.addLayout(left_layout, stretch=3)

        # --- Right Side: Control Panel ---
        right_panel = QVBoxLayout()

        # 1. Fitting Settings
        fit_group = QGroupBox("Fitting Settings")
        fit_l = QVBoxLayout(fit_group)
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("CST Order:"))
        self.spin_order = QSpinBox()
        self.spin_order.setRange(2, 12); self.spin_order.setValue(6)
        h_layout.addWidget(self.spin_order)
        fit_l.addLayout(h_layout)

        self.btn_naca = QPushButton("Generate NACA & Fit")
        self.btn_naca.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_load = QPushButton("Load & Fit Airfoil File")
        fit_l.addWidget(self.btn_naca)
        fit_l.addWidget(self.btn_load)
        right_panel.addWidget(fit_group)

        # 2. Operations & Export
        exp_group = QGroupBox("Export Airfoil")
        exp_l = QVBoxLayout(exp_group)
        self.btn_csv = QPushButton("Export .DAT")
        self.btn_flip = QPushButton("Export Inverted .DAT")
        # ---------------
        self.btn_vba = QPushButton("Generate SW VBA")

        exp_l.addWidget(self.btn_csv)
        exp_l.addWidget(self.btn_flip) 
        exp_l.addWidget(self.btn_vba)
        right_panel.addWidget(exp_group)

        # 3. Operating Conditions
        xf_group = QGroupBox("XFOIL Simulation")
        xf_l = QVBoxLayout(xf_group)
        self.spin_re = QDoubleSpinBox(); self.spin_re.setRange(1e4, 1e7); self.spin_re.setValue(1e6)
        self.spin_alpha = QDoubleSpinBox(); self.spin_alpha.setRange(-20, 20); self.spin_alpha.setValue(4.0)
        self.btn_run = QPushButton("Run XFOIL Analysis")
        self.btn_run.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        xf_l.addWidget(QLabel("Reynolds Number (Re):")); xf_l.addWidget(self.spin_re)
        xf_l.addWidget(QLabel("Alpha (deg):")); xf_l.addWidget(self.spin_alpha)
        xf_l.addWidget(self.btn_run)
        right_panel.addWidget(xf_group)

        # 4. Slider Scroll Area
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.sld_widget = QWidget(); self.sld_layout = QVBoxLayout(self.sld_widget)
        self.scroll.setWidget(self.sld_widget)
        right_panel.addWidget(self.scroll)

        main_layout.addLayout(right_panel, stretch=1)

    def clear_sliders(self):
        for i in reversed(range(self.sld_layout.count())):
            w = self.sld_layout.itemAt(i).widget()
            if w: w.setParent(None)
        self.sliders = []