"""复验精调最优解, 并量化它对 CS:GO 冻结的冲击面.

回答三个问题:
  1. refine45_best.json 的 obj 能否独立复现 (换进程重算, 排除存档 bug);
  2. 该解相对生产参数的漂移有多大 (哪些参数动了、动多少);
  3. **CS:GO 190 场里有多少场的选手排序/分数会变** —— 这决定"写回"是否真的
     破坏冻结, 以及破坏范围.

用法: .venv/bin/python tuning/verify_refine.py <best.json> [WORKERS=12]
"""
import copy
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
from tuning.cma_refine import PATHS, get_nested, set_nested  # noqa: E402

_G = {}


def _init_worker():
    import sys as _s
    _s.stdout = open(os.devnull, "w")
    import eval_full as ef
    _G["official"] = ef.load_official()
    _G["cache"] = ef.load_cache(_G["official"])
    _G["seg"] = {e: ef.segment_of(e) for e in _G["cache"]}
    # Python 3.14 Linux 默认 forkserver → 子进程不继承父进程 _G, 参数走环境变量传
    _G["ref_params"] = json.load(open(os.environ["EVP_REFINE_SRC"]))["params"]


def scores_for(eid, cfg):
    """该赛事下所有选手的 total_score (按 player 名对齐的 dict)."""
    summary, *_ = evp_exp.run_experiment(None, None, None, cfg=cfg, save=False,
                                         raw_df=_G["cache"][eid])
    return dict(zip(summary["player"], summary["total_score"]))


def compare_event(eid):
    """生产 cfg vs 精调 cfg 在该赛事的逐选手分数对比."""
    if eid not in _G["cache"]:
        return None
    prod = copy.deepcopy(evp_exp.EVP_CONFIG)
    ref = copy.deepcopy(evp_exp.EVP_CONFIG)
    for p, v in _G["ref_params"].items():
        set_nested(ref, p, v)

    a = scores_for(eid, prod)
    b = scores_for(eid, ref)
    common = set(a) & set(b)
    if not common:
        return {"eid": eid, "seg": _G["seg"][eid], "n": 0, "changed": 0, "maxdiff": 0.0}
    # 排序对比: 只看双方共同出现的选手, 按各自分数排序
    ra = [p for p in sorted(common, key=lambda x: -a[x])]
    rb = [p for p in sorted(common, key=lambda x: -b[x])]
    diffs = [abs(a[p] - b[p]) for p in common]
    return {"eid": eid, "seg": _G["seg"][eid], "n": len(common),
            "changed": sum(1 for p in common if abs(a[p] - b[p]) > 1e-9),
            "rank_changed": sum(1 for i, p in enumerate(ra) if p != rb[i]),
            "maxdiff": max(diffs), "reldiff": max(diffs) / (max(a.values()) or 1.0)}


def main():
    src = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    best = json.load(open(src))
    _G["ref_params"] = best["params"]
    os.environ["EVP_REFINE_SRC"] = src   # worker initializer 据此加载 (forkserver)

    prod = copy.deepcopy(evp_exp.EVP_CONFIG)
    print(f"=== 参数漂移 (精调 vs 生产) ===")
    moved = []
    for p in PATHS:
        a = get_nested(prod, p)
        b = best["params"].get(p, a)   # params 是扁平字典 (键含点号), 直接取
        if abs(b / a - 1.0) > 1e-6:
            moved.append((p, a, b, b / a))
    moved.sort(key=lambda t: -abs(t[3] - 1.0))
    print(f"42 个核心参数中动了 {len(moved)} 个:")
    for p, a, b, r in moved:
        print(f"  {p:<30} {a:>10.5f} → {b:>10.5f}  (x{r:.4f})")

    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        import eval_full as _ef
        eids = sorted(_ef.load_official().keys(), key=lambda e: (_ef.segment_of(e), e))
        rows = [r for r in ex.map(compare_event, eids) if r is not None]

    print(f"\n=== 冲击面 (逐赛事逐选手 total_score 对比) ===")
    for seg in ("csgo", "cs2"):
        sub = [r for r in rows if r["seg"] == seg]
        ev_ch = [r for r in sub if r["changed"] > 0]
        rk_ch = [r for r in sub if r.get("rank_changed", 0) > 0]
        npl = sum(r["n"] for r in sub)
        nch = sum(r["changed"] for r in sub)
        md = max((r["maxdiff"] for r in sub), default=0.0)
        mrel = max((r.get("reldiff", 0.0) for r in sub), default=0.0)
        print(f"[{seg}] {len(sub)} 场: 分数变化 {len(ev_ch)} 场 / 排序变化 {len(rk_ch)} 场; "
              f"选手分数变化 {nch}/{npl}; 最大绝对差 {md:.4f} (相对 {mrel:.2%})")
        if ev_ch:
            print(f"   分数变化最大的 5 场:")
            for r in sorted(ev_ch, key=lambda x: -x["maxdiff"])[:5]:
                print(f"     {r['eid']}: {r['changed']}/{r['n']} 人变, maxdiff={r['maxdiff']:.4f}")

    with open(os.path.splitext(src)[0] + "_impact.json", "w") as f:
        json.dump({"src": src, "obj": best["obj"], "delta": best["delta"],
                   "moved_params": [{"p": p, "prod": a, "ref": b, "ratio": r}
                                    for p, a, b, r in moved],
                   "events": rows}, f, indent=1)
    print(f"\n→ {os.path.splitext(src)[0]}_impact.json")


if __name__ == "__main__":
    main()
