from PyQt5.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                             QSlider, QLabel, QGroupBox, QDoubleSpinBox, 
                             QPushButton, QScrollArea, QFrame)
from PyQt5.QtCore import Qt

class AirfoilGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FSAE Multi-Element Design Productivity Tool v3.6")
        self.setGeometry(50, 50, 1600, 900)
        self.wing_controls = []
        self._init_ui()

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # --- Left: Plotting Area ---
        self.canvas_container = QWidget()
        self.canvas_layout = QVBoxLayout(self.canvas_container)
        main_layout.addWidget(self.canvas_container, stretch=2)

        # --- Right: Control Panel ---
        right_panel = QVBoxLayout()
        
        top_btn_layout = QHBoxLayout()
        self.btn_import_all = QPushButton("Import Scheme (.dat)")
        self.btn_export_all = QPushButton("Export Scheme (.dat)")
        self.btn_export_vba = QPushButton("Export Combo VBA (CAD)")
        
        # Styling
        self.btn_export_vba.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; height: 35px;")
        self.btn_export_all.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; height: 35px;")
        
        top_btn_layout.addWidget(self.btn_import_all)
        top_btn_layout.addWidget(self.btn_export_all)
        top_btn_layout.addWidget(self.btn_export_vba)
        right_panel.addLayout(top_btn_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        wings_h_layout = QHBoxLayout(scroll_content)
        
        for i in range(3):
            wing_col = self._create_wing_column(i)
            self.wing_controls.append(wing_col)
            wings_h_layout.addWidget(wing_col['group'])
        
        scroll.setWidget(scroll_content)
        right_panel.addWidget(scroll)
        main_layout.addLayout(right_panel, stretch=3)

    def _create_wing_column(self, idx):
        names = ["Wing1 (Main)", "Wing2 (Flap)", "Wing3 (Slat)"]
        colors = ["#1f77b4", "#d62728", "#2ca02c"]
        group = QGroupBox(names[idx])
        group.setStyleSheet(f"QGroupBox {{ border: 2px solid {colors[idx]}; border-radius: 8px; margin-top: 1.5ex; font-weight: bold; }}")
        
        layout = QVBoxLayout(group)
        ctrls = {'group': group, 'geo_slds': {}}

        btn_load = QPushButton("Load Original Airfoil")
        layout.addWidget(btn_load)
        ctrls['btn_load'] = btn_load

        # Geometry Controls Configuration
        geo_cfg = [
            ("pos_x", "X Position (m):", -2.0, 4.0), 
            ("pos_y", "Y Position (m):", -1.0, 1.0), 
            ("chord", "Chord Length (m):", 0.01, 2.5), 
            ("angle", "Angle of Attack (deg):", -90.0, 90.0)
        ]
        
        for key, lbl, v_min, v_max in geo_cfg:
            layout.addWidget(QLabel(lbl))
            row = QHBoxLayout()
            spin = QDoubleSpinBox()
            spin.setRange(v_min, v_max)
            spin.setDecimals(4)
            spin.setSingleStep(0.01)
            
            sld = QSlider(Qt.Horizontal)
            sld.setRange(0, 1000) # Resolution
            
            row.addWidget(sld, stretch=2)
            row.addWidget(spin, stretch=1)
            layout.addLayout(row)
            
            ctrls[key] = spin
            ctrls['geo_slds'][key] = sld

        # CST Controls
        for skey, sname in [('up_w', "Upper Surface (CST)"), ('lo_w', "Lower Surface (CST)")]:
            layout.addWidget(QLabel(f"<b>{sname}</b>"))
            ctrls[skey] = []
            ctrls[f"{skey}_labels"] = []
            for j in range(4):
                row = QHBoxLayout()
                sld = QSlider(Qt.Horizontal)
                sld.setRange(0, 200) # 0% to 200%
                sld.setValue(100)
                lbl = QLabel("0.0000 (100%)")
                lbl.setFixedWidth(120)
                row.addWidget(sld)
                row.addWidget(lbl)
                layout.addLayout(row)
                ctrls[skey].append(sld)
                ctrls[f"{skey}_labels"].append(lbl)

        layout.addStretch()
        return ctrls