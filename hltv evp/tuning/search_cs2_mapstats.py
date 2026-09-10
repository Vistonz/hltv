"""CS2 mapstats 机制搜索 (2026-09-09) — 2 维, 42 核心参数冻结.

⚠ 弃用 (2026-09-10): 机制键已从 EVP_CONFIG 迁到 CS2_OVERRIDES, 且本文件的
CS2_CLUTCH_W/CS2_DPR_W 键名已改 (→CS2_KPRW_E_W, dpr 带符号)。历史存档勿重跑。
全候选轴回归改用 tuning/search_cs2_axes_cma.py; 采纳判定用 tuning/decision_cs2_axes.py
+ tuning/robust_cs2_axes.py (样本外检验判真伪)。

(原 docstring 存档如下)

预检定案轴 (v3 score-matched 配对 + v4 共线甄别, 见 EVP_CONFIG 注释):
  CS2_CLUTCH_W (+z kprw_e)  /  CS2_DPR_W (+z −dpr)  均 0 = 精确复现两段基线 obj=161.2287.

搜索空间: 仅这 2 个机制键. 42 核心参数保持 EVP_CONFIG 原样 → CS:GO 恒为常数
(机制结构上不触发 CS:GO) → 最大化 CS2-only obj ≡ 最大化全量 obj.
objective 用 CS2 评估子集 (~64 事件) 提速 ~4×; 终值用全量 eval_cfg 复核.

两段粗扫 + 局部精扫: 无 CMA 维度需求, 网格更透明. best 即时落盘.
用法: .venv/bin/python tuning/search_cs2_mapstats.py [GRID1] [GRID2]
"""
import os
import sys
import time
import json
import copy
from concurrent.futures import ProcessPoolExecutor

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ev  # noqa: E402

OUT = "/home/hongbin/.claude/jobs/75f6c437/tmp"
KEYS = ["CS2_CLUTCH_W", "CS2_DPR_W"]


def _init_worker():
    import sys as _s
    import os as _o
    _s.stdout = open(_o.devnull, "w")
    import eval_full as _ef
    _G["official"] = _ef.load_official()
    _G["ordered"] = _ef.load_ordered()
    _G["cache"] = _ef.load_cache(_G["official"])
    _G["slug2nick"] = _ef.load_slug2nick()
    _G["discard"] = _ef.DISCARD_ORDERED
    # CS2 评估子集 (机制只可能改 CS2; CS:GO 在 objective 中恒为常数)
    _G["cache_cs2"] = {eid: df for eid, df in _G["cache"].items()
                       if _ef.segment_of(eid) == "cs2"}


_G = {}


def eval_one(pair):
    """pair = (CS2_CLUTCH_W, CS2_DPR_W). 返回 CS2-only obj."""
    import eval_full as _ef
    cfg = copy.deepcopy(evp_exp.EVP_CONFIG)
    cfg["CS2_CLUTCH_W"], cfg["CS2_DPR_W"] = pair
    r = _ef.eval_cfg(cfg, _G["cache_cs2"], _G["official"], _G["ordered"],
                     _G["slug2nick"], discard_ordered=_G["discard"])
    return (r["obj"], r["ordered"], r["in_topn"], r["mvp_ok"], r["mismatch"],
            r["ord_hit"], r["ord_tot"])


def grid_scan(vals_a, vals_b, label):
    print(f"\n[{label}] 粗扫 {len(vals_a)}×{len(vals_b)} = {len(vals_a)*len(vals_b)} 点", flush=True)
    t0 = time.time()
    ncore = os.cpu_count() or 8
    workers = max(8, min(ncore - 1, 14))
    results = {}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        futs = {ex.submit(eval_one, (a, b)): (a, b)
                for a in vals_a for b in vals_b}
        done = 0
        best = (-1e9, None, None)
        for fut in futs:
            r = fut.result()
            pair = futs[fut]
            results[pair] = r
            done += 1
            if r[0] > best[0]:
                best = (r[0], pair, r)
                save_best(best, label)
            if done % 12 == 0 or done == len(futs):
                print(f"  {done}/{len(futs)}  best obj={best[0]:.4f} @ {best[1]} "
                      f"({time.time()-t0:.0f}s)", flush=True)
    return results


def save_best(best, tag):
    obj, pair, r = best
    tmp = f"{OUT}/cs2mapstats_best.json.tmp"
    with open(tmp, "w") as f:
        json.dump({"obj": obj, "pair": list(pair), "tag": tag,
                   "ordered": r[1], "in_topn": r[2], "mvp_ok": r[3],
                   "mismatch": r[4]}, f, indent=1)
    os.replace(tmp, f"{OUT}/cs2mapstats_best.json")


def main():
    # 默认: [0,0.4] step 0.05 粗扫 → ±0.08 step 0.005 精扫
    coarse = "0.0,0.05,0.1,0.15,0.2,0.25,0.3,0.35,0.4"
    g1 = sys.argv[1] if len(sys.argv) > 1 else coarse
    g2 = sys.argv[2] if len(sys.argv) > 2 else g1
    vals_a = [float(x) for x in g1.split(",")]
    vals_b = [float(x) for x in g2.split(",")]

    t0 = time.time()
    results = grid_scan(vals_a, vals_b, "2D-grid")
    # 基线 & 粗扫 argmax
    base = results.get((0.0, 0.0))
    best = max(results, key=lambda p: results[p][0])
    best_obj = results[best][0]
    if base:
        print(f"\n基线(0,0) CS2-only obj = {base[0]:.4f}")
    print(f"粗扫 best obj={best_obj:.4f} @ CLUTCH={best[0]} DPR={best[1]} "
          f"(Δvs基线 {best_obj - (base[0] if base else 0):+.4f})", flush=True)
    # 局部精扫 (粗扫 argmax ±0.08, step 0.01)
    a, b = best
    fa = [round(max(0.0, a + i * 0.01), 3) for i in range(-8, 9)]
    fb = [round(max(0.0, b + i * 0.01), 3) for i in range(-8, 9)]
    print(f"局部精扫 {len(fa)}×{len(fb)} 窗口 CLUTCH∈[{fa[0]},{fa[-1]}] DPR∈[{fb[0]},{fb[-1]}]", flush=True)
    res2 = grid_scan(fa, fb, "refine")
    final = max(res2, key=lambda p: res2[p][0])
    print(f"\n{'='*70}\n最终: obj(CS2-only)={res2[final][0]:.4f} @ CLUTCH={final[0]} DPR={final[1]} "
          f"Δvs基线={res2[final][0]-(base[0] if base else 0):+.4f} 总耗时 {time.time()-t0:.0f}s")
    save_best((res2[final][0], final, res2[final]), "final")
    print("→ cs2mapstats_best.json")


if __name__ == "__main__":
    main()
