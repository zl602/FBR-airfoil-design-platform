import subprocess
import os

import subprocess
import os
import re

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
    status = True
    # 1. 生成坐标文件
    #print(coords)
    with open(dat_file, "w") as f:
        f.write(f"{name}\n" + "\n".join([f"{c[0]} {c[1]}" for c in coords]))

    # 2. 准备脚本：一次性解决宏观和微观数据
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
        "VPLO",
        "CF",
        f"DUMP {cf_file}", # 导出分离数据
        "", 
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
    return results, cf_file, status

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