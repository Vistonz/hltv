"""重生成交付物 (CS:GO + CS2 全段) — 解冻写回后用.

背景: 2026-09-10 在 W_IN=0.45 口径下局部精调 CMA 得到 obj=115.4474 (锚点 114.8402,
+0.6072), 42 核心参数全部写回 EVP_CONFIG。42 参数为 CS:GO/CS2 共用 → **CS:GO 冻结
随之解除**, 190 个 CS:GO 交付物与 65 个 CS2 交付物全部需按新参数重生成。

流程 (只跑 Step 2 + Step 3, 不触碰 Step 0/1/1.5):
  1. 快照: 全部 event_*_evp_summary.xlsx + global_stats.json + 透视表 的 md5。
  2. Step 2: 重算全局 mean/std → global_stats.json。
  3. Step 3: 全赛事计算并写出交付物 (WRITE_EVENTS=all) + 重写透视表。
  4. 复核: ① 逐段统计变更文件数 (两段都应大范围变化); ② 抽两段各一个赛事, 把交付物
     顶部选手 evp_score 与 run_experiment(cfg_for(seg)) 直算对拍。

用法: .venv/bin/python tuning/regen_all_deliverables.py [csgo|cs2|all]
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

SEG_ARG = (sys.argv[1] if len(sys.argv) > 1 else "all").strip().lower()
os.environ["EVP_WRITE_EVENTS"] = SEG_ARG

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
    if not p.startswith(DB):
        return None
    eid = os.path.basename(os.path.dirname(p))
    return ev.segment_of(eid) if eid.isdigit() else None


def verify_content(seg):
    """抽样对拍: 某交付物顶部选手 evp_score ?= run_experiment(cfg_for(seg)) 顶部 total_score."""
    import contextlib
    import io
    for eid in sorted(os.listdir(DB)):
        f = os.path.join(DB, eid, f"event_{eid}_evp_summary.xlsx")
        raw = os.path.join(DB, eid, f"raw_event_{eid}_data.xlsx")
        if not (os.path.exists(f) and os.path.exists(raw)) or not eid.isdigit():
            continue
        if ev.segment_of(eid) != seg:
            continue
        df = pd.read_excel(f, sheet_name=f"EVP_Summary_{eid}")
        top_file = float(df.sort_values("evp_score", ascending=False)["evp_score"].iloc[0])
        with contextlib.redirect_stdout(io.StringIO()):
            sm, _b, _m, _d = evp_exp.run_experiment(raw, None, None,
                                                    cfg=evp_exp.cfg_for(seg), save=False)
        top_calc = float(sm["total_score"].iloc[0])
        ok = abs(top_file - top_calc) < 1e-3
        print(f"[复核②/{seg}] {eid}: 文件 evp_score={top_file:.4f}  直算={top_calc:.4f}  "
              f"差={abs(top_file-top_calc):.6f}  {'✔ 一致' if ok else '✘ 不一致'}")
        return ok
    print(f"[复核②/{seg}] 未找到可对拍的交付物")
    return None


def main():
    spec = importlib.util.spec_from_file_location("hltv_evp", os.path.join(ROOT, "hltv evp.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hltv_evp"] = mod
    spec.loader.exec_module(mod)
    print(f"[regen] hltv evp.py 载入: WRITE_EVENTS={mod.WRITE_EVENTS}", flush=True)

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
    unchanged = [p for p in after if before.get(p) == after[p]]
    print("\n" + "=" * 90)
    print(f"[复核①] 变更 {len(changed)} 个 / 新增 {len(new)} 个 / 未变 {len(unchanged)} 个")
    for seg in ("csgo", "cs2"):
        chg = [p for p in changed if _seg_of_path(p) == seg]
        unch = [p for p in unchanged if _seg_of_path(p) == seg]
        print(f"[复核①] {seg}: 已重生成 {len(chg)} 个, 未变 {len(unch)} 个")
    for p in changed + new:
        if _seg_of_path(p) is None:
            print(f"          全局文件: {p}")
    dm = stats_after.get("global_mean_performance_score")
    ds = stats_after.get("global_std_dev_performance_score")
    print(f"[复核①] global_stats: mean {stats_before.get('global_mean_performance_score'):.4f} → {dm:.4f}   "
          f"std {stats_before.get('global_std_dev_performance_score'):.4f} → {ds:.4f}")

    for seg in ("csgo", "cs2"):
        verify_content(seg)
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
