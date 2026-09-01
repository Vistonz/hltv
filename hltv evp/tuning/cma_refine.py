"""从给定解出发的局部精调 CMA (窄空间 + 小步长).

用法: .venv/bin/python cma_refine.py <best.json> [MAXITER=30] [POPSIZE=15] [SEED]

设计 (与 search_cma.py 的区别):
  - x0 = 外部解 (如 seed50) 的参数, 而非生产定案;
  - 空间 = 每维 x0×(0.7, 1.3) (±30% 局部邻域), 全部参数统一, 无 WIDE 宽维;
  - sigma0 = 0.1 (初始单维波动 ≈ 0.1×0.6 = ±6% 参数值);
  - 30 代 × 15 ≈ 450 evals, 只在峰顶附近打磨, 不重新全局搜索;
  - 起点 obj 从 best.json 读, 打印 Δ 相对起点.
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

PATHS = [
    "ABS_WEIGHT", "REL_WEIGHT", "ABS_SCALE", "REL_SCALE", "GAMMA_ABS", "GAMMA_REL",
    "WIN_MULT", "LOSE_MULT", "BO_LOSS_FACTOR", "BO_LOSS_FACTOR_NORMAL",
    "MAP_SOFT_CAP", "MAP_HARD_MAX", "PO_SOFT_MULT", "PO_HARD_MULT", "GF_SOFT_MULT", "GF_HARD_MULT",
    "CAP_BO1", "CAP_BO3", "CAP_BO5", "GROUP_MULT", "OVER_CAP_SLOPE", "GROUP_OVER_CAP_SLOPE",
    "GROUP_OVER_CAP_SLOPE_NORMAL", "SOFT_LAND_SPREAD", "SATURATE_TAU", "SATURATE_R0", "SATURATE_FLAT",
    "EXEMPT_COMP", "CAP_GF", "NO_GROUP_MULT", "LEN_PENALTY", "ESL_GSL_FACTOR",
    "GROUP_CAP_EXEMPT.soft", "GROUP_CAP_EXEMPT.xmax", "GROUP_CAP_EXEMPT.slope",
    "GROUP_CAP_NORMAL.soft", "GROUP_CAP_NORMAL.xmax", "GROUP_CAP_NORMAL.slope",
    "PLAYOFF_CAP_EXEMPT.soft", "PLAYOFF_CAP_EXEMPT.xmax", "PLAYOFF_CAP_NORMAL.soft", "PLAYOFF_CAP_NORMAL.xmax",
]

LO_MUL, HI_MUL = 0.7, 1.3  # 局部邻域: 每维 ±30%

_G = {}


def _init_worker():
    import sys
    import os
    sys.stdout = open(os.devnull, "w")
    import eval_full as ef
    _G["official"] = ef.load_official()
    _G["ordered"] = ef.load_ordered()
    _G["cache"] = ef.load_cache(_G["official"])
    _G["slug2nick"] = ef.load_slug2nick()
    _G["discard"] = ef.DISCARD_ORDERED


def get_nested(cfg, path):
    node = cfg
    for k in path.split("."):
        node = node[k]
    return node


def set_nested(cfg, path, val):
    keys = path.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = val


def build_space(x0_cfg):
    space = []
    for p in PATHS:
        cur = get_nested(x0_cfg, p)
        space.append((p, cur * LO_MUL, cur * HI_MUL))
    return space


def to_unit(v, lo, hi):
    return (v - lo) / (hi - lo)


def to_real(u, lo, hi):
    u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
    return lo + u * (hi - lo)


def unit_to_cfg(uvec, space):
    cfg = copy.deepcopy(evp_exp.EVP_CONFIG)
    for (path, lo, hi), u in zip(space, uvec):
        set_nested(cfg, path, to_real(float(u), lo, hi))
    return cfg


def eval_one(cfg):
    import eval_full as ef
    r = ef.eval_cfg(cfg, _G["cache"], _G["official"], _G["ordered"],
                    _G["slug2nick"], discard_ordered=_G["discard"])
    return (r["obj"], r["ordered"], r["in_topn"], r["mvp_ok"], r["ord_hit"], r["ord_tot"])


def main():
    src = sys.argv[1]
    maxiter = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    popsize = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 60

    base = json.load(open(src))
    x0_cfg = copy.deepcopy(evp_exp.EVP_CONFIG)
    for p, v in base["params"].items():
        set_nested(x0_cfg, p, v)
    start_obj = base.get("obj", float("nan"))

    space = build_space(x0_cfg)
    x0 = [0.5] * len(space)  # 空间以 x0 为中心 → 中心向量
    sigma0 = 0.1
    print(f"精调 CMA: {len(space)} 维 × ±30% 邻域, sigma0={sigma0}, "
          f"popsize={popsize} maxiter={maxiter} seed={seed}", flush=True)
    print(f"起点 = {src} obj={start_obj:.4f}", flush=True)

    opts = {
        "popsize": popsize, "bounds": [-0.15, 1.15], "maxiter": maxiter,
        "verbose": -1, "seed": seed, "CMA_diagonal": True, "CMA_on": True,
    }
    es = cma.CMAEvolutionStrategy(x0, sigma0, opts)
    t0 = time.time()
    evals = 0
    gen = 0
    best_obj, best_cfg, best_info = -1e9, None, None
    restart_n = 0
    log = []

    def save_best():
        if best_cfg is None:
            return
        params = {p: get_nested(best_cfg, p) for p, lo, hi in space}
        tmp = f"{OUT}/cma_refine_best.json.tmp"
        with open(tmp, "w") as f:
            json.dump({"obj": best_obj, "delta": best_obj - start_obj,
                       "evals": evals, "gen": gen, "params": params}, f, indent=1)
        os.replace(tmp, f"{OUT}/cma_refine_best.json")

    with ProcessPoolExecutor(max_workers=max(8, popsize), initializer=_init_worker) as ex:
        while evals < 900 and gen < maxiter * (restart_n + 1):
            try:
                X = es.ask()
            except ValueError as e:
                print(f"  ↳ ask 边界异常, 重置 mean: {e}", flush=True)
                es = cma.CMAEvolutionStrategy(
                    [0.5] * len(space), sigma0,
                    {**opts, "popsize": popsize * 2 ** restart_n, "seed": seed + restart_n})
                continue
            cfgs = [unit_to_cfg(x, space) for x in X]
            results = list(ex.map(eval_one, cfgs))
            fitness = [-r[0] for r in results]
            es.tell(X, fitness)
            evals += len(X)
            gen += 1
            for x, r in zip(X, results):
                if r[0] > best_obj:
                    best_obj = r[0]
                    best_cfg = copy.deepcopy(unit_to_cfg(x, space))
                    best_info = r
                    save_best()
            line = (f"[gen{gen}] evals={evals} {time.time()-t0:.0f}s "
                    f"gen_best={max(r[0] for r in results):.3f} all_best={best_obj:.3f}")
            print(line, flush=True)
            log.append(line)
            if es.stop():
                reason = es.stop()
                print(f"  ↳ restart #{restart_n}: {list(reason.keys())}", flush=True)
                restart_n += 1
                if restart_n > 2:
                    break
                mean = [max(0.0, min(1.0, m)) for m in es.mean]
                es = cma.CMAEvolutionStrategy(mean, es.sigma * 1.0,
                                              {**opts, "popsize": popsize * 2 ** restart_n,
                                               "seed": seed + restart_n})

    print(f"\n总耗时 {round(time.time()-t0,1)}s — {evals} evals, {gen} 代")
    print(f"起点 obj = {start_obj:.4f} → 精调后 best = {best_obj:.4f} (Δ={best_obj-start_obj:+.4f})")
    if best_cfg is not None:
        for p, lo, hi in space:
            cur = get_nested(x0_cfg, p)
            v = get_nested(best_cfg, p)
            if abs(v / cur - 1.0) > 0.01:
                print(f"  {p:<28} {v:>10.5f}  (x{v/cur:.4f})")
    with open(f"{OUT}/cma_refine_best.json", "w") as f:
        params = {} if best_cfg is None else {
            p: get_nested(best_cfg, p) for p, lo, hi in space}
        json.dump({"obj": best_obj, "delta": best_obj - start_obj,
                   "evals": evals, "gen": gen, "params": params}, f, indent=1)
    with open(f"{OUT}/cma_refine_log.txt", "w") as f:
        f.write("\n".join(log) + "\n")
    print("→ 已写入 cma_refine_best.json / cma_refine_log.txt")


if __name__ == "__main__":
    main()
