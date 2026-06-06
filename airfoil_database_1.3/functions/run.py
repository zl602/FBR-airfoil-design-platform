from functions.parsec import parsec
from functions.xfoil_ops import run_xfoil, analyze_cf_data, run_xfoil_naca_auto_kill
from functions.naca import naca4
import sys
import time
import os
import json


start = time.perf_counter()




def run_parsec(name, pparray, panel, alpha, reynold, xfoil_path):
    _, coords = parsec(pparray)
    results, cf_file, status = run_xfoil(name, coords, panel, alpha, reynold, xfoil_path)
    if status == True: 
        bubble_start, bubble_end, true_separation_x = analyze_cf_data(cf_file)
        results['bubble_start'] = bubble_start
        results['bubble_end'] = bubble_end
        results['separation'] = true_separation_x
        print(results)
    if cf_file:
        if os.path.exists(cf_file):
            os.remove(cf_file)
    return results

def run_naca(name, naca, panel, alpha, reynold, xfoil_path):
    _, coords = naca4(naca, 400, False, False)
    #print(coords)
    results, cf_file, status = run_xfoil(name, coords, panel, alpha, reynold, xfoil_path)
    if status == True: 
        bubble_start, bubble_end, true_separation_x = analyze_cf_data(cf_file)
        results['bubble_start'] = bubble_start
        results['bubble_end'] = bubble_end
        results['separation'] = true_separation_x
        print(results)
    print()
    if cf_file:
        if os.path.exists(cf_file):
            os.remove(cf_file)
    return results


#run("test_test",coords, 200, 10, 4e6, r"D:\airfoil_database\functions\xfoil.exe")

elapsed = time.perf_counter() - start
print(f"⏱️ 完成！用时: {elapsed}")