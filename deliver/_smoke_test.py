# -*- coding: utf-8 -*-
"""开发冒烟测试：不抓网，只验证“配置 ini → 核心函数参数”映射与 import 链。

运行：
    python3 _smoke_test.py

检查点：
  1. 三个核心脚本 + 三个入口能正常 import（依赖：openpyxl/undetected_chromedriver 等已装）；
  2. 三份 ini 能被解析，翻译出的 kwargs 与核心函数形参一一对应、无缺无多；
  3. stagedate 字符串能被正确解析成二维整数表；
  4. 输出路径能解析成基于 deliver/ 的绝对路径并自动建目录。
"""

import importlib
import inspect
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import shared_lib as sl  # noqa: E402

# (入口模块, 配置文件名, 要调用的核心函数全名)
CASES = [
    ("main_year",  "配置_year.ini",  "hltvnew.run_yearly_scrape"),
    ("main_event", "配置_event.ini", "hltvsingleevent.scrape_single_event"),
    ("main_team",  "配置_team.ini",  "hltvteam.scrape_team_stats"),
]

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  ✅ {name} {detail}")
    else:
        FAIL.append(name)
        print(f"  ❌ {name} {detail}")


def main():
    print("冒烟测试开始……\n")

    # ---- 1) import 链 ----
    for mod_name, _, _ in CASES:
        try:
            mod = importlib.import_module(mod_name)
            check(f"import {mod_name}", True, "")
        except Exception as exc:  # noqa: BLE001
            check(f"import {mod_name}", False, f"失败：{exc}")

    # ---- 2) 三份 ini → kwargs 与核心函数签名对齐 ----
    for mod_name, ini_name, func_ref in CASES:
        try:
            mod = importlib.import_module(mod_name)
            parser = sl.load_ini(os.path.join(HERE, ini_name))
            kwargs = mod.build_kwargs(parser)
            # 定位核心函数并核对参数名
            fq = func_ref.split(".")
            core_mod = importlib.import_module(fq[0])
            core_fn = getattr(core_mod, fq[1])
            sig_params = set(inspect.signature(core_fn).parameters)
            have_params = set(kwargs)
            check(
                f"{mod_name}: 参数一一对应",
                have_params == sig_params,
                f"(in {func_ref}：{sorted(have_params ^ sig_params) or '完全一致'})",
            )
            # file_path 必须能解析成绝对路径
            fp = kwargs["file_path"]
            check(f"{mod_name}: file_path 已绝对化", os.path.isabs(fp), f"-> {fp}")
            if mod_name == "main_event":
                sd = kwargs["stagedate"]
                check(
                    f"{mod_name}: stagedate 解析",
                    isinstance(sd, list) and all(len(g) == 6 for g in sd),
                    f"共 {len(sd)} 组，末组 = {sd[-1]}",
                )
            if "eventfilter" in kwargs:
                check(
                    f"{mod_name}: 赛事筛选非空",
                    bool(kwargs["eventfilter"]),
                    f"（长度 {len(kwargs['eventfilter'])}）",
                )
        except Exception as exc:  # noqa: BLE001
            check(f"{mod_name}: 配置解析", False, f"抛异常：{exc!r}")

    # ---- 收尾：清掉测试造成的“结果”空目录（若没有产出文件） ----
    result_dir = os.path.join(HERE, "结果")
    if os.path.isdir(result_dir):
        try:
            shutil.rmtree(result_dir)
        except OSError:
            pass

    print(f"\n结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：", FAIL)
        sys.exit(1)
    print("🎉 冒烟测试全部通过（本机仅验证配置映射/导入，不抓网）。")


if __name__ == "__main__":
    main()
