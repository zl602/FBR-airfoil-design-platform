import numpy as np

def compute_panel_properties(wings_points):
    """
    输入: export_all_wings_for_solver 返回的 [[(x,y),...], [], []]
    输出: 一个包含三个子列表的列表，每个子列表里是该机翼的所有面板属性(字典格式)
    """
    all_wings_panels = []
    
    for wing_idx, points in enumerate(wings_points):
        if not points:
            all_wings_panels.append([])
            continue
            
        wing_panels = []
        num_pts = len(points)
        
        # 遍历所有点，每两个相邻点组成一个面板
        # 为了闭合，最后一个点会和第一个点连起来
        for i in range(num_pts):
            p1 = points[i]
            # 如果是最后一个点，则连接回第一个点（LE）
            p2 = points[(i + 1) % num_pts]
            
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = np.sqrt(dx**2 + dy**2)
            
            if length < 1e-10: # 避免极小面板导致的除零
                continue
                
            # 1. 中点 (控制点)
            xc = (p1[0] + p2[0]) / 2.0
            yc = (p1[1] + p2[1]) / 2.0
            
            # 2. 单位切向量 (Tangent)
            tx = dx / length
            ty = dy / length
            
            # 3. 单位法向量 (Normal) 
            # 逆时针排序下，向外法线为 (-dy, dx)
            nx = -ty
            ny = tx
            
            # 4. 面板角度 (用于某些势流公式)
            angle = np.arctan2(dy, dx)
            
            panel = {
                'p1': p1,
                'p2': p2,
                'xc': xc,
                'yc': yc,
                'length': length,
                'sx': tx, 'sy': ty, # 切向分量
                'nx': nx, 'ny': ny, # 法向分量
                'angle': angle,
                'wing_id': wing_idx  # 标记属于哪个机翼，方便后面施加Kutta条件
            }
            wing_panels.append(panel)
            
        all_wings_panels.append(wing_panels)
        print(f"Wing {wing_idx+1} 预处理完成: 生成了 {len(wing_panels)} 个面板")
        
    return all_wings_panels


def calc_influence_coefficients(p_i, p_j):
    """
    计算面板 j 对面板 i 控制点的几何影响系数
    p_i: 目标面板 (受影响者)
    p_j: 源面板 (施加影响者)
    """
    # 目标控制点坐标
    xi, yi = p_i['xc'], p_i['yc']
    ni_x, ni_y = p_i['nx'], p_i['ny'] # 目标面板的法向
    
    # 源面板的几何属性
    xj, yj = p_j['p1'][0], p_j['p1'][1]
    length_j = p_j['length']
    theta_j = p_j['angle']
    
    # 坐标变换：将目标点转到源面板 j 的局部坐标系中
    # 这样做可以让积分公式变得极其简单
    dx = xi - xj
    dy = yi - yj
    
    x_local = dx * np.cos(theta_j) + dy * np.sin(theta_j)
    y_local = -dx * np.sin(theta_j) + dy * np.cos(theta_j)
    
    # 计算在局部坐标系下的速度分量 u, v (解析解)
    # 这里处理 r1, r2, theta1, theta2 的对数和反正切
    r1_sq = x_local**2 + y_local**2
    r2_sq = (x_local - length_j)**2 + y_local**2
    
    # 源强 (Source) 产生的局部速度 (单位强度)
    u_s = (0.5 / (2 * np.pi)) * np.log(r1_sq / r2_sq)
    v_s = (1.0 / (2 * np.pi)) * (np.arctan2(y_local, x_local - length_j) - np.arctan2(y_local, x_local))
    
    # 涡强 (Vortex) 产生的局部速度 (单位强度)
    u_v = v_s
    v_v = -u_s
    
    # 将局部速度转回全局坐标系
    v_global_s = [u_s * np.cos(theta_j) - v_s * np.sin(theta_j),
                  u_s * np.sin(theta_j) + v_s * np.cos(theta_j)]
    
    v_global_v = [u_v * np.cos(theta_j) - v_v * np.sin(theta_j),
                  u_v * np.sin(theta_j) + v_v * np.cos(theta_j)]
    
    # 计算对目标面板法向的影响 (点乘法向量)
    # 这就是填充 A 矩阵的元素
    inf_source = v_global_s[0] * ni_x + v_global_s[1] * ni_y
    inf_vortex = v_global_v[0] * ni_x + v_global_v[1] * ni_y
    
    return inf_source, inf_vortex

def build_multi_wing_matrix(all_wings_panels, v_inf=1.0, alpha_deg=0.0):
    """
    构建多段翼势流解算矩阵 Ax = B
    
    参数:
    all_wings_panels: 由 compute_panel_properties 生成的面板列表 [[wing1_panels], [wing2_panels], ...]
    v_inf: 来流速度大小
    alpha_deg: 攻角 (度)
    
    返回:
    A: 系数矩阵 (N+M, N+M)
    B: 右端项向量 (N+M,)
    flat_panels: 拍平后的所有面板列表，方便后续索引
    """
    # 1. 拍平面板并记录各机翼的索引边界
    flat_panels = []
    wing_boundaries = []  # 记录每片机翼面板的起始和结束索引 (start, end)
    
    curr_idx = 0
    for w_panels in all_wings_panels:
        if not w_panels: continue
        start = curr_idx
        flat_panels.extend(w_panels)
        end = len(flat_panels)
        wing_boundaries.append((start, end))
        curr_idx = end
        
    num_p = len(flat_panels)      # 总面板数 N
    num_w = len(wing_boundaries)  # 机翼数量 M
    
    # 初始化 A 矩阵和 B 向量
    A = np.zeros((num_p + num_w, num_p + num_w))
    B = np.zeros(num_p + num_w)
    
    # 计算来流速度矢量
    alpha_rad = np.radians(alpha_deg)
    v_inf_x = v_inf * np.cos(alpha_rad)
    v_inf_y = v_inf * np.sin(alpha_rad)

    # --- 第一部分：填充前 N 行 (不穿透边界条件) ---
    # 方程：Σ(σj * Inf_S_ij) + Σ(Γk * Inf_V_ik) = -V_inf · n_i
    for i in range(num_p):
        p_target = flat_panels[i]
        
        # 填充 B 向量：来流在法向上的投影取负
        B[i] = -(v_inf_x * p_target['nx'] + v_inf_y * p_target['ny'])
        
        # 遍历所有面板 j 对目标面板 i 的影响
        for j in range(num_p):
            p_source = flat_panels[j]
            
            # 计算单位源和单位涡的影响系数
            inf_s, inf_v = calc_influence_coefficients(p_target, p_source)
            
            # 1. 填充源强系数 (A 的左侧 N x N 区域)
            # A[i, i] 会因为 calc_influence_coefficients 内部逻辑自动变为 0.5
            A[i, j] = inf_s
            
            # 2. 填充环量系数 (A 的右侧 N x M 区域)
            # 找到 j 属于哪片机翼，将其涡感应累加到该机翼对应的环量列
            for w_idx, (start, end) in enumerate(wing_boundaries):
                if start <= j < end:
                    A[i, num_p + w_idx] += inf_v
                    break

    # --- 第二部分：填充最后 M 行 (Kutta 条件) ---
    # 这里采用常用的后缘速度相等条件：Vt_first + Vt_last = 0
    for w_idx, (start, end) in enumerate(wing_boundaries):
        row_kutta = num_p + w_idx
        
        # 定义该机翼的后缘面板（第一个和最后一个）
        idx_first = start
        idx_last = end - 1
        
        # Kutta 条件：对这两个面板的切向感应进行约束
        # 简化逻辑：在 A 矩阵中直接对这两个面板的源强和总环量进行线性组合
        # 注意：这里的系数通常需要计算切向影响系数，此处先给出一个典型的常系数模型
        A[row_kutta, idx_first] = 1.0
        A[row_kutta, idx_last] = 1.0
        A[row_kutta, num_p + w_idx] = 1.0  # 代表该机翼自身环量的贡献
        
        # Kutta 条件方程右端项通常为 0
        B[row_kutta] = 0.0
        
    return A, B, flat_panels