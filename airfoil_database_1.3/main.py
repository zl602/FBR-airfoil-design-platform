from functions.run import run_naca, run_parsec
import time
import numpy as np
import csv
import os


xfoil_path = r"D:\FBR_database\airfoil_database_1.1\xfoil\xfoil.exe"
csv_file = r"D:\FBR_database\airfoil_database_1.2\bubble_study.csv"
parsec_settings = { #naca2414
    "rle": [False, 0.0216, 0, 0],         # 前缘半径（替换为 r_le=0.0216）
    "x_pre": [False, 0.2365, 0, 0],        # 下表面最低点横坐标（替换为 X_lo=0.2365）
    "y_pre": [False, -0.0519, 0, 0],      # 下表面最低点纵坐标（替换为 Z_lo=-0.0519）
    "d2ydx2_pre": [False, 0.3141, 0, 0],    # 下表面曲率（替换为 Z_xxlo=0.3141）
    "th_pre": [False, -0.08, 0, 0],      # 下表面后缘角（无匹配值，保留原数值）
    "x_suc": [False, 0.3240, 0, 0],        # 上表面最高点横坐标（替换为 X_up=0.3240）
    "y_suc": [False, 0.0888, 0, 0],       # 上表面最高点纵坐标（替换为 Z_up=0.0888）
    "d2ydx2_suc": [False, -0.6363, 0, 0],   # 上表面曲率（替换为 Z_xxup=-0.6363）
    "th_suc": [False, -0.18, 0, 0],      # 上表面后缘角（无匹配值，保留原数值）
    
    # --- 迭代变量：恢复原始数值 ---
    "alpha": [True, 0, 40.0, 1],     # 攻角：恢复为原始值 -10.0
    "reynold": [True, 3e6, 5e6, 5e5],      # 雷诺数：恢复为原始值 5e5
    "panels": [False, 400, 400, 50],          # 无匹配值，保留原数值

}
naca_settings = {
    "max_camber": [True, 4, 6, 1],
    "max_camber_position": [True, 40, 70, 10],
    "thickness" : [True, 8, 13, 1.0],
    # --- 计算设置 ----------------------------------------------
    "reynold": [True, 5e5, 1e6, 2.5e5],
    "alpha": [True, 0, 10, 0.1],     
    "panels": [False, 300, 400, 50],        
}
def gen_cases(settings):
    cases = {}
    keys = list(settings.keys())
    count = 1

    for i in range(len(keys)):
        content = settings[keys[i]]
        if content[0]:
            cases[keys[i]] = np.arange(content[1], content[2] + content[3]/10, content[3]).tolist()
        else: 
            cases[keys[i]] = [content[1]]
        count = count * len(cases[keys[i]])


    print(cases)
    return cases, count

import itertools

def calculation(cases, count, approach):
    keys = list(cases.keys())
    values = list(cases.values())
    stall_counts = {}
    
    while True:
        proceed = input(f"{count} cases to be calculated, do you want to proceed? [y/n]:")
        if proceed in ["y", "Y"]: break
        if proceed in ["n", "N"]: return

    all_combos = itertools.product(*values)
    

    
    # 结果缓存，每 50 组存一次盘，防止频繁 IO 影响速度
    results_buffer = []
    
    for i, combo in enumerate(all_combos):
        c = dict(zip(keys, combo))
        if approach == "parsec": 
        
            # 1. 构造 pparray
            pparray = [c["rle"], c["x_pre"], c["y_pre"], c["d2ydx2_pre"], c["th_pre"], 
                    c["x_suc"], c["y_suc"], c["d2ydx2_suc"], c["th_suc"]]
            
            aoa = c["alpha"]
            reynolds = c["reynold"]
            panels = int(c["panels"])
            case_name = f"case_{i}"
            
            print(f"[{i+1}/{count}] Calculating {case_name}: Alpha={aoa}, Re={reynolds}")
            
            # 2. 执行计算
            # 注意：这里需要接收 run 返回的结果字典
            output_results = run_parsec(case_name, pparray, panels, aoa, reynolds, xfoil_path)

        
        if approach == "naca": 
        
            # 1. 构造 pparray
            if int(c["thickness"]) < 10:
                naca = f'''{int(c["max_camber"])}{int(c["max_camber_position"])}{int(c["thickness"])}'''
            else: 
                naca = f'''{int(c["max_camber"])}{int(int(c["max_camber_position"])/10)}{int(c["thickness"])}'''
            namae = f'''{naca}_Re{c["reynold"]}'''
            if namae not in list(stall_counts.keys()):
                stall_counts[namae] = 0
                stall_counts[f"{namae}_wierd_reading"] = 0

            
            
            aoa = c["alpha"]
            reynolds = c["reynold"]
            panels = int(c["panels"])
            case_name = f"case_{i + 1}"

            
            print(f'''[{i+1}/{count}] Calculating {case_name}: NACA {naca}, Alpha={aoa}, Re={reynolds}, stall count: {stall_counts[namae]}, ayashii: {stall_counts[f"{namae}_wierd_reading"]}''')
            if stall_counts[namae] >= 2 or stall_counts[f"{namae}_wierd_reading"] >= 8:
                print("Already stalled or numerically diverged, skip this case\n")
                continue
            # 2. 执行计算
            # 注意：这里需要接收 run 返回的结果字典
            output_results = run_naca(case_name, naca, panels, aoa, reynolds, xfoil_path)
            
            #Translations: "jyoutai" means "status" in Japanese, "ayashii" means "dodgy", "shinyou" means "trust/credit"
            jyoutai = None
            if output_results:
                #Stall monitor: TE stall after x = 0.7 is acceptable, LE stall leads to end of calculation of current airfoil
                if output_results["separation"]:
                    if output_results["separation"] <= 0.7:
                        stall_counts[namae] += 1
                    if output_results["separation"] < 0.1:
                        stall_counts[namae] = 3
                        jyoutai = "ayashii"
                #Physically unrealistic quantities
                if output_results["cl"] >= 3 or output_results["cd"] >= 0.02 or output_results["ld"] >= 300:
                    stall_counts[f"{namae}_wierd_reading"] +=1
                    jyoutai = "ayashii"
                #check sudden changes (instead of a gradual process) of L/D, which indicates xfoil is doing sth wierd
                if len(results_buffer) != 0:
                    delta_ld = (-results_buffer[len(results_buffer)-1]["ld"] + output_results["ld"])/abs(results_buffer[len(results_buffer)-1]["ld"])
                    #print(f"delta l/d: {delta_ld}, shinyou: {jyoutai}")
                    # We only track sudden increase, as it might just be a vibration. If it dropps dramatically and rises again it will still be detected
                    if delta_ld >= 0.4 and results_buffer[-1]["naca"] == naca and abs(results_buffer[len(results_buffer)-1]["ld"]) >= 40:
                        stall_counts[f"{namae}_wierd_reading"] +=1
                        jyoutai = "ayashii"
                    print(f"delta l/d: {delta_ld}, shinyou: {jyoutai}\n")
                
                # 3. 合并输入和输出数据
                # 把输入参数 (c) 和输出结果 (output_results) 整合到一个字典里
                naca_dict ={"naca":naca, "alpha": aoa, "Re":reynolds, "shinyou": jyoutai}
                combined_data = {**naca_dict, **output_results}
                results_buffer.append(combined_data)
            
            # 4. 定期保存到 CSV
            if (i + 1) == count:
                save_to_csv(results_buffer, csv_file)
            elif len(results_buffer) >= 20:
                save_to_csv(results_buffer[:-1], csv_file)
                results_buffer = [results_buffer[-1]] # 清空缓存
                print("\n ------------------AUTO SAVED---------------------------------------------\n")

    print(f"所有数据已保存至 {csv_file}")

def save_to_csv(data_list, filename):
    """将字典列表追加保存到 CSV"""
    if not data_list: return
    
    file_exists = os.path.isfile(filename)
    keys = data_list[0].keys()
    
    with open(filename, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        # 如果文件是新建的，先写表头
        if not file_exists:
            writer.writeheader()
        writer.writerows(data_list)
    
from datetime import timedelta
# 测试运行
start_time = time.time()
cases, count = gen_cases(naca_settings)
calculation(cases, count, "naca")
end_time = time.time()
elapsed_time = end_time - start_time
readable_time = str(timedelta(seconds=elapsed_time))
print(f"总耗时 (时:分:秒): {readable_time}")
#run("test_test", pparray, panels, aoa, reynolds, xfoil_path)
