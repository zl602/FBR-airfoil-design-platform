import numpy as np

class PotentialFlowSolver:
    """
    多段翼势流解算器 (基于源-涡混合面板法)
    """
    def __init__(self, v_inf=1.0, alpha_deg=0.0):
        self.v_inf = v_inf
        self.alpha_deg = alpha_deg
        self.alpha_rad = np.radians(alpha_deg)
        self.v_inf_vec = np.array([v_inf * np.cos(self.alpha_rad), 
                                   v_inf * np.sin(self.alpha_rad)])
        
        self.flat_panels = []
        self.wing_boundaries = []
        self.num_p = 0
        self.num_w = 0
        self.A = None
        self.B = None
        self.X = None  # 解向量 [sigma_1...sigma_N, Gamma_1...Gamma_M]

    def build_system(self, all_wings_panels):
        """
        构建 Ax = B 线性方程组
        """
        # 1. 拍平面板并记录边界
        self.flat_panels = []
        self.wing_boundaries = []
        curr_idx = 0
        for w_idx, w_panels in enumerate(all_wings_panels):
            if not w_panels: continue
            start = curr_idx
            # 确保每个面板知道自己属于哪个机翼
            for p in w_panels: p['wing_id'] = w_idx
            self.flat_panels.extend(w_panels)
            end = len(self.flat_panels)
            self.wing_boundaries.append((start, end))
            curr_idx = end
            
        self.num_p = len(self.flat_panels)
        self.num_w = len(self.wing_boundaries)
        
        # 2. 初始化矩阵
        self.A = np.zeros((self.num_p + self.num_w, self.num_p + self.num_w))
        self.B = np.zeros(self.num_p + self.num_w)

        # 3. 填充不穿透条件 (前 N 行)
        for i in range(self.num_p):
            p_i = self.flat_panels[i]
            # 右端项：-V_inf · n_i
            self.B[i] = -(self.v_inf_vec[0] * p_i['nx'] + self.v_inf_vec[1] * p_i['ny'])
            
            for j in range(self.num_p):
                p_j = self.flat_panels[j]
                # 计算法向诱导系数
                inf_s_n, inf_v_n = self._calc_influence(p_i, p_j, mode='normal')
                
                # 源强系数
                self.A[i, j] = inf_s_n
                # 环量系数 (累加到所属机翼列)
                w_id = p_j['wing_id']
                self.A[i, self.num_p + w_id] += inf_v_n

        # 4. 填充 Kutta 条件 (最后 M 行)
        # 条件：后缘上下表面面板切向速度之和为 0 (Vt_first + Vt_last = 0)
        for w_idx, (start, end) in enumerate(self.wing_boundaries):
            row_kutta = self.num_p + w_idx
            idx_f = start
            idx_l = end - 1
            
            # 简化版 Kutta 矩阵填充逻辑
            self.A[row_kutta, idx_f] = 1.0
            self.A[row_kutta, idx_l] = 1.0
            self.A[row_kutta, self.num_p + w_idx] = 1.0 
            self.B[row_kutta] = 0.0

    def solve(self):
        """
        求解方程并返回结果集
        """
        if self.A is None: return None
        
        # 求解线性方程组
        self.X = np.linalg.solve(self.A, self.B)
        
        sigmas = self.X[:self.num_p]
        gammas = self.X[self.num_p:]
        
        panel_results = []
        # 计算每个面板的 Cp
        for i in range(self.num_p):
            p_i = self.flat_panels[i]
            # 来流切向分量
            vt = self.v_inf_vec[0] * p_i['sx'] + self.v_inf_vec[1] * p_i['sy']
            
            # 叠加所有面板的诱导切向速度
            for j in range(self.num_p):
                p_j = self.flat_panels[j]
                inf_s_t, inf_v_t = self._calc_influence(p_i, p_j, mode='tangent')
                
                vt += sigmas[j] * inf_s_t
                vt += gammas[p_j['wing_id']] * inf_v_t
                
            cp = 1.0 - (vt / self.v_inf)**2
            panel_results.append({'x': p_i['xc'], 'y': p_i['yc'], 'cp': cp, 'wing_id': p_i['wing_id']})
            
        return panel_results, gammas

    def _calc_influence(self, p_i, p_j, mode='normal'):
        """
        核心几何计算：计算面板 j 对 i 的诱导系数
        mode: 'normal' (法向) 或 'tangent' (切向)
        """
        # 局部坐标变换
        dx, dy = p_i['xc'] - p_j['p1'][0], p_i['yc'] - p_j['p1'][1]
        xL = dx * np.cos(p_j['angle']) + dy * np.sin(p_j['angle'])
        yL = -dx * np.sin(p_j['angle']) + dy * np.cos(p_j['angle'])
        L = p_j['length']
        
        r1_sq = xL**2 + yL**2
        r2_sq = (xL - L)**2 + yL**2
        
        # 解析积分公式 (单位强度)
        # 源产生的局部速度
        u_s = (0.5 / (2 * np.pi)) * np.log(r1_sq / r2_sq)
        v_s = (1.0 / (2 * np.pi)) * (np.arctan2(yL, xL - L) - np.arctan2(yL, xL))
        
        # 涡产生的局部速度 (对偶关系)
        u_v = v_s
        v_v = -u_s
        
        # 转回全局坐标
        def to_global(u, v):
            return [u * np.cos(p_j['angle']) - v * np.sin(p_j['angle']),
                    u * np.sin(p_j['angle']) + v * np.cos(p_j['angle'])]
        
        v_gs = to_global(u_s, v_s)
        v_gv = to_global(u_v, v_v)
        
        if mode == 'normal':
            return (v_gs[0]*p_i['nx'] + v_gs[1]*p_i['ny']), (v_gv[0]*p_i['nx'] + v_gv[1]*p_i['ny'])
        else:
            return (v_gs[0]*p_i['sx'] + v_gs[1]*p_i['sy']), (v_gv[0]*p_i['sx'] + v_gv[1]*p_i['sy'])

    def get_cl(self, gammas, ref_chord=1.0):
        """
        计算各机翼升力系数
        """
        cls = [(2.0 * g) / (self.v_inf * ref_chord) for g in gammas]
        return cls, sum(cls)