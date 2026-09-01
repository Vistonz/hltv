"""重算 Step2 (global_stats) + Step3 (全局透视 + 254 赛事明细).

用法: .venv/bin/python tuning/rerun_step23.py
importlib 加载带空格的 "hltv evp.py" (模块名不含空格).
"""
import importlib.util
import os
import sys

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())  # "hltv evp.py" 内部 import evp_experiment 需要

spec = importlib.util.spec_from_file_location(
    "hltv_evp", "/home/hongbin/Desktop/hltv/hltv evp/hltv evp.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

print("== Step2: 全局统计 ==")
mod.run_step2_calculate_global_stats()
print("== Step3: EVP 透视 + 赛事明细 ==")
mod.run_step3_calculate_evp_pivot()
print("== 全部完成 ==")
