"""重生成 CS2 交付物 (2026-09-10) — 只跑生产 Step 2 + Step 3, 不触碰 Step 0/1/1.5.

背景: 两套分拆后 CS2 生产口径 = EVP_CONFIG + CS2_OVERRIDES (kprw_e / dpr 2 轴机制).
交付物 event_{eid}_evp_summary.xlsx 上次生成于 2026-09-01 (机制定案之前), 需按新口径重生成.
按冻结策略 **CS:GO 190 个交付物不重写** (EVP_WRITE_EVENTS=cs2 门控); 但全局分布
(global_stats.json) 与透视表 (global_evp_pivot_summary.xlsx) 用全部赛事行重算.

流程:
  1. 快照: 全部 event_*_evp_summary.xlsx + global_stats.json + 透视表 的 md5 (前后对比).
  2. Step 2: 重算全局 mean/std (CS2 机制-on 口径) → global_stats.json.
  3. Step 3: 全赛事计算 (行数据供透视表), 只写 CS2 段交付物 + 重写透视表.
  4. 复核: ① 变更文件必须全部属 CS2 段 (CS:GO 逐一未变); ② 抽一个 CS2 赛事, 把交付物
     顶部选手 evp_score 与 run_experiment(cfg_for("cs2")) 直接对拍 (证明机制已进产物).

用法: .venv/bin/python tuning/regen_cs2_deliverables.py
"""
import hashlib
import importlib.util
import json
import os
import sys
import time

ROOT = "/home/hongbin/Desktop/hltv/hltv evp"
DB = "/home/hongbin/Desktop/hltv/database/event"
PIVOT = os.path.join(ROOT, "global_evp_pivot_summary.xlsx")
STATS = os.path.join(DB, "global_stats.json")

os.chdir(ROOT)
sys.path.insert(0, ROOT)

# 必须在 import 前设置: hltv evp.py 模块级读取 WRITE_EVENTS
os.environ["EVP_WRITE_EVENTS"] = "cs2"

import pandas as pd  # noqa: E402
import eval_full as ev  # noqa: E402
import evp_experiment as evp_exp  # noqa: E402


def _md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def snapshot():
    out = {}
    for eid in os.listdir(DB):
        p = os.path.join(DB, eid, f"event_{eid}_evp_summary.xlsx")
        if os.path.exists(p):
            out[p] = _md5(p)
    for extra in (STATS, PIVOT):
        if os.path.exists(extra):
            out[extra] = _md5(extra)
    return out


def _seg_of_path(p):
    """交付物路径 → 赛事段 ('csgo'/'cs2'), 非赛事文件 → None."""
    if not p.startswith(DB):
        return None
    eid = os.path.basename(os.path.dirname(p))
    return ev.segment_of(eid) if eid.isdigit() else None


def verify_content():
    """抽样对拍: 某 CS2 交付物顶部选手 evp_score ?= run_experiment(cfg_for('cs2')) 顶部 total_score."""
    import io
    import contextlib
    for eid in sorted(os.listdir(DB)):
        f = os.path.join(DB, eid, f"event_{eid}_evp_summary.xlsx")
        raw = os.path.join(DB, eid, f"raw_event_{eid}_data.xlsx")
        if not (os.path.exists(f) and os.path.exists(raw)) or not eid.isdigit():
            continue
        if ev.segment_of(eid) != "cs2":
            continue
        df = pd.read_excel(f, sheet_name=f"EVP_Summary_{eid}")
        top_file = float(df.sort_values("evp_score", ascending=False)["evp_score"].iloc[0])
        with contextlib.redirect_stdout(io.StringIO()):
            sm, _b, _m, _d = evp_exp.run_experiment(raw, None, None,
                                                    cfg=evp_exp.cfg_for("cs2"), save=False)
        top_calc = float(sm["total_score"].iloc[0])
        with contextlib.redirect_stdout(io.StringIO()):
            sm_pure, _b, _m, _d = evp_exp.run_experiment(raw, None, None,
                                                         cfg=evp_exp.EVP_CONFIG, save=False)
        top_pure = float(sm_pure["total_score"].iloc[0])
        print(f"[复核②] CS2 交付物 {eid}: 文件顶部 evp_score={top_file:.4f}  "
              f"机制-on 直算={top_calc:.4f} (差 {abs(top_file-top_calc):.6f})  "
              f"机制-off 直算={top_pure:.4f}")
        mech = abs(top_file - top_calc) < 1e-3
        print(f"[复核②] {'✔ 交付物 = 机制-on 口径' if mech else '✘ 交付物与机制-on 口径不一致'}"
              f"  (机制使该选手 {'变动' if abs(top_calc-top_pure) > 1e-9 else '未变动'})")
        return mech
    print("[复核②] 未找到可对拍的 CS2 交付物")
    return None


def main():
    spec = importlib.util.spec_from_file_location("hltv_evp", os.path.join(ROOT, "hltv evp.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hltv_evp"] = mod
    spec.loader.exec_module(mod)
    print(f"[regen] hltv evp.py 载入: WRITE_EVENTS={mod.WRITE_EVENTS}  事件源 {len(mod.event_urls)} 个",
          flush=True)

    stats_before = json.load(open(STATS)) if os.path.exists(STATS) else {}
    before = snapshot()
    print(f"[regen] 快照: {len(before)} 个文件", flush=True)

    t0 = time.time()
    ok, _, _ = mod.run_step2_calculate_global_stats()
    print(f"\n[regen] Step 2 {'成功' if ok else '失败'} ({time.time()-t0:.0f}s)", flush=True)
    if not ok:
        return 1

    t1 = time.time()
    mod.run_step3_calculate_evp_pivot()
    print(f"\n[regen] Step 3 完成 ({time.time()-t1:.0f}s)", flush=True)

    stats_after = json.load(open(STATS)) if os.path.exists(STATS) else {}
    after = snapshot()

    changed = sorted(p for p in after if before.get(p) != after[p])
    new = sorted(p for p in after if p not in before)
    print("\n" + "=" * 90)
    print(f"[复核①] 变更 {len(changed)} 个 / 新增 {len(new)} 个 / 未变 "
          f"{len([p for p in after if before.get(p) == after[p]])} 个")
    bad = [(p, _seg_of_path(p)) for p in changed + new
           if _seg_of_path(p) is not None and _seg_of_path(p) != "cs2"]
    print(f"[复核①] 非 CS2 段却变更/新增: {bad if bad else '无 ✔ (CS:GO 交付物零触碰)'}")
    chg_cs2 = [p for p in changed if _seg_of_path(p) == "cs2"]
    print(f"[复核①] CS2 交付物已重生成: {len(chg_cs2)} 个")
    for p in changed:
        if _seg_of_path(p) is None:
            print(f"          全局文件变更: {p}")
    dm = stats_after.get("global_mean_performance_score")
    ds = stats_after.get("global_std_dev_performance_score")
    print(f"[复核①] global_stats: mean {stats_before.get('global_mean_performance_score'):.4f} → {dm:.4f}   "
          f"std {stats_before.get('global_std_dev_performance_score'):.4f} → {ds:.4f}")

    verify_content()
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
