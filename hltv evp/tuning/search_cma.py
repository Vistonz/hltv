"""CMA-ES 全局搜索 (42 维参数相关性协同).

背景: 粗扫/随机/TPE 均未用 CMA-ES. 其强项是建模参数间协方差 (相关性),
可能找到随机采样测不出的多参数协同峰. 目标函数 obj 离散 (平台多), 用 IPOP
restart 防过早收敛.

设计:
  - 搜索空间归一化到 [0,1]^42 (单位立方体), 规避各维量纲差异; sigma0=0.15.
  - x0 = 当前 EVP_CONFIG (起点 obj 动态重算, 不硬编码 —— base.json 里的 obj 可能是旧权重口径).
  - 每代 popsize 个点并行评估 (ProcessPoolExecutor), 单次全量 eval ≈43s.
  - 检测 es.stop() 时触发 IPOP restart (popsize 翻倍, 从 es.mean 重新出发).
  - cma 最小化 → fitness = -obj.
  - 每个评估点把 (ord/in/mvp/mis, u向量) 追加到 TAG_archive.jsonl; obj 对权重线性
    → 事后换 W_IN 可直接重排档案, 不必重跑. 空间定义存 TAG_space.json (u→参数可解码).

用法: .venv/bin/python tuning/search_cma.py [MAX_EVALS] [POPSIZE] [MAXITER] [SEED] [BASE_JSON]
       BASE_JSON: 可选 — 用它作为搜索锚点 (不写生产), 默认用生产 EVP_CONFIG.
环境: EVP_CMA_OUT 输出目录 / EVP_CMA_TAG 文件名前缀 / EVP_W_IN objective 权重.
"""
import os
import sys
import time
import copy
import json
import cma
from concurrent.futures import ProcessPoolExecutor

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402

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

WIDE = {
    "CAP_BO1": (0.5, 4.5),
    "LEN_PENALTY": (0.002, 0.04),
    "NO_GROUP_MULT": (0.3, 1.5),
    "CAP_BO3": (0.4, 3.0),
    "CAP_BO5": (0.4, 3.0),
}
LO_MUL, HI_MUL = 0.4, 2.5

# 输出目录可用 EVP_CMA_OUT 覆盖 → 换 objective 重跑时不覆盖历史存档.
OUT = os.environ.get("EVP_CMA_OUT", "/home/hongbin/.claude/jobs/75f6c437/tmp")
os.makedirs(OUT, exist_ok=True)
TAG = os.environ.get("EVP_CMA_TAG", "cma")
BEST_JSON = os.path.join(OUT, f"{TAG}_best.json")
LOG_TXT = os.path.join(OUT, f"{TAG}_log.txt")
ARCHIVE_JSONL = os.path.join(OUT, f"{TAG}_archive.jsonl")
SPACE_JSON = os.path.join(OUT, f"{TAG}_space.json")

_G = {}


def eval_anchor(cfg):
    """单进程评估一个配置 → 完整指标 dict (用于动态锚定起点 obj).

    不要信任 base.json 里存的 obj: 它可能是在旧 objective 权重 (如 W_IN=1.0) 下算的,
    换权重后必须用当前口径重算, 否则 Δ 全是错的.
    """
    import io
    from contextlib import redirect_stdout
    import eval_full as ef
    official = ef.load_official()
    ordered = ef.load_ordered()
    cache = ef.load_cache(official)
    slug2nick = ef.load_slug2nick()
    with redirect_stdout(io.StringIO()):
        return ef.eval_cfg(cfg, cache, official, ordered, slug2nick,
                           discard_ordered=ef.DISCARD_ORDERED)


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


def build_space():
    space = []
    for p in PATHS:
        cur = get_nested(evp_exp.EVP_CONFIG, p)
        if p in WIDE:
            lo, hi = WIDE[p]
        else:
            lo, hi = cur * LO_MUL, cur * HI_MUL
        space.append((p, lo, hi))
    return space


def to_unit(v, lo, hi):
    return (v - lo) / (hi - lo)


def to_real(u, lo, hi):
    # cma 采样可能略出 [0,1], clip 保证物理范围
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
    # 返回分量而不仅是 obj: obj 对权重是线性的 (obj = 100·ord + W_IN·100·in + 40·mvp
    # − W_MIS·mis), 存下分量后可在任意 W_IN 下重排整个搜索档案, 无需重跑.
    return {"obj": r["obj"], "ord": r["ordered"], "in": r["in_topn"],
            "mvp": r["mvp_ok"], "mis": r["mismatch"],
            "ord_hit": r["ord_hit"], "ord_tot": r["ord_tot"]}


def main():
    max_evals = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    popsize = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    maxiter = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 42
    # 可选 BASE_JSON: 用外部解 (如精调峰值) 作为搜索锚点/基线, 不写生产
    # 可选 BASE_JSON: 用外部解 (如精调峰值) 作为搜索锚点/基线, 不写生产
    base_src = sys.argv[5] if len(sys.argv) > 5 else None
    if base_src:
        base = json.load(open(base_src))
        for p, v in base["params"].items():
            set_nested(evp_exp.EVP_CONFIG, p, v)
    space = build_space()
    x0 = [to_unit(get_nested(evp_exp.EVP_CONFIG, p), lo, hi) for p, lo, hi in space]
    # 起点 obj 动态重算 (当前 objective 口径) — base.json 里的 obj 可能是旧权重的
    print("评估起点配置 (动态锚定, 当前 objective 口径)...", flush=True)
    start_info = eval_anchor(copy.deepcopy(evp_exp.EVP_CONFIG))
    start_obj = start_info["obj"]
    import eval_full as _ef
    print(f"CMA-ES: {len(space)} 维 × 单位立方体, popsize={popsize} maxiter={maxiter} "
          f"max_evals={max_evals} seed={seed} anchor={base_src or '生产定案'}", flush=True)
    print(f"objective: W_IN={_ef.W_IN} (W_ORD={_ef.W_ORD} W_MVP={_ef.W_MVP} "
          f"W_MIS={_ef.W_MIS})  输出目录={OUT}", flush=True)
    print(f"起点 obj = {start_obj:.4f}  (ord={start_info['ordered']:.4f} "
          f"in={start_info['in_topn']:.4f} mvp={start_info['mvp_ok']:.4f} "
          f"mis={start_info['mismatch']:.2f}). 每代并行评估, IPOP restart 防平台卡死.",
          flush=True)

    # 档案: 本次 run 从零开始 (避免与历史混淆); 同时落盘空间定义 → u 向量可解码回参数
    open(ARCHIVE_JSONL, "w").close()
    with open(SPACE_JSON, "w") as f:
        json.dump({"win": _ef.W_IN, "w_ord": _ef.W_ORD, "w_mvp": _ef.W_MVP,
                   "w_mis": _ef.W_MIS, "out": OUT, "tag": TAG,
                   "space": [[p, lo, hi] for p, lo, hi in space],
                   "x0u": [float(v) for v in x0]}, f, indent=1)
    with open(ARCHIVE_JSONL, "a") as af:
        af.write(json.dumps({"ord": start_info["ordered"], "in": start_info["in_topn"],
                             "mvp": start_info["mvp_ok"], "mis": start_info["mismatch"],
                             "u": [round(float(v), 6) for v in x0], "anchor": True}) + "\n")

    opts = {
        "popsize": popsize, "bounds": [-0.15, 1.15], "maxiter": maxiter,
        "verbose": -1, "seed": seed, "CMA_diagonal": True, "CMA_on": True,
    }
    es = cma.CMAEvolutionStrategy(x0, 0.15, opts)
    t0 = time.time()
    evals = 0
    gen = 0
    best_obj, best_cfg, best_info = -1e9, None, None
    restart_n = 0
    log = []

    def save_best():
        """每代 best 更新后立即落盘 (含完整参数), 防进程崩溃丢失."""
        if best_cfg is None:
            return
        params = {p: get_nested(best_cfg, p) for p, lo, hi in space}
        tmp = BEST_JSON + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"obj": best_obj, "delta": best_obj - start_obj,
                       "evals": evals, "gen": gen, "params": params}, f, indent=1)
        os.replace(tmp, BEST_JSON)

    with ProcessPoolExecutor(max_workers=max(8, popsize), initializer=_init_worker) as ex:
        while evals < max_evals and gen < maxiter * (restart_n + 1):
            try:
                X = es.ask()
            except ValueError as e:
                # 边界逆变换崩溃: 重置 mean 到物理范围 [0,1] 中心再继续
                print(f"  ↳ ask 边界异常, 重置 mean: {e}", flush=True)
                es = cma.CMAEvolutionStrategy(
                    [0.5] * len(space), 0.15,
                    {**opts, "popsize": popsize * 2 ** restart_n, "seed": seed + restart_n})
                continue
            cfgs = [unit_to_cfg(x, space) for x in X]
            results = list(ex.map(eval_one, cfgs))
            fitness = [-r["obj"] for r in results]  # cma 最小化
            es.tell(X, fitness)
            evals += len(X)
            gen += 1
            # 全档案落盘 (分量 + 参数) → 换权重后可离线重排, 不必重跑 CMA
            with open(ARCHIVE_JSONL, "a") as af:
                for x, r in zip(X, results):
                    af.write(json.dumps({
                        "ord": r["ord"], "in": r["in"], "mvp": r["mvp"], "mis": r["mis"],
                        "u": [round(float(v), 6) for v in x]}) + "\n")
            # 记录本代最优
            for x, r in zip(X, results):
                if r["obj"] > best_obj:
                    best_obj = r["obj"]
                    best_cfg = copy.deepcopy(unit_to_cfg(x, space))
                    best_info = r
                    save_best()
            line = (f"[gen{gen}] evals={evals}/{max_evals} {time.time()-t0:.0f}s "
                    f"gen_best={max(r['obj'] for r in results):.3f} all_best={best_obj:.3f}")
            print(line, flush=True)
            log.append(line)
            if es.stop():
                reason = es.stop()
                print(f"  ↳ restart #{restart_n}: {list(reason.keys())}", flush=True)
                restart_n += 1
                if restart_n > 3:
                    break
                # clip mean 到物理范围 [0,1], 避免 restart 边界逆变换崩溃
                mean = [max(0.0, min(1.0, m)) for m in es.mean]
                es = cma.CMAEvolutionStrategy(mean, es.sigma * 1.0,
                                              {**opts, "popsize": popsize * 2 ** restart_n,
                                               "seed": seed + restart_n})

    print(f"\n总耗时 {round(time.time()-t0,1)}s — {evals} evals, {gen} 代")
    print(f"最佳 obj = {best_obj:.4f} (起点 {start_obj:.4f}, Δ={best_obj-start_obj:+.4f})")
    if best_cfg is not None:
        print("最佳参数 (相对当前值尺度):")
        for p, lo, hi in space:
            cur = get_nested(evp_exp.EVP_CONFIG, p)
            v = get_nested(best_cfg, p)
            if abs(v / cur - 1.0) > 0.02:
                print(f"  {p:<28} {v:>10.5f}  (x{v/cur:.3f})")
    with open(BEST_JSON, "w") as f:
        params = {} if best_cfg is None else {
            p: get_nested(best_cfg, p) for p, lo, hi in space}
        json.dump({"obj": best_obj, "delta": best_obj - start_obj,
                   "evals": evals, "gen": gen, "params": params}, f, indent=1)
    with open(LOG_TXT, "w") as f:
        f.write("\n".join(log) + "\n")
    print(f"→ 已写入 {BEST_JSON} / {LOG_TXT}")


if __name__ == "__main__":
    main()
