"""CS2 全轴回归 — 样本外稳定性检验 (Task #96 采纳闸门核心).

9 轴 CMA in-sample CS2-only obj 186.74 (全量 obj 163.80, Δ+1.43 vs 生产), 但权重含
物理上不可能的负 KAST/ADR/MK → 高过拟合嫌疑. 本脚本用**分割样本外**判真伪:

  - CS2 评估事件按 eid 排序交替劈成 A/B 两半 (~32/32).
  - 半边 A 上 CMA 拟合 9 轴 (起点=生产), 在另一半 B 上评估 obj → Δ vs 生产在同半的 obj.
    out-of-sample Δ > 0 且两方向一致 → 轴有真实增量, 可采纳 (再全量重拟一次);
    ≈0 或负 → 纯过拟合, 诚实停在生产 2 轴.
  - in-sample Δ (拟合半边自身) 一并打印作对照 (应远高于 OOS = 过拟合特征).

用法: .venv/bin/python tuning/robust_cs2_axes.py [MAXITER=25] [POPSIZE=12] [SEED=42]
"""
import copy
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import cma

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402

AXES = ["KPRW_E", "DPR", "KPRW_AVG", "KPR", "KAST", "MK", "ADR", "SWING_SUM", "SWING_AVG"]
LO, HI = -0.6, 0.6
PROD = {"KPRW_E": 0.19, "DPR": -0.04}
_G = {}


def _init_worker(subset):
    import sys as _s
    import os as _o
    _s.stdout = open(_o.devnull, "w")
    import eval_full as _ef
    _G["official"] = _ef.load_official()
    _G["ordered"] = _ef.load_ordered()
    _G["cache"] = _ef.load_cache(_G["official"])
    _G["slug2nick"] = _ef.load_slug2nick()
    _G["discard"] = _ef.DISCARD_ORDERED
    _G["cache_cs2"] = {eid: df for eid, df in _G["cache"].items()
                       if _ef.segment_of(eid) == "cs2" and eid in subset}


def _to_real(u):
    u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
    return LO + u * (HI - LO)


def eval_one(uvec):
    import eval_full as _ef
    ov = {f"CS2_{ax}_W": _to_real(float(u)) for ax, u in zip(AXES, uvec)}
    r = _ef.eval_cfg(evp_exp.EVP_CONFIG, _G["cache_cs2"], _G["official"], _G["ordered"],
                     _G["slug2nick"], discard_ordered=_G["discard"], cs2_overrides=ov)
    return r["obj"]


def fit(subset, x0u, seed, maxiter, popsize):
    """在 subset 上 CMA 拟合 → 返回 (best_obj_in, best_uvec)."""
    opts = {"popsize": popsize, "bounds": [-0.15, 1.15], "maxiter": maxiter,
            "verbose": -1, "seed": seed, "CMA_diagonal": True, "CMA_on": True}
    es = cma.CMAEvolutionStrategy(x0u, 0.15, opts)
    best = (-1e9, None)
    with ProcessPoolExecutor(max_workers=popsize,
                             initializer=_init_worker, initargs=(subset,)) as ex:
        for _ in range(maxiter):
            X = es.ask()
            vals = list(ex.map(eval_one, X))
            es.tell(X, [-v for v in vals])
            for x, v in zip(X, vals):
                if v > best[0]:
                    best = (v, list(x))
            if es.stop():
                break
    return best


def obj_of(subset, ov):
    """单进程静音评估 subset 上给定覆写的 obj."""
    import io
    from contextlib import redirect_stdout
    import eval_full as _ef
    official = _ef.load_official()
    ordered = _ef.load_ordered()
    cache = _ef.load_cache(official)
    slug2nick = _ef.load_slug2nick()
    cache_sub = {eid: df for eid, df in cache.items()
                 if _ef.segment_of(eid) == "cs2" and eid in subset}
    with redirect_stdout(io.StringIO()):
        r = _ef.eval_cfg(evp_exp.EVP_CONFIG, cache_sub, official, ordered, slug2nick,
                         discard_ordered=_ef.DISCARD_ORDERED, cs2_overrides=ov)
    return r["obj"]


def main():
    maxiter = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    popsize = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42

    # CS2 评估事件劈两半 (eid 交替) — 只在"有 raw 的评估事件"上劈, 与 objective 口径一致.
    # 旧版误在 official 全集 (133, 含无 raw 者) 上劈 → 两折实际可用赛事不均. 2026-09-10 修正.
    import eval_full as _ef
    official = _ef.load_official()
    cache = _ef.load_cache(official)
    cs2 = sorted(eid for eid in cache if _ef.segment_of(eid) == "cs2")
    A = {eid for i, eid in enumerate(cs2) if i % 2 == 0}
    B = {eid for i, eid in enumerate(cs2) if i % 2 == 1}
    print(f"CS2 评估事件 {len(cs2)} → 折A {len(A)} / 折B {len(B)}", flush=True)

    x0 = [LO + (HI - LO) * (0.5 + 0.0) for _ in AXES]
    # 生产权重 → 单位坐标
    def to_unit(w):
        return (w - LO) / (HI - LO)
    x0u = [to_unit(PROD.get(ax, 0.0)) for ax in AXES]

    pA = obj_of(A, None)
    pB = obj_of(B, None)
    print(f"生产 obj: 折A={pA:.4f}  折B={pB:.4f}", flush=True)

    # 折A 拟合 → 折B 测 OOS; 折B 拟合 → 折A 测 OOS
    for fit_name, fit_sub, oos_sub, p_oos in (("A→B", A, B, pB), ("B→A", B, A, pA)):
        t0 = time.time()
        obj_in, best_u = fit(fit_sub, x0u, seed, maxiter, popsize)
        w = {ax: _to_real(float(u)) for ax, u in zip(AXES, best_u)}
        ov = {f"CS2_{ax}_W": w[ax] for ax in AXES}
        oos = obj_of(oos_sub, ov)
        delta = oos - p_oos
        verdict = "✔ 泛化" if delta > 0.3 else ("≈0 无泛化" if delta > -0.3 else "✘ 伤害样本外")
        print(f"\n[{fit_name}] 拟合半边 in-sample obj={obj_in:.4f}  "
              f"样本外 Δ={delta:+.4f}  [{verdict}]  ({time.time()-t0:.0f}s)", flush=True)
        print("  拟合权重:", "  ".join(f"{ax}={w[ax]:+.3f}" for ax in AXES))
        seed += 1


if __name__ == "__main__":
    main()
