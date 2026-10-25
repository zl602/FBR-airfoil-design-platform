import subprocess
import os

import subprocess
import os
import re
import numpy as np

if os.name == 'nt':  # 如果是 Windows 系统
    startupinformation = subprocess.STARTUPINFO()
    startupinformation.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinformation.wShowWindow = subprocess.SW_HIDE
else:
    startupinformation = None

def run_xfoil(name, coords, panel, alpha, reynold, xfoil_path):
    dat_file = f"{name}.dat"
    input_file = f"{name}.in"
    cf_file = f"{name}_cf.txt"
    cp_file = f"{name}_cp.txt"  # <--- 新增：压力分布文件名
    status = True
    # 1. 生成坐标文件
    #print(coords)
    with open(dat_file, "w") as f:
        f.write(f"{name}\n" + "\n".join([f"{c[0]} {c[1]}" for c in coords]))

    # 2. 准备脚本：一次性解决宏观和微观数据
# 2. 准备脚本：增加 CPWR 指令
    commands = [
        f"LOAD {dat_file}",
        "PANE",
        "PPAR",
        f"N {panel}",
        "",
        "",
        "OPER",
        f"VISC {reynold}",
        "ITER 100",
        f"ALFA {alpha}",
        f"CPWR {cp_file}",   # <--- 核心改动：要求 XFOIL 输出 Cp 数据
        "VPLO",
        "CF",
        f"DUMP {cf_file}",
        "", 
        "QUIT"
    ]
    
    with open(input_file, "w") as f:
        f.write("\n".join(commands) + "\n")
    input_str = "\n".join(commands) + "\n"
    try:
    # 3. 执行
        proc = subprocess.run(
            f"{xfoil_path} < {input_file}",
            #shell=True, 
            input=input_str,
            capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10
        )
        
        stdout = proc.stdout
    except subprocess.TimeoutExpired:
        # 4. 如果超时，打印警告并记录，准备进入下一次循环
        print(f"⚠️Subprocess timed out\n")
        status = False
        return None, None, status
        # 注意：subprocess.run 在超时时会自动 kill 掉子进程
    except Exception as e:
        print(f"{e}\n")
        status = False
        return None, None, status


    # 4. 从 stdout 解析 Cl, Cd, Cm (正则提取)
    # XFOIL 输出格式示例: a = 10.000  CL = 1.2726  Cm = -0.0125  CD = 0.01288
    results = {
        "cl": None, "cd": None, "cm": None, "ld": None, "converged": False
    }
    #print(stdout)
    
    if "Converged" in stdout or "CL =" in stdout:
        results["converged"] = True
        try:
            # 使用正则精准打击
            cl_match = re.search(r"CL\s*=\s*([\d\.-]+)", stdout)
            cd_match = re.search(r"CD\s*=\s*([\d\.-]+)", stdout)
            cm_match = re.search(r"Cm\s*=\s*([\d\.-]+)", stdout)
            
            if cl_match: results["cl"] = float(cl_match.group(1))
            if cd_match: results["cd"] = float(cd_match.group(1))
            if cm_match: results["cm"] = float(cm_match.group(1))
            
            # 计算升阻比 L/D
            if results["cl"] is not None and results["cd"] and results["cd"] != 0:
                results["ld"] = results["cl"] / results["cd"]
        except (ValueError, ZeroDivisionError):
            pass

    # 5. 清理（保留 cf_file 供后续分离点分析）
    for f in [dat_file, input_file]:
        if os.path.exists(f): os.remove(f)
    status = True
    return results, cf_file, cp_file, status

def _read_polar(polar_file):
    """解析 PACC 保存的极曲线文件，返回 {alpha: [CL, CD, CDp, CM, Top_Xtr, Bot_Xtr]}（只含收敛点）"""
    rows = {}
    if not os.path.exists(polar_file):
        return rows
    started = False
    with open(polar_file, 'r') as f:
        for line in f:
            if line.strip().startswith('------'):
                started = True
                continue
            if not started:
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            try:
                vals = [float(p) for p in parts[:7]]
            except ValueError:
                continue
            rows[round(vals[0], 3)] = vals[1:]
    return rows

def run_xfoil_sweep(name, coords, panel, alphas, reynold, xfoil_path):
    """
    攻角扫描：一次 XFOIL 会话内依次计算多个攻角，每个攻角输出 Cp 和 Cf。
    从最接近 0° 的攻角向正方向推进，INIT 重置边界层后再向负方向推进，
    让每个点都以相邻收敛解为初值，大攻角更容易收敛。
    只保留写进极曲线文件（即真正收敛）的攻角。
    返回按攻角升序的列表，每项: {alpha, cl, cd, cm, ld, cp (N×2: x, Cp), sep_x}
    """
    alphas = sorted({round(float(a), 3) for a in alphas})
    if not alphas:
        return []
    dat_file = f"{name}.dat"
    polar_file = f"{name}_polar.txt"
    cp_files = [f"{name}_cp{i}.txt" for i in range(len(alphas))]
    cf_files = [f"{name}_cf{i}.txt" for i in range(len(alphas))]
    generated = [dat_file, polar_file] + cp_files + cf_files

    # XFOIL 会向已存在的极曲线文件追加，先清理上次的残留
    for f in generated:
        if os.path.exists(f): os.remove(f)

    with open(dat_file, "w") as f:
        f.write(f"{name}\n" + "\n".join([f"{c[0]} {c[1]}" for c in coords]))

    def session(branches, polar, iters):
        """运行一次 XFOIL；branches 中每组攻角开始前都 INIT 重置边界层"""
        commands = [
            "PLOP", "G", "",          # 关闭绘图窗口（数据输出不受影响）
            f"LOAD {dat_file}",
            "PANE",
            "PPAR",
            f"N {panel}",
            "",
            "",
            "OPER",
            f"VISC {reynold}",
            f"ITER {iters}",
            "PACC", polar, "",        # 收敛点自动写入极曲线文件
        ]
        for b, idx_list in enumerate(branches):
            if b > 0:
                commands.append("INIT")
            for i in idx_list:
                commands += [
                    f"ALFA {alphas[i]}",
                    f"CPWR {cp_files[i]}",
                    "VPLO",
                    "CF",
                    f"DUMP {cf_files[i]}",
                    "",
                ]
        commands += ["", "QUIT"]
        n = sum(len(b) for b in branches)
        try:
            subprocess.run(
                [xfoil_path],
                input="\n".join(commands) + "\n",
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=15 + 3 * n * iters / 100,
                startupinfo=startupinformation,
            )
        except subprocess.TimeoutExpired:
            # 超时也照常解析：已经收敛的攻角都在极曲线文件里
            print("⚠️Subprocess timed out\n")
        except Exception as e:
            print(f"{e}\n")
        return _read_polar(polar)

    # 第一轮：从最接近 0° 的攻角向两侧推进
    pivot = min(range(len(alphas)), key=lambda i: abs(alphas[i]))
    branches = [list(range(pivot, len(alphas))), list(range(pivot - 1, -1, -1))]
    polar = session([b for b in branches if b], polar_file, 100)

    # 第二轮：未收敛的攻角各自从头初始化重算（迭代上限加倍）
    failed = [i for i, a in enumerate(alphas) if a not in polar]
    if failed and len(failed) < len(alphas):
        polar_retry = f"{name}_polar2.txt"
        generated.append(polar_retry)
        if os.path.exists(polar_retry): os.remove(polar_retry)
        polar.update(session([[i] for i in failed], polar_retry, 200))

    results = []
    for i, a in enumerate(alphas):
        if a not in polar or not os.path.exists(cp_files[i]):
            continue
        cl, cd, _, cm = polar[a][:4]
        cp = np.loadtxt(cp_files[i], skiprows=3)[:, [0, 2]]
        _, _, sep_x = analyze_cf_data(cf_files[i])
        results.append({
            "alpha": a, "cl": cl, "cd": cd, "cm": cm,
            "ld": cl / cd if cd else None,
            "cp": cp, "sep_x": sep_x,
        })

    for f in generated:
        if os.path.exists(f): os.remove(f)
    return assess_credibility(results, reynold)

def assess_credibility(results, reynold=1e6):
    """
    基于 airfoil_database 1.3 的数据清洗规则，给扫描结果标记可信度：
    r['warnings'] 为原因列表，空列表表示可信。
      1. 分离点：x/c < 0.1 为前缘失速；x/c <= 0.7 为失速发展（0.7 之后的尾缘分离可接受）
      2. 阈值：CL >= 3、CD >= CD_lim(Re)、L/D >= 300 视为超出可信范围
      3. 梯度：L/D 出现孤立尖峰 / 下凹，视为数值异常
      4. 出现第 2 个失速点或第 8 个异常点后，数据库不再计算更远的攻角，这里统一标为超出可信范围
    从最接近 0° 的攻角分别向正、负两侧推进判定（数据库从 0° 向上扫描）。

    相对数据库放宽的两条（数据库的阈值是在 Re 5e5~1e6、0.1° 步长下定的，
    直接用于低雷诺数和 1° 步长会在小攻角误报）：
      - CD 阈值随雷诺数放宽：0.02 × max(1, (1e6/Re)^0.5)，层流摩阻约随 Re^-0.5 变化；
        Re >= 1e6 时仍为 0.02
      - L/D 不再看"比前一攻角涨了多少"（与步长有关，线性段正常上升也会触发），
        改为与前后两个攻角的线性插值比较，偏离 >= 40% 才算异常（只看曲线弯折，与步长无关）；
        扫描端点只有一侧邻点，沿用原规则，但只在越过 L/D 极值之后检查
    放宽 CD 阈值后，低雷诺数下刚越过 CLmax 的一两个攻角可能不再被 CD 捕捉，因此另加：
      5. 越过整个扫描的 CL 最大值（负攻角一侧为 CL 最小值）之后的攻角，XFOIL 失速后结果不可信
    """
    if not results:
        return results
    cd_lim = CD_LIMIT_BASE * max(1.0, (1e6 / reynold) ** CD_LIMIT_RE_EXP)
    ld_anomaly = _ld_anomalies(results)
    pivot = min(range(len(results)), key=lambda i: abs(results[i]['alpha']))

    # 规则 5：用整段扫描的极值（而非局部极值），附着流区 CL 的小波动不会触发；
    # 扫描未到失速时极值就在端点，不标记任何点
    past_clmax = {}
    pos, neg = results[pivot:], results[:pivot + 1]
    if len(pos) > 1:
        top = max(pos, key=lambda r: r['cl'])
        for r in pos[pos.index(top) + 1:]:
            if r['cl'] < top['cl']:
                past_clmax[id(r)] = f"Past CLmax ({top['cl']:.3f} at {top['alpha']:g}°): XFOIL post-stall results are unreliable"
    if len(neg) > 1:
        bottom = min(neg, key=lambda r: r['cl'])
        for r in neg[:neg.index(bottom)]:
            if r['cl'] > bottom['cl']:
                past_clmax[id(r)] = f"Past CLmin ({bottom['cl']:.3f} at {bottom['alpha']:g}°): XFOIL post-stall results are unreliable"
    branches = [results[pivot:], [results[pivot]] + results[:pivot][::-1]]
    for b, branch in enumerate(branches):
        stall_count, weird_count = 0, 0
        for r in branch:
            if b > 0 and r is results[pivot]:
                continue          # 0° 附近的点已在正方向判定过
            warnings = []
            if stall_count >= 2:
                warnings.append("Beyond stall: past the 2nd stalled angle, XFOIL post-stall results are unreliable")
            elif weird_count >= 8:
                warnings.append("Past 8 anomalous readings: XFOIL is likely diverging in this range")

            sep, cl, cd, ld = r['sep_x'], r['cl'], r['cd'], r['ld']
            if sep is not None:
                if sep < 0.1:
                    stall_count = 3
                    warnings.append(f"Leading-edge stall: separation at x/c = {sep:.3f} (< 0.1)")
                elif sep <= 0.7:
                    stall_count += 1
                    warnings.append(f"Stall developing: separation at x/c = {sep:.3f} (<= 0.7)")

            weird = []
            if cl >= 3: weird.append(f"CL = {cl:.3f} (>= 3)")
            if cd >= cd_lim: weird.append(f"CD = {cd:.4f} (>= {cd_lim:.3f} at Re {reynold:.3g})")
            if ld is not None and ld >= 300: weird.append(f"L/D = {ld:.0f} (>= 300)")
            if weird:
                weird_count += 1
                warnings.append("Outside trusted range: " + ", ".join(weird))

            if id(r) in ld_anomaly:
                weird_count += 1
                warnings.append(ld_anomaly[id(r)])

            if id(r) in past_clmax:
                warnings.append(past_clmax[id(r)])

            r['warnings'] = warnings
    return results

CD_LIMIT_BASE = 0.02       # 数据库在 Re 1e6 附近使用的 CD 上限
CD_LIMIT_RE_EXP = 0.5      # 低雷诺数下的放宽指数（层流摩阻 ~ Re^-0.5）
LD_JUMP = 0.4              # L/D 偏离 / 突增的判定比例
LD_MIN = 40                # 参与比较的 |L/D| 下限（零升附近比例会被放大）

def _ld_anomalies(results):
    """返回 {id(结果): 原因}，标出 L/D 曲线上的孤立尖峰 / 下凹（results 按攻角升序）"""
    out = {}
    n = len(results)
    ld = [r['ld'] for r in results]
    al = [r['alpha'] for r in results]

    # 中间点：与前后两点按攻角线性插值的期望值比较
    dev, expected = {}, {}
    for i in range(1, n - 1):
        if None in (ld[i - 1], ld[i], ld[i + 1]):
            continue
        if min(abs(ld[i - 1]), abs(ld[i + 1])) < LD_MIN:
            continue
        e = ld[i - 1] + (ld[i + 1] - ld[i - 1]) * (al[i] - al[i - 1]) / (al[i + 1] - al[i - 1])
        if abs(e) < LD_MIN:
            continue
        expected[i], dev[i] = e, (ld[i] - e) / abs(e)
    for i, d in dev.items():
        # 一个异常点会把相邻点的期望值也带偏，只标偏离最大的那个
        if abs(d) >= LD_JUMP and all(abs(d) >= abs(dev.get(j, 0)) for j in (i - 1, i + 1)):
            kind = "spike" if d > 0 else "dip"
            out[id(results[i])] = (f"L/D {kind}: {ld[i]:.1f} vs {expected[i]:.1f} expected from "
                                   f"{al[i - 1]:g}° and {al[i + 1]:g}° ({d:+.0%}, numerical anomaly)")

    # 端点：只有一侧邻点。沿外推方向看 L/D（负攻角一侧取相反数），
    # 端点之前的极值已经过去（L/D 本应下降）时仍突增 >= 40% 才算异常
    pivot = min(range(n), key=lambda k: abs(al[k]))
    ends = []
    if n - 1 > pivot: ends.append((n - 1, n - 2, 1, range(pivot, n - 1)))   # 正攻角一侧
    if pivot > 0:     ends.append((0, 1, -1, range(1, pivot + 1)))           # 负攻角一侧
    for end, inner, sign, branch in ends:
        if ld[end] is None or ld[inner] is None or abs(ld[inner]) < LD_MIN:
            continue
        s = {k: sign * ld[k] for k in branch if ld[k] is not None}
        if not s:
            continue
        peak = max(s, key=s.get)           # 不含端点本身
        past_peak = peak != inner          # 极值在 inner 之前，说明已在下降段
        delta = (sign * ld[end] - sign * ld[inner]) / abs(ld[inner])
        if past_peak and delta >= LD_JUMP:
                out[id(results[end])] = (f"L/D jumped {delta:+.0%} from {al[inner]:g}° "
                                         f"after the L/D peak (numerical anomaly)")
    return out

def run_xfoil_naca_auto_kill(name, naca_code, panel, alpha, reynold, xfoil_path):
    input_file = f"{name}.in"
    cf_file = f"{name}_cf.txt"
    
    # 1. 准备脚本 (直接用 NACA 指令更快，避免读取 dat 文件)
    commands = [
        f"NACA {naca_code}",
        "PANE",
        "PPAR",
        f"N {panel}",
        "",
        "",
        "OPER",
        f"VISC {reynold}",
        "ITER 100",
        f"ALFA {alpha}",
        "VPLO",
        "CF",
        f"DUMP {cf_file}", 
        "", 
        "",
        "QUIT"
    ]
    
    with open(input_file, "w") as f:
        f.write("\n".join(commands) + "\n")

    results = {
        "cl": None, "cd": None, "cm": None, "ld": None, "converged": False, "error": None
    }

    # 2. 执行并加入 10 秒超时限制
    try:
        proc = subprocess.run(
            f"{xfoil_path} < {input_file}",
            shell=True, 
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            errors='ignore',
            timeout=10,  # <--- 核心改动：10秒必杀
            # startupinfo=startupinformation # 如果是Windows隐藏窗口请保留
        )
        stdout = proc.stdout

        # 3. 解析结果 (逻辑同你之前的)
        if "Converged" in stdout or "CL =" in stdout:
            results["converged"] = True
            cl_match = re.search(r"CL\s*=\s*([\d\.-]+)", stdout)
            cd_match = re.search(r"CD\s*=\s*([\d\.-]+)", stdout)
            cm_match = re.search(r"Cm\s*=\s*([\d\.-]+)", stdout)
            
            if cl_match: results["cl"] = float(cl_match.group(1))
            if cd_match: results["cd"] = float(cd_match.group(1))
            if cm_match: results["cm"] = float(cm_match.group(1))
            
            if results["cl"] is not None and results["cd"]:
                results["ld"] = results["cl"] / results["cd"]

    except subprocess.TimeoutExpired:
        # 4. 如果超时，打印警告并记录，准备进入下一次循环
        print(f"⚠️Subprocess timed out")
        results["error"] = "Timeout"
        # 注意：subprocess.run 在超时时会自动 kill 掉子进程
    except Exception as e:
        results["error"] = str(e)
    finally:
        # 5. 清理脚本文件
        if os.path.exists(input_file):
            os.remove(input_file)

    return results, cf_file

def analyze_cf_data(cf_file):
    """
    高级解析器：区分分离气泡和永久分离
    返回格式: (bubble_start, bubble_end, true_separation_x)
    """
    if not os.path.exists(cf_file):
        return None, None, None

    points = []
    with open(cf_file, 'r') as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                try:
                    x, cf = float(parts[0]), float(parts[1])
                    if x > 1.0: break  # 忽略尾迹区
                    points.append((x, cf))
                except: continue

    # 识别吸力面（第一段数据直到 x 到达 1.0）
    # 如果数据里有两段，x 会从 1.0 跳回 0，这里逻辑只处理第一段
    
    bubble_start = None
    bubble_end = None
    true_separation_x = None
    
    for i in range(len(points) - 1):
        curr_x, curr_cf = points[i]
        next_x, next_cf = points[i+1]

        # 1. 捕捉分离发生（由正变负）
        if curr_cf >= 0 and next_cf < 0:
            potential_sep = next_x
            
            # 向后探测，看它是否重新贴附
            reattached = False
            for j in range(i + 1, len(points)):
                if points[j][1] > 0:
                    bubble_start = potential_sep
                    bubble_end = points[j][0]
                    reattached = True
                    break
            
            # 2. 如果直到最后都没有重新贴附，那就是真正的分离
            if not reattached:
                true_separation_x = potential_sep
                break # 既然已经彻底分离，后面的数据就不看了

    return bubble_start, bubble_end, true_separation_x