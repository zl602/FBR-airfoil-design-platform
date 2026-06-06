import sys
import numpy as np
import datetime
import pyperclip
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QInputDialog
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from scipy.special import comb

from multi_gui import AirfoilGUI
from airfoil_toolbox_v2 import Airfoil

class MultiElementApp(AirfoilGUI):
    def __init__(self):
        super().__init__()
        self.af_tools = [Airfoil() for _ in range(3)]
        n_points = 100
        beta = np.linspace(0, np.pi, n_points)
        self.x_sample = 0.5 * (1 - np.cos(beta)) # 前后缘加密
        # 初始权重设为非零值，防止乘法失效
        self.orig_weights = [{'up_w': [0.1, 0.1, 0.1, 0.1], 'lo_w': [-0.1, -0.1, -0.1, -0.1]} for _ in range(3)]
        self.is_loaded = [False, False, False]
        self.wing_colors = ['#1f77b4', '#d62728', '#2ca02c']
        self.wing_lines = [None, None, None]
        self.wing_fills = [None, None, None]
        
        self._setup_plotting()
        self._connect_signals()

    def _setup_plotting(self):
        self.fig = Figure(); self.canvas = FigureCanvas(self.fig)
        self.canvas_layout.addWidget(self.canvas)
        self.ax = self.fig.add_subplot(111); self.ax.set_aspect('equal'); self.ax.grid(True, alpha=0.3)

    def _connect_signals(self):
        self.btn_export_all.clicked.connect(self.on_export_scheme)
        self.btn_import_all.clicked.connect(self.on_import_scheme)
        self.btn_export_vba.clicked.connect(self.export_vba)
        for i in range(3):
            c = self.wing_controls[i]
            c['btn_load'].clicked.connect(lambda _, idx=i: self.load_single_dat(idx))
            for k in ['pos_x', 'pos_y', 'chord', 'angle']:
                c[k].valueChanged.connect(self.refresh_plot)
                c['geo_slds'][k].valueChanged.connect(lambda v, sp=c[k]: self.sync_sld(v, sp))
            for side in ['up_w', 'lo_w']:
                for sid, sld in enumerate(c[side]):
                    sld.valueChanged.connect(self.refresh_plot)
                    sld.valueChanged.connect(lambda _, w=i, k=side, s=sid: self.update_labels(w, k, s))

    def sync_sld(self, pos, spin):
        spin.blockSignals(True)
        val = spin.minimum() + (pos/1000.0)*(spin.maximum()-spin.minimum())
        spin.setValue(val); spin.blockSignals(False); self.refresh_plot()

    def update_labels(self, wi, sk, si):
        if not self.is_loaded[wi]: return
        ctrls = self.wing_controls[wi]
        pct = ctrls[sk][si].value()
        val = self.orig_weights[wi][sk][si] * (pct/100.0)
        ctrls[f"{sk}_labels"][si].setText(f"{val:.4f} ({pct}%)")

    def load_single_dat(self, idx):
        path, _ = QFileDialog.getOpenFileName(self, "加载翼型")
        if path:
            self.af_tools[idx].load_csv_coords(path)
            u, l = self.af_tools[idx].get_cst_parameters(order=3)
            self.orig_weights[idx]['up_w'] = list(u.values())
            self.orig_weights[idx]['lo_w'] = list(l.values())
            self.is_loaded[idx] = True
            for s in ['up_w', 'lo_w']:
                for sid, sld in enumerate(self.wing_controls[idx][s]):
                    sld.setValue(100); self.update_labels(idx, s, sid)
            self.refresh_plot()

    def get_transformed(self, i):
        if not self.is_loaded[i]: return None
        c = self.wing_controls[i]
        uw = [self.orig_weights[i]['up_w'][j] * (c['up_w'][j].value()/100.0) for j in range(4)]
        lw = [self.orig_weights[i]['lo_w'][j] * (c['lo_w'][j].value()/100.0) for j in range(4)]
        n, x = 3, self.x_sample
        def cst(w): return (x**0.5*(1-x)**1.0)*sum(wi*(comb(n,k)*x**k*(1-x)**(n-k)) for k,wi in enumerate(w))
        self.af_tools[i].upper = np.column_stack((x, cst(uw))).tolist()
        self.af_tools[i].lower = np.column_stack((x, cst(lw))).tolist()
        return self.af_tools[i].transform_airfoil(c['chord'].value(), c['angle'].value(), c['pos_x'].value(), c['pos_y'].value())

    def refresh_plot(self):
        for i in range(3):
            res = self.get_transformed(i)
            if not res: continue
            pts = np.array(res[0] + res[1][::-1])
            if self.wing_lines[i] is None:
                self.wing_fills[i] = self.ax.fill(pts[:,0], pts[:,1], color=self.wing_colors[i], alpha=0.2)[0]
                self.wing_lines[i], = self.ax.plot(pts[:,0], pts[:,1], color=self.wing_colors[i], lw=2)
            else:
                self.wing_lines[i].set_data(pts[:,0], pts[:,1])
                self.wing_fills[i].set_xy(pts)
        self.ax.relim(); self.ax.autoscale_view(); self.canvas.draw()

    def on_export_scheme(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出方案", "FSAE_Scheme.dat", "DAT (*.dat)")
        if not path: return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# FSAE DESIGN | {datetime.datetime.now()}\n")
            for i in range(3):
                if not self.is_loaded[i]: continue
                c = self.wing_controls[i]
                # 计算当前实际权重导出
                uw = [self.orig_weights[i]['up_w'][j] * (c['up_w'][j].value()/100.0) for j in range(4)]
                lw = [self.orig_weights[i]['lo_w'][j] * (c['lo_w'][j].value()/100.0) for j in range(4)]
                f.write(f"\n# SEGMENT: Wing{i+1}\n")
                f.write(f"# PARA | CHORD: {c['chord'].value():.6f} | LE_X: {c['pos_x'].value():.6f} | LE_Y: {c['pos_y'].value():.6f} | ANGLE: {c['angle'].value():.4f}\n")
                f.write(f"# CST_UP | {' '.join(map(str, uw))}\n")
                f.write(f"# CST_LO | {' '.join(map(str, lw))}\n")
                res = self.get_transformed(i)
                for p in (res[0]+res[1][::-1]): f.write(f"{p[0]:.8f} {p[1]:.8f}\n")
        QMessageBox.information(self, "完成", "方案已导出")

    def on_import_scheme(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入方案", "", "DAT (*.dat)")
        if not path: return
        try:
            curr_idx = -1
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    if "# SEGMENT: Wing" in line:
                        curr_idx = int(line.split("Wing")[-1]) - 1
                        self.is_loaded[curr_idx] = True # 关键：强制激活加载状态
                    elif "# PARA" in line and curr_idx != -1:
                        parts = {it.split(':')[0].strip(): float(it.split(':')[1]) for it in line.split('|')[1:]}
                        self.wing_controls[curr_idx]['chord'].setValue(parts['CHORD'])
                        self.wing_controls[curr_idx]['pos_x'].setValue(parts['LE_X'])
                        self.wing_controls[curr_idx]['pos_y'].setValue(parts['LE_Y'])
                        self.wing_controls[curr_idx]['angle'].setValue(parts['ANGLE'])
                    elif "# CST_UP" in line and curr_idx != -1:
                        self.orig_weights[curr_idx]['up_w'] = [float(x) for x in line.split('|')[1].split()]
                        for sid, sld in enumerate(self.wing_controls[curr_idx]['up_w']):
                            sld.setValue(100); self.update_labels(curr_idx, 'up_w', sid)
                    elif "# CST_LO" in line and curr_idx != -1:
                        self.orig_weights[curr_idx]['lo_w'] = [float(x) for x in line.split('|')[1].split()]
                        for sid, sld in enumerate(self.wing_controls[curr_idx]['lo_w']):
                            sld.setValue(100); self.update_labels(curr_idx, 'lo_w', sid)
            self.refresh_plot()
            QMessageBox.information(self, "成功", "方案已全量导入并重绘")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"文件内容不兼容: {e}")

    def export_vba(self):
        z, ok = QInputDialog.getDouble(self, "CAD导出", "Z轴坐标(m):", 0, -5, 5, 4)
        if not ok: return
        vba = "Dim swApp As Object\nDim Part As Object\nSub main()\nSet swApp=Application.SldWorks\nSet Part=swApp.ActiveDoc\n"
        for i in range(3):
            res = self.get_transformed(i)
            if not res: continue
            for name, pts in [("Up", res[0]), ("Lo", res[1])]:
                vba += f"\n'W{i+1}{name}\nReDim p(0 To {3*len(pts)-1}) As Double\n"
                for j, p in enumerate(pts):
                    vba += f"p({j*3})={p[0]}: p({j*3+1})={p[1]}: p({j*3+2})={z}\n"
                vba += "Part.SketchManager.CreateSpline((p))\n"
        vba += "End Sub"
        pyperclip.copy(vba); QMessageBox.information(self, "CAD", "VBA已复制")

if __name__ == "__main__":
    app = QApplication(sys.argv); win = MultiElementApp(); win.show(); sys.exit(app.exec_())