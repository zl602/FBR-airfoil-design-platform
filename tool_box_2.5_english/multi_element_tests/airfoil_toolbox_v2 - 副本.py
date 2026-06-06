
import numpy as np
from scipy.special import comb
import pandas as pd
import os
import math
import pyperclip

class Airfoil():
    def __init__(self):
        self.upper = None
        self.lower = None

    def generate_naca_with_header(self, naca4, folder, n_points=80):
        """解析 NACA 4 位数代码"""
        file = f"naca{naca4}_xy.dat" # 后缀改为 .dat
        filename = os.path.join(folder, file)
        
        code = str(naca4).zfill(4)
        m = int(code[0]) / 100.0
        p = int(code[1]) / 10.0
        t = int(code[2:]) / 100.0

        beta = np.linspace(0, np.pi, n_points)
        x = 0.5 * (1 - np.cos(beta))

        yt = 5 * t * (0.2969*np.sqrt(x) - 0.1260*x - 0.3516*x**2 + 0.2843*x**3 - 0.1015*x**4)

        yc = np.zeros_like(x)
        dyc_dx = np.zeros_like(x)
        for i, xi in enumerate(x):
            if xi < p:
                yc[i] = (m / p**2) * (2*p*xi - xi**2) if p != 0 else 0
                dyc_dx[i] = (2*m / p**2) * (p - xi) if p != 0 else 0
            else:
                yc[i] = (m / (1-p)**2) * ((1-2*p) + 2*p*xi - xi**2) if p != 1 else 0
                dyc_dx[i] = (2*m / (1-p)**2) * (p - xi) if p != 1 else 0

        theta = np.arctan(dyc_dx)
        xu = x - yt * np.sin(theta)
        yu = yc + yt * np.cos(theta)
        xl = x + yt * np.sin(theta)
        yl = yc - yt * np.cos(theta)

        all_x = np.concatenate([xu, xl[::-1]])
        all_y = np.concatenate([yu, yl[::-1]])

        df = pd.DataFrame({'x': all_x, 'y': all_y})
        # 保存为以空格分隔的 .dat 文件，不包含索引
        df.to_csv(filename, index=False, header=True, sep=' ')
        print(f"NACA {naca4} generated: {filename}")

    def load_csv_coords(self, file_path):
        
        # 将 sep 改为匹配任意空白字符，以兼容常见的 .dat 格式
        df = pd.read_csv(file_path, sep=r'\s+', engine='python', skip_blank_lines=True)
        # 如果 .dat 没有表头，可能需要处理或者强制指定列名
        if not isinstance(df.iloc[0, 0], (int, float, np.number)):
            df = pd.read_csv(file_path, sep=r'\s+', engine='python', skiprows=1, names=['x', 'y'])
    
        # 确保数据为浮点数
        pts = df[['x', 'y']].values.astype(float)
        
        # 2. 寻找第一个 x 接近 1.0 的点
        # 注意：由于浮点数精度，用 np.isclose 或设定阈值更稳妥
        te_start_idx = np.where(np.isclose(pts[:, 0], 1.0, atol=1e-3))[0][0]

        # 3. 按照你的逻辑，从序列开始到后缘点，和从后缘点到结束进行切分
        # 通常 side1 是 Upper (如果序列是 TE-UP-LE)，side2 是 Lower (LE-LO-TE)
        side1 = pts[:te_start_idx + 1]
        side2 = pts[te_start_idx:]

        # 4. 自动识别并重排：我们要的结果是 self.upper/lower 都是从 LE 到 TE 且 x 递增
        if np.mean(side1[:, 1]) > np.mean(side2[:, 1]):
            up_raw, lo_raw = side1, side2
        else:
            up_raw, lo_raw = side2, side1

        # 确保内部存储顺序：LE -> TE
        self.upper = up_raw[np.argsort(up_raw[:, 0])].tolist()
        self.lower = lo_raw[np.argsort(lo_raw[:, 0])].tolist()

        # 5. 归一化处理 (强制 LE 归零，TE 闭合)
        self.upper[0] = [0.0, 0.0]
        self.lower[0] = [0.0, 0.0]
        self.upper[-1] = [1.0, 0.0]
        self.lower[-1] = [1.0, 0.0]

        print(f">>> 已按尾缘起始逻辑加载: {os.path.basename(file_path)}")
        return self.upper, self.lower
    
    def flip_y(self, folder=".", filename="flipped_airfoil.csv"):
        """
        将当前加载的 self.upper 和 self.lower 沿 X 轴翻转，
        并输出一个新的 CSV 文件。
        """
        if self.upper is None or self.lower is None:
            print("错误：没有已加载的数据可供翻转。")
            return None

        # 1. 执行翻转逻辑 (Y 坐标取反)
        # 注意：翻转后，原上表面(y>0)变成下表面，原下表面(y<0)变成上表面
        new_upper = [[p[0], -p[1]] for p in self.lower]
        new_lower = [[p[0], -p[1]] for p in self.upper]
        
        # 2. 更新内存数据
        self.upper = new_upper
        self.lower = new_lower
        
        # 3. 构造导出数据 (顺时针顺序)
        # new_upper: 前缘 -> 尾缘
        # new_lower[::-1]: 尾缘 -> 前缘
        all_points = self.upper + self.lower[::-1]
        
        # 4. 去重并保存
        df = pd.DataFrame(all_points, columns=['x', 'y'])
        df = df.drop_duplicates().reset_index(drop=True)
        
        if not os.path.exists(folder):
            os.makedirs(folder)
    
        save_path = os.path.join(folder, filename)
        df.to_csv(save_path, index=False, sep=' ') # 改为空格分隔
        return save_path

    def transform_airfoil(self, chord, angle_deg, pos_x, pos_y, folder=""):
        """缩放、旋转和平移坐标"""
        rad = math.radians(angle_deg)
        def transform_point(p):
            rx, ry = p[0] * chord, p[1] * chord
            tx = rx * math.cos(rad) - ry * math.sin(rad)
            ty = rx * math.sin(rad) + ry * math.cos(rad)
            return [tx + pos_x, ty + pos_y]

        upper1 = [transform_point(p) for p in self.upper]
        lower1 = [transform_point(p) for p in self.lower]
        lower1[-1] = upper1[-1]

        if folder != "":
            if not os.path.exists(folder): os.makedirs(folder)
            save_path = os.path.join(folder, f"trans_c{chord}_a{angle_deg}.csv")
            all_points = upper1 + lower1[::-1]
            df = pd.DataFrame(all_points, columns=['x', 'y']).drop_duplicates().reset_index(drop=True)
            df.to_csv(save_path, index=False)
            print(f"变换后坐标已保存: {save_path}")
        return upper1, lower1

    def get_cst_parameters(self, order=6, plot_comparison=True, export_csv=True, folder=".", filename="cst_fit_result.csv"):
        """CST 拟合逻辑"""
        import matplotlib.pyplot as plt
        if self.upper is None: return None, None
        
        results_weights = []
        fit_y_data = [] 
        mse_values = []
        for coords in [self.upper, self.lower]:
            coords = np.array(coords)
            x, y = coords[:, 0], coords[:, 1]
            C = x**0.5 * (1 - x)**1.0
            X = np.column_stack([C * (comb(order, i) * (x**i) * (1 - x)**(order - i)) for i in range(order + 1)])
            weights, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            results_weights.append(weights)
            y_fit = X @ weights
            fit_y_data.append(y_fit)
            mse_values.append(np.mean((y - y_fit)**2))
        upper_dict = {f'w{i}': val.item() for i, val in enumerate(results_weights[0])}
        lower_dict = {f'w{i}': val.item() for i, val in enumerate(results_weights[1])}
        print(f"upper CST parameters: {np.round(results_weights[0], 4).tolist()}\n lower CST parameters: {np.round(results_weights[1], 4).tolist()}")

        if export_csv:
            self.generate_cst(results_weights[0].tolist(), results_weights[1].tolist(), folder, filename=filename)

        if plot_comparison:
            plt.figure(figsize=(10, 4))
            up_orig = np.array(self.upper)
            lo_orig = np.array(self.lower)
            plt.scatter(up_orig[:, 0], up_orig[:, 1], color='gray', s=8, alpha=0.3)
            plt.plot(up_orig[:, 0], fit_y_data[0], 'r-', label=f'Upper MSE: {mse_values[0]:.2e}')
            plt.plot(lo_orig[:, 0], fit_y_data[1], 'b-', label=f'Lower MSE: {mse_values[1]:.2e}')
            plt.axis('equal'); plt.legend(); plt.grid(True); plt.show()

        #upper_dict = {f'w{i}': val.item() for i, val in enumerate(results_weights[0])}
        #lower_dict = {f'w{i}': val.item() for i, val in enumerate(results_weights[1])}
        #print(f"upper CST parameters:{upper_dict}\n lower CST parameters: {lower_dict}")
        return upper_dict, lower_dict

    def generate_cst(self, upper_weights, lower_weights, folder, filename="", n_points=100):
        """根据权重生成 CST 翼型"""
        def cst_surface(x, weights):
            n = len(weights) - 1
            c_x = x**0.5 * (1 - x)**1.0
            s_x = sum(w * (comb(n, i) * (x**i) * (1 - x)**(n - i)) for i, w in enumerate(weights))
            return c_x * s_x

        beta = np.linspace(0, np.pi, n_points)
        x = 0.5 * (1 - np.cos(beta))
        yu = np.array([cst_surface(xi, upper_weights) for xi in x])
        yl = np.array([cst_surface(xi, lower_weights) for xi in x])
        all_x = np.concatenate([x, x[::-1]])
        all_y = np.concatenate([yu, yl[::-1]])
        if filename:
            df = pd.DataFrame({'x': all_x, 'y': all_y}).drop_duplicates().reset_index(drop=True)
            if not os.path.exists(folder): os.makedirs(folder) 
            if not filename.endswith('.dat'):
                filename = os.path.splitext(filename)[0] + '.dat'
            save_path = os.path.join(folder, filename)
            df.to_csv(save_path, index=False, sep=' ')
            print(f"CST generated: {save_path}")
        return save_path
    

    def plot_airfoil(self, title="Airfoil Visualization"):
        """
        升级版绘图：增加 1/2 中弧线 (Mean Camber Line)
        """
        import matplotlib.pyplot as plt
        if self.upper is None or self.lower is None: 
            print("!!! 数据为空，无法绘图")
            return
            
        up = np.array(self.upper)
        lo = np.array(self.lower)

        # 1. 为了计算准确的中弧线，需要将上下表面的 x 坐标对齐
        # 我们创建一个均匀的 x 轴采样
        x_standard = np.linspace(0, 1, 100)
        
        # 2. 插值得到对齐后的 y 值
        y_up_interp = np.interp(x_standard, up[:, 0], up[:, 1])
        y_lo_interp = np.interp(x_standard, lo[:, 0], lo[:, 1])
        
        # 3. 计算中弧线 (Mean Camber Line)
        mcl = (y_up_interp + y_lo_interp) / 2

        # 4. 绘图
        plt.figure(figsize=(12, 5))
        
        # 画上下表面
        plt.plot(up[:, 0], up[:, 1], 'b-', linewidth=2, label='Upper Surface')
        plt.plot(lo[:, 0], lo[:, 1], 'r-', linewidth=2, label='Lower Surface')
        
        # 画中弧线 (1/2 线)
        plt.plot(x_standard, mcl, 'g--', linewidth=1.2, label='Mean Camber Line (1/2)')
        
        # 装饰
        plt.fill_between(x_standard, y_lo_interp, y_up_interp, color='gray', alpha=0.1) # 填充翼型内部
        plt.axis('equal')
        plt.grid(True, which='both', linestyle=':', alpha=0.5)
        
        # 自动计算最大弯度并在标题显示
        max_camber = np.max(np.abs(mcl)) * 100
        plt.title(f"{title}\nMax Camber: {max_camber:.2f}%")
        
        plt.legend()
        plt.show()

    def sw_sketch_vba(self,  z, chord = 1, angle_deg = 0, pos_x = 0, pos_y = 0, path = ""):
        upper1, lower1 = self.transform_airfoil(chord, angle_deg, pos_x, pos_y)
        vba = '''Dim swApp As Object
Dim Part As Object
Dim boolstatus As Boolean
Dim longstatus As Long, longwarnings As Long
Sub main()
Set swApp = Application.SldWorks
Set Part = swApp.ActiveDoc
Part.ClearSelection2 True'''
        vba += f"\nReDim points(0 To {3 * len(upper1) - 1}) As Double\n"
        for idx, point in enumerate(upper1):
            vba += f"points({idx*3}) = {point[0]}\n"
            vba += f"points({idx*3+1}) = {point[1]}\n"
            vba += f"points({idx*3+2}) = {z}\n"
        vba += "pointArray = points\nSet skSegment = Part.SketchManager.CreateSpline((pointArray))\n"
        vba += f"ReDim points(0 To {3 * len(lower1) - 1}) As Double\n"
        for idx, point in enumerate(lower1):
            vba += f"points({idx*3}) = {point[0]}\n"
            vba += f"points({idx*3+1}) = {point[1]}\n"
            vba += f"points({idx*3+2}) = {z}\n"
        vba += "pointArray = points\nSet skSegment = Part.SketchManager.CreateSpline((pointArray))\nEnd Sub"
        if path:
            with open(path, "w", encoding="gbk") as f: f.write(vba)
        pyperclip.copy(vba)
        print("VBA macro copied to clipboard.")
