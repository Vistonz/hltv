"""CS2 mapstats 全候选轴回归搜索 (2026-09-09 用户指令 "CS2 添加所有这些参数跑回归").

旧 2D 网格只拟合了 kprw_e/dpr (obj 161.2287→162.3726). 本脚本把全部 9 个候选轴
(kprw_e / kprw_avg / kpr / kast / mk / adr / dpr / swing_sum / swing_avg) 一起放开,
在同一 objective 上联合拟合 (真·全参数回归, 不再预筛丢弃轴). 权重带符号, CMA 决定.

架构: 两套分拆后, 42 核心参数留在 EVP_CONFIG (CS:GO 冻结源) 不动;
搜索空间 = CS2_OVERRIDES 的 9 个机制键, 逐点经 eval_cfg(cs2_overrides=...) 只评估
CS2 子集 (~64 事件) → CS:GO 恒常数, 不参与, 加速且零漂移风险.

量纲: 事件内 z 标准化 → 权重 ≈ 分数. bounds ±0.6 (生产 kprw_e=0.19/dpr=-0.04 居中).
x0 = 生产定案 (其余轴 0). IPOP restart 防平台卡死.
best 即时落盘: cs2axes_best.json (含全轴权重 + 分段 obj).
用法: .venv/bin/python tuning/search_cs2_axes_cma.py [MAXITER=40] [POPSIZE=12] [SEED=42]
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

OUT = "/home/hongbin/.claude/jobs/75f6c437/tmp"
# 轴顺序 (与 CS2_OVERRIDES/_CS2_AXES 一致). 键 = CS2_<AXIS>_W.
AXES = ["KPRW_E", "DPR", "KPRW_AVG", "KPR", "KAST", "MK", "ADR", "SWING_SUM", "SWING_AVG"]
LO, HI = -0.6, 0.6

# x0 = 生产定案 (迁移): kprw_e 0.19, dpr -0.04, 其余 0
PROD = {"KPRW_E": 0.19, "DPR": -0.04}

_G = {}


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
    _G["cache_cs2"] = {eid: df for eid, df in _G["cache"].items()
                       if _ef.segment_of(eid) == "cs2"}


def to_unit(w):
    return (w - LO) / (HI - LO)


def to_real(u):
    u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
    return LO + u * (HI - LO)


def vec_to_overrides(uvec):
    return {f"CS2_{ax}_W": to_real(float(u)) for ax, u in zip(AXES, uvec)}


def eval_one(uvec):
    """返回 (obj, ordered, in_topn, mvp, mismatch, n_ev)."""
    import eval_full as _ef
    ov = vec_to_overrides(uvec)
    r = _ef.eval_cfg(evp_exp.EVP_CONFIG, _G["cache_cs2"], _G["official"], _G["ordered"],
                     _G["slug2nick"], discard_ordered=_G["discard"], cs2_overrides=ov)
    return (r["obj"], r["ordered"], r["in_topn"], r["mvp_ok"], r["mismatch"], r["n_ev"])


def save_best(best_obj, uvec, r, tag):
    weights = {ax: to_real(float(u)) for ax, u in zip(AXES, uvec)}
    tmp = f"{OUT}/cs2axes_best.json.tmp"
    with open(tmp, "w") as f:
        json.dump({"obj": best_obj, "tag": tag, "weights": weights,
                   "ordered": r[1], "in_topn": r[2], "mvp_ok": r[3],
                   "mismatch": r[4], "n_ev": r[5]}, f, indent=1)
    os.replace(tmp, f"{OUT}/cs2axes_best.json")


def run_cma(seed, x0, popsize, maxiter, tag, workers):
    opts = {"popsize": popsize, "bounds": [-0.15, 1.15], "maxiter": maxiter,
            "verbose": -1, "seed": seed, "CMA_diagonal": True, "CMA_on": True}
    es = cma.CMAEvolutionStrategy(x0, 0.12, opts)
    restart_n = 0
    best_obj, best_x, best_r = -1e9, None, None
    evals = gen = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        while gen < maxiter * (restart_n + 1):
            try:
                X = es.ask()
            except ValueError as e:
                print(f"  ↳ ask 边界异常, 重置 mean: {e}", flush=True)
                es = cma.CMAEvolutionStrategy([0.5] * len(X[0] if len(X) else x0), 0.12,
                                              {**opts, "popsize": popsize * 2 ** restart_n,
                                               "seed": seed + restart_n})
                continue
            results = list(ex.map(eval_one, X))
            es.tell(X, [-r[0] for r in results])
            evals += len(X)
            gen += 1
            for x, r in zip(X, results):
                if r[0] > best_obj:
                    best_obj, best_x, best_r = r[0], list(x), r
                    save_best(best_obj, best_x, best_r, f"{tag} g{gen}")
            print(f"  [gen{gen}] evals={evals} {time.time()-t0:.0f}s "
                  f"gen_best={max(r[0] for r in results):.4f} all_best={best_obj:.4f}",
                  flush=True)
            if es.stop():
                print(f"  ↳ restart #{restart_n}: {list(es.stop().keys())}", flush=True)
                restart_n += 1
                if restart_n > 3:
                    break
                mean = [max(0.0, min(1.0, m)) for m in es.mean]
                es = cma.CMAEvolutionStrategy(mean, es.sigma,
                                              {**opts, "popsize": popsize * 2 ** restart_n,
                                               "seed": seed + restart_n})
    print(f"  [{tag}] 完成: {evals} evals/{gen} gen, best obj={best_obj:.4f}, "
          f"耗时 {time.time()-t0:.0f}s", flush=True)
    return best_obj, best_x, best_r


def main():
    maxiter = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    popsize = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    ncore = os.cpu_count() or 8
    workers = max(8, min(ncore - 1, popsize))

    x0 = [to_unit(PROD.get(ax, 0.0)) for ax in AXES]
    w0 = {f"CS2_{ax}_W": PROD.get(ax, 0.0) for ax in AXES}
    with ProcessPoolExecutor(max_workers=1, initializer=_init_worker) as ex:
        base_r = ex.submit(eval_one, [to_unit(PROD.get(a, 0.0)) for a in AXES]).result()
    print(f"锚点: 生产定案 (kprw_e 0.19, dpr -0.04, 余 0) → CS2-only obj={base_r[0]:.4f} "
          f"(期望 184.5893)", flush=True)

    t_all = time.time()
    best_obj, best_x, best_r = run_cma(seed, x0, popsize, maxiter, "9轴CMA", workers)
    print(f"\n{'='*72}")
    print(f"全候选轴 CMA best obj(CS2-only) = {best_obj:.4f} "
          f"(起点 {base_r[0]:.4f}, Δ={best_obj-base_r[0]:+.4f})")
    if best_x is not None:
        print("拟合权重 (带符号):")
        for ax, u in zip(AXES, best_x):
            w = to_real(float(u))
            mark = "" if abs(w) < 1e-9 else f"   {'★' if abs(w) > 0.02 else '·'}"
            print(f"  CS2_{ax}_W = {w:+.4f}{mark}")
        save_best(best_obj, best_x, best_r, "final")
    print(f"总耗时 {(time.time()-t_all)/60:.1f}min → cs2axes_best.json")


if __name__ == "__main__":
    main()
