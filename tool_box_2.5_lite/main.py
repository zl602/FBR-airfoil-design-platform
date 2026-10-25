import sys
import os
import numpy as np
import datetime
import csv
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QInputDialog, QLabel, QWidget, QVBoxLayout, QSlider
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from math import comb

# --- Matplotlib 引用移至 main.py ---
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# 导入 GUI 基类和核心工具
from gui import AirfoilGUI
from airfoil_toolbox_v2 import Airfoil
from xfoil_ops import run_xfoil_sweep

class XfoilWorker(QThread):
    finished = pyqtSignal(object, int)  # (按攻角升序的结果列表, 请求的攻角数)
    def __init__(self, name, coords, alphas, reynold, xfoil_path):
        super().__init__()
        self.params = (name, coords, alphas, reynold, xfoil_path)

    def run(self):
        name, coords, alphas, re, path = self.params
        results = run_xfoil_sweep(name, coords, 160, alphas, re, path)
        self.finished.emit(results, len(alphas))

class AirfoilApp(AirfoilGUI):
    def __init__(self):
        super().__init__()
        self.af = Airfoil()
        self.x_sample = np.linspace(0, 1, 150)
        self.xfoil_path = "xfoil.exe"
        self.current_log_file = None 
        
        # --- 路径初始化 ---
        # main_v2.py 约第 49 行起的修改
        
        # --- 修复打包后的路径识别问题 ---
        if getattr(sys, 'frozen', False):
            # 如果是打包后的 exe，使用 exe 所在的真实目录
            self.base_dir = os.path.dirname(sys.executable)
        else:
            # 如果是直接运行脚本，使用脚本所在的目录
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.log_dir = os.path.join(self.base_dir, "design_logs")
        self.airfoil_dir = os.path.join(self.base_dir, "airfoils")
        
        for d in [self.log_dir, self.airfoil_dir]:
            if not os.path.exists(d):
                os.makedirs(d)
        # ------------------------------

        self.setup_plotting()
        self.connect_signals()

    def setup_plotting(self):
        self.fig = Figure(figsize=(10, 8))
        self.canvas = FigureCanvas(self.fig)
        self.canvas_layout.addWidget(self.canvas)
        self.ax_foil = self.fig.add_subplot(211) 
        self.ax_cp = self.fig.add_subplot(212)   
        self.ax_foil.set_title("Airfoil Geometry")
        self.ax_foil.set_aspect('equal')
        self.ax_foil.grid(True, linestyle=':', alpha=0.6)
        self.ax_cp.set_title("Pressure Distribution (Cp)")
        self.ax_cp.invert_yaxis() 
        self.ax_cp.grid(True, linestyle=':', alpha=0.6)
        self.line_up, = self.ax_foil.plot([], [], 'b-', lw=2, label='Upper')
        self.line_lo, = self.ax_foil.plot([], [], 'r-', lw=2, label='Lower')
        self.line_orig, = self.ax_foil.plot([], [], 'k.', markersize=3, alpha=0.3, label='Baseline') 
        self.line_cp, = self.ax_cp.plot([], [], 'g-', lw=1.5, label='Cp')
        # 可信度警告：滑到存疑攻角时显示在 Cp 图右上角
        self.cp_warn = self.ax_cp.text(
            0.99, 0.97, "", transform=self.ax_cp.transAxes, ha='right', va='top',
            fontsize=9, color='#b71c1c', visible=False, zorder=5,
            bbox=dict(boxstyle='round,pad=0.4', fc='#ffebee', ec='#c62828'))
        self.ax_foil.legend(loc='upper right')

    def connect_signals(self):
        self.btn_naca.clicked.connect(self.on_generate_naca)
        self.btn_load.clicked.connect(self.on_load_file)
        self.btn_run.clicked.connect(self.on_run_xfoil)
        self.btn_csv.clicked.connect(self.on_export_csv)
        self.btn_vba.clicked.connect(self.on_export_vba)
        self.btn_flip.clicked.connect(self.on_export_flipped)
        self.sld_alpha.valueChanged.connect(self.show_sweep_point)

    def init_design_log(self, baseline_path):
        """在 design_logs 文件夹内创建日志"""
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        log_name = f"design_log_{now}.csv"
        self.current_log_file = os.path.join(self.log_dir, log_name)
        
        with open(self.current_log_file, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([f"Generation Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
            writer.writerow([f"Baseline Airfoil Path: {os.path.abspath(baseline_path)}"])
            writer.writerow(["Timestamp", "Upper CST Weights", "Lower CST Weights", "Re", "Alpha", "Cl", "Cd", "L/D", "Separation Point", "Credibility"])

    def on_generate_naca(self):
        code, ok = QInputDialog.getText(self, "NACA", "Enter 4-digit code (e.g. 2412):")
        if ok and code:
            self.af.generate_naca_with_header(code, self.airfoil_dir)
            # 更新这里寻找的文件名后缀
            file_path = os.path.join(self.airfoil_dir, f"naca{code}_xy.dat")
            self.init_design_log(file_path)
            self.process_airfoil_data(file_path)

    def on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Airfoil", "", "DAT (*.dat)")
        if path: 
            self.init_design_log(path)
            self.process_airfoil_data(path)

    def process_airfoil_data(self, path):
        self.af.load_csv_coords(path)
        self.orig_pts = np.array(self.af.upper + self.af.lower)
        order = self.spin_order.value()
        up_w, lo_w = self.af.get_cst_parameters(order=order, plot_comparison=False, export_csv=False)
        self.orig_up, self.orig_lo = list(up_w.values()), list(lo_w.values())
        self.clear_sweep()  # 旧翼型的扫描结果不再适用
        self.build_sliders()
        self.refresh_plot()

    def build_sliders(self):
        self.clear_sliders()
        self.sld_layout.addWidget(QLabel("<b>Upper Weights</b>"))
        for i, v in enumerate(self.orig_up):
            self.sliders.append(self._create_slider_item(f"Up W{i}", v))
        self.sld_layout.addWidget(QLabel("<b>Lower Weights</b>"))
        for i, v in enumerate(self.orig_lo):
            self.sliders.append(self._create_slider_item(f"Lo W{i}", v))
        self.sld_layout.addStretch()

    def _create_slider_item(self, name, val):
        container = QWidget(); lay = QVBoxLayout(container)
        lbl = QLabel(f"{name}: 100% | {val:.4f}"); sld = QSlider(Qt.Horizontal)
        sld.setRange(0, 200); sld.setValue(100)
        sld.valueChanged.connect(self.refresh_plot)
        lay.addWidget(lbl); lay.addWidget(sld)
        self.sld_layout.addWidget(container)
        return (sld, lbl, val)

    def refresh_plot(self):
        if not hasattr(self, 'orig_up'): return
        u_len = len(self.orig_up)
        self.curr_up = [s[2]*(s[0].value()/100.0) for s in self.sliders[:u_len]]
        self.curr_lo = [s[2]*(s[0].value()/100.0) for s in self.sliders[u_len:]]
        
        for i, s in enumerate(self.sliders):
            prefix = "Up" if i < u_len else "Lo"
            s[1].setText(f"{prefix} W{i%u_len}: {s[0].value()}% | {(s[2]*s[0].value()/100.0):.4f}")

        def cst_calc(x, w):
            n = len(w)-1
            return (x**0.5*(1-x)) * sum(wi*(comb(n,j)*x**j*(1-x)**(n-j)) for j,wi in enumerate(w))
        
        yu = [cst_calc(xi, self.curr_up) for xi in self.x_sample]
        yl = [cst_calc(xi, self.curr_lo) for xi in self.x_sample]
        
        self.line_up.set_data(self.x_sample, yu)
        self.line_lo.set_data(self.x_sample, yl)
        self.line_orig.set_data(self.orig_pts[:,0], self.orig_pts[:,1])
        self.ax_foil.relim(); self.ax_foil.autoscale_view(); self.canvas.draw()

    def sweep_alphas(self):
        """根据 From / To / Step 生成攻角列表（From > To 时自动交换）"""
        a0, a1, da = self.spin_a0.value(), self.spin_a1.value(), self.spin_da.value()
        if a0 > a1: a0, a1 = a1, a0
        n = int(round((a1 - a0) / da)) + 1
        return [round(a0 + i * da, 3) for i in range(n) if a0 + i * da <= a1 + 1e-9]

    def on_run_xfoil(self):
        if not hasattr(self, 'curr_up'): return
        yu, yl = self.line_up.get_ydata(), self.line_lo.get_ydata()
        coords = [(x, y) for x, y in zip(self.x_sample[::-1], yu[::-1])] + [(x, y) for x, y in zip(self.x_sample[1:], yl[1:])]
        alphas = self.sweep_alphas()

        self.btn_run.setEnabled(False); self.btn_run.setText(f"Solving {len(alphas)} angles...")
        self.worker = XfoilWorker("current", coords, alphas, self.spin_re.value(), self.xfoil_path)
        self.worker.finished.connect(self.on_xfoil_finished)
        self.worker.start()

    def on_xfoil_finished(self, results, n_requested):
        self.btn_run.setEnabled(True); self.btn_run.setText("Run XFOIL Alpha Sweep")
        if not results:
            QMessageBox.warning(self, "XFOIL", "Convergence failed at every angle of attack.")
            return

        self.sweep = results
        n_warn = sum(1 for r in results if r['warnings'])
        self.sweep_info = f"{len(results)}/{n_requested} converged" + (f", {n_warn} questionable" if n_warn else "")

        # 整个扫描共用固定的 Cp 坐标范围，拖动滑块时曲线变化一目了然
        all_cp = np.concatenate([r['cp'][:, 1] for r in results])
        pad = 0.05 * (all_cp.max() - all_cp.min() or 1.0)
        self.ax_cp.set_xlim(-0.02, 1.02)
        self.ax_cp.set_ylim(all_cp.max() + pad, all_cp.min() - pad)  # 倒置：负 Cp 在上

        # 滑块初始停在升阻比最大的攻角
        best = max(range(len(results)), key=lambda i: results[i]['ld'] or float('-inf'))
        self.sld_alpha.blockSignals(True)
        self.sld_alpha.setRange(0, len(results) - 1)
        self.sld_alpha.setValue(best)
        self.sld_alpha.blockSignals(False)
        self.alpha_group.setVisible(True)
        self.show_sweep_point(best)

        # 记录到 design_logs 文件夹中的文件（每个收敛攻角一行）
        if self.current_log_file:
            now = datetime.datetime.now().strftime('%H:%M:%S')
            with open(self.current_log_file, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                for r in results:
                    writer.writerow([
                        now,
                        [round(w, 5) for w in self.curr_up],
                        [round(w, 5) for w in self.curr_lo],
                        self.spin_re.value(), r['alpha'],
                        round(r['cl'], 5), round(r['cd'], 5),
                        round(r['ld'], 3) if r['ld'] is not None else "N/A",
                        f"{r['sep_x']:.3f}" if r['sep_x'] else "N/A",
                        "Questionable: " + "; ".join(r['warnings']) if r['warnings'] else "OK",
                    ])

    def show_sweep_point(self, idx):
        """滑块回调：显示第 idx 个收敛攻角的 Cp 分布与气动数据"""
        if not getattr(self, 'sweep', None): return
        r = self.sweep[idx]
        self.line_cp.set_data(r['cp'][:, 0], r['cp'][:, 1])
        self.ax_cp.set_title(f"Pressure Distribution (Cp)  @  Alpha = {r['alpha']:g}°")
        self.lbl_alpha.setText(f"Alpha: {r['alpha']:g}°   ({self.sweep_info})")
        self.lbl_cl.setText(f"CL: {r['cl']:.4f}"); self.lbl_cd.setText(f"CD: {r['cd']:.5f}")
        self.lbl_ld.setText(f"L/D: {r['ld']:.2f}" if r['ld'] is not None else "L/D: N/A")
        self.lbl_sep.setText(f"Sep. Point: {r['sep_x']:.3f}" if r['sep_x'] else "Sep. Point: N/A")

        # 存疑攻角：Cp 曲线变红，并在图上和滑块下方给出原因
        warnings = r['warnings']
        self.line_cp.set_color('#c62828' if warnings else 'g')
        self.cp_warn.set_visible(bool(warnings))
        self.lbl_warn.setVisible(bool(warnings))
        if warnings:
            self.cp_warn.set_text("WARNING: XFOIL result questionable\n" + "\n".join("- " + w for w in warnings))
            self.lbl_warn.setText("WARNING: XFOIL result at this angle is questionable. " + " | ".join(warnings))
        self.canvas.draw_idle()

    def clear_sweep(self):
        self.sweep = None
        self.alpha_group.setVisible(False)
        self.line_cp.set_data([], [])
        self.cp_warn.set_visible(False)
        self.lbl_warn.setVisible(False)
        self.ax_cp.set_title("Pressure Distribution (Cp)")
        for lbl, txt in [(self.lbl_cl, "CL: -"), (self.lbl_cd, "CD: -"), (self.lbl_ld, "L/D: -"), (self.lbl_sep, "Separation: -")]:
            lbl.setText(txt)

    def on_export_csv(self):
        # 默认导出路径设为 airfoils 文件夹
        path, _ = QFileDialog.getSaveFileName(self, "Save", os.path.join(self.airfoil_dir, "modified.dat"), "DAT (*.dat)")
        if path: 
            self.af.generate_cst(self.curr_up, self.curr_lo, os.path.dirname(path), os.path.basename(path))

    def on_export_vba(self):
        chord, ok = QInputDialog.getDouble(self, "VBA", "Chord Length:", 1.0)
        AoA, ok = QInputDialog.getDouble(self, "VBA", "AoA:", 0.0)
        z, ok = QInputDialog.getDouble(self, "VBA", "z offset:", 0.0)
        x,  ok = QInputDialog.getDouble(self, "VBA", "LE x coord:", 0.0)
        y,  ok = QInputDialog.getDouble(self, "VBA", "LE y coord:", 0.0)

        if ok:
            self.af.upper = np.column_stack((self.x_sample, self.line_up.get_ydata())).tolist()
            self.af.lower = np.column_stack((self.x_sample, self.line_lo.get_ydata())).tolist()
            self.af.sw_sketch_vba(z=z, chord=chord, angle_deg= AoA, pos_x=x, pos_y=y)

    # main_v2.py 文件末尾添加该方法

    def on_export_flipped(self):
        """调用 toolbox 翻转翼型并导出"""
        if not hasattr(self, 'curr_up'):
            QMessageBox.warning(self, "Error", "Please load or generate an airfoil first!")
            return

        # 弹出保存对话框
        default_name = os.path.join(self.airfoil_dir, "flipped_airfoil.dat") # 改为 .dat
        path, _ = QFileDialog.getSaveFileName(self, "Export Flipped Airfoil", default_name, "DAT (*.dat)")
        if path:
            # 1. 先将当前滑块调整后的 CST 坐标同步回 self.af 对象
            # 注意：flip_y 依赖 self.af.upper 和 self.af.lower
            self.af.upper = np.column_stack((self.x_sample, self.line_up.get_ydata())).tolist()
            self.af.lower = np.column_stack((self.x_sample, self.line_lo.get_ydata())).tolist()
            
            # 2. 调用 airfoil_toolbox_v2 中的 flip_y 方法
            folder = os.path.dirname(path)
            filename = os.path.basename(path)
            save_path = self.af.flip_y(folder=folder, filename=filename)
            
            if save_path:
                QMessageBox.information(self, "Success", f"Flipped airfoil saved to:\n{save_path}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AirfoilApp()
    window.show()
    sys.exit(app.exec_())

def run_main():
    app = QApplication(sys.argv)
    window = AirfoilApp()
    window.show()
    sys.exit(app.exec_())