"""CS2 原两轴扩展区网格 (2026-09-10) — 补齐 2D 网格从未覆盖的区域.

背景 (为什么还要跑):
  - 旧 2D 网格 search_cs2_mapstats.py 只扫 kprw_e∈[0,0.4] step0.05 与 dpr≥0,
    **从未测 kprw_e>0.27 与 dpr 负侧**; 生产定案 (0.19, -0.04) 落在那张网格内.
  - decision_cs2_axes.py 的 B 臂 = CMA 9 轴点的 kprw_e=0.2820 / dpr=-0.1705
    "只留两轴", CS2-only 181.8835 (输生产 2.7058) — 但那是**单点**.
  - 本脚本在扩展区做两轴细网格, 判定 "把原两轴推大" 这一族是否真能赢生产,
    并把 A(生产)/B(单点)/C(9轴) 三臂的四项指标 (in/ord/mvp/mis) 一并打印.

口径: CS2-only objective (CS:GO 恒常数, 机制结构上不动 CS:GO), 终值用全量复核.
用法: .venv/bin/python tuning/grid_cs2_two_axis.py [STEP=0.025]
"""
import contextlib
import io
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ev  # noqa: E402

BEST = "/home/hongbin/.claude/jobs/75f6c437/tmp/cs2axes_best.json"
AXES = ["KPRW_E", "DPR", "KPRW_AVG", "KPR", "KAST", "MK", "ADR", "SWING_SUM", "SWING_AVG"]
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
    # CS2 评估子集: 机制只可能改 CS2, CS:GO 在 objective 中恒为常数 → 提速
    _G["cache_cs2"] = {eid: df for eid, df in _G["cache"].items()
                       if _ef.segment_of(eid) == "cs2"}


def eval_pair(pair):
    """pair = (kprw_e_w, dpr_w) → CS2-only obj."""
    import eval_full as _ef
    ov = {"CS2_KPRW_E_W": pair[0], "CS2_DPR_W": pair[1]}
    r = _ef.eval_cfg(evp_exp.EVP_CONFIG, _G["cache_cs2"], _G["official"], _G["ordered"],
                     _G["slug2nick"], discard_ordered=_G["discard"], cs2_overrides=ov)
    return r["obj"]


def _fmt(tag, r):
    return (f"{tag:<26} obj={r['obj']:8.4f}  in={r['in_topn']*100:6.2f}%  ord={r['ordered']*100:6.2f}%  "
            f"mvp={r['mvp_ok']*100:6.2f}%  mis={r['mismatch']:7.2f}")


def main():
    step = float(sys.argv[1]) if len(sys.argv) > 1 else 0.025

    official = ev.load_official()
    ordered = ev.load_ordered()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()
    kw = dict(discard_ordered=ev.DISCARD_ORDERED)
    cache_cs2 = {eid: df for eid, df in cache.items() if ev.segment_of(eid) == "cs2"}

    def silent(fn, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*a, **k)

    def run(c, ov):
        return silent(ev.eval_cfg, evp_exp.EVP_CONFIG, c, official, ordered,
                      slug2nick, cs2_overrides=ov, **kw)

    # ---- 三臂 (与 decision_cs2_axes.py 同一口径) ----
    ov_prod = None                                     # CS2_OVERRIDES 默认 = 生产 2 轴
    ov_b = {"CS2_KPRW_E_W": 0.2820, "CS2_DPR_W": -0.1705}   # CMA 9 轴点只留两轴
    ov_9 = None
    if os.path.exists(BEST):
        w = json.load(open(BEST))["weights"]           # 键 = 裸轴名
        ov_9 = {f"CS2_{ax}_W": w.get(ax, 0.0) for ax in AXES}

    print("=" * 96)
    print(f"CS2 评估赛事 {len(cache_cs2)} 场 (共 {len(cache)} 场, CS:GO 恒常数)")
    print("=" * 96)
    print(f"\n[A/B/C 三臂 · CS2-only 四项指标]   (A 生产 2 轴 0.19/-0.04, B = 0.2820/-0.1705)")
    a_cs2 = run(cache_cs2, ov_prod)
    b_cs2 = run(cache_cs2, ov_b)
    print(_fmt("A 生产 2 轴", a_cs2))
    print(_fmt("B 两轴推大 (CMA点)", b_cs2))
    print(f"{'':<26} Δ(B−A) = {b_cs2['obj']-a_cs2['obj']:+.4f}")
    if ov_9:
        c_cs2 = run(cache_cs2, ov_9)
        print(_fmt("C 9 轴全量", c_cs2))
        print(f"{'':<26} Δ(C−B) = {c_cs2['obj']-b_cs2['obj']:+.4f} (新增 7 轴边际)")
    print(f"\n[A/B 全量两段 四项指标]")
    a_full = run(cache, ov_prod)
    b_full = run(cache, ov_b)
    print(_fmt("A 生产 2 轴", a_full))
    print(_fmt("B 两轴推大 (CMA点)", b_full))
    print(f"{'':<26} Δ(B−A) = {b_full['obj']-a_full['obj']:+.4f}")

    # ---- 扩展区网格: kprw_e>0.27 与 dpr 负侧 (旧网格盲区) ----
    ke = [round(0.10 + i * step, 4) for i in range(int((0.45 - 0.10) / step) + 1)]
    dp = [round(-0.30 + j * step, 4) for j in range(int((0.10 + 0.30) / step) + 1)]
    print(f"\n[扩展区两轴网格] kprw_e∈[{ke[0]},{ke[-1]}] dpr∈[{dp[0]},{dp[-1]}] "
          f"step={step} → {len(ke)*len(dp)} 点 (CS2-only)")
    t0 = time.time()
    workers = max(8, min((os.cpu_count() or 8) - 1, 14))
    best = (-1e9, None)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        pairs = [(a, b) for a in ke for b in dp]
        done = 0
        for pair, val in zip(pairs, ex.map(eval_pair, pairs, chunksize=4)):
            done += 1
            if val > best[0]:
                best = (val, pair)
            if done % 40 == 0 or done == len(pairs):
                print(f"  {done}/{len(pairs)}  best obj={best[0]:.4f} @ {best[1]} ({time.time()-t0:.0f}s)",
                      flush=True)
    print(f"\n扩展区网格 argmax: obj={best[0]:.4f} @ kprw_e={best[1][0]} dpr={best[1][1]}")
    print(f"对照 A 生产 2 轴 CS2-only = {a_cs2['obj']:.4f}  → 网格最优 Δ = {best[0]-a_cs2['obj']:+.4f}")
    ov_best = {"CS2_KPRW_E_W": best[1][0], "CS2_DPR_W": best[1][1]}
    bf = run(cache, ov_best)
    print(f"网格最优点全量两段 obj = {bf['obj']:.4f}  (Δvs 生产 {bf['obj']-a_full['obj']:+.4f})")
    print(_fmt("网格最优 (全量)", bf))


if __name__ == "__main__":
    main()
