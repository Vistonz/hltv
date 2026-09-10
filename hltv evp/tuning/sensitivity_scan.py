"""生产配置的单轴灵敏度扫描 — 直接回答"它是不是局部峰顶, 哪个参数还有余量".

动机: 42 维 CMA 在尖峭地形上收敛缓慢 (900 evals 后仍低于起点), 只能证明"没找到更好的",
不能证明"附近没有更好的". 单轴扫描是互补且可解释的检验:

  对 42 个参数逐个 × {−10%, −5%, +5%, +10%}, 其余参数全部保持生产值 → 评估全量 obj.
  - 所有扰动都不优于锚点 → 锚点是**坐标轴方向的局部峰顶** (每个参数都恰在最优侧);
  - 某参数某个方向更好   → 该轴仍有余量, 输出方向与幅度供进一步精调.

注意: 只测轴对齐方向, 测不出参数间协同 (那是 CMA 的活). 两者结论一致才叫真峰顶.

用法: .venv/bin/python tuning/sensitivity_scan.py [DELTAS=0.05,0.10] [WORKERS=12]
"""
import copy
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
from tuning.search_cma import PATHS, WIDE, LO_MUL, HI_MUL, get_nested, set_nested  # noqa: E402

OUT = os.environ.get("EVP_CMA_OUT", "/home/hongbin/.claude/jobs/75f6c437/tmp/win045")
TAG = os.environ.get("EVP_SENS_TAG", "sens45")
_G = {}


def _init_worker():
    import sys as _s
    _s.stdout = open(os.devnull, "w")
    import eval_full as ef
    _G["official"] = ef.load_official()
    _G["ordered"] = ef.load_ordered()
    _G["cache"] = ef.load_cache(_G["official"])
    _G["slug2nick"] = ef.load_slug2nick()
    _G["discard"] = ef.DISCARD_ORDERED


def eval_one(cfg):
    import eval_full as ef
    r = ef.eval_cfg(cfg, _G["cache"], _G["official"], _G["ordered"],
                    _G["slug2nick"], discard_ordered=_G["discard"])
    return {"obj": r["obj"], "ord": r["ordered"], "in": r["in_topn"],
            "mvp": r["mvp_ok"], "mis": r["mismatch"]}


def make_cfg(path, factor):
    """生产配置 + 单参数 × factor. 越界/非正 → 返回 None (跳过该点)."""
    cfg = copy.deepcopy(evp_exp.EVP_CONFIG)
    cur = get_nested(cfg, path)
    v = cur * factor
    if v <= 0:
        return None
    lo, hi = WIDE[path] if path in WIDE else (cur * LO_MUL, cur * HI_MUL)
    if not (lo * 0.5 <= v <= hi * 2.0):   # 允许略超原空间, 但拒绝离谱值
        return None
    set_nested(cfg, path, v)
    return cfg


def main():
    deltas = ([float(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1
              else [0.05, 0.10])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    anchor = copy.deepcopy(evp_exp.EVP_CONFIG)
    jobs, meta = [], []
    for p in PATHS:
        for d in deltas:
            for sign in (-1, 1):
                f = 1.0 + sign * d
                cfg = make_cfg(p, f)
                if cfg is not None:
                    jobs.append(cfg)
                    meta.append((p, f))

    print(f"单轴灵敏度扫描: {len(jobs)} 个点 "
          f"(42 参数 × ±{deltas}), workers={workers}, 输出={OUT}/{TAG}_*.json",
          flush=True)

    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        anchor_r = list(ex.map(eval_one, [anchor]))[0]
        print(f"锚点 obj = {anchor_r['obj']:.4f}", flush=True)
        results = list(ex.map(eval_one, jobs))

    rows = []
    for (p, f), r in zip(meta, results):
        rows.append({"param": p, "factor": f, "obj": r["obj"],
                     "delta": r["obj"] - anchor_r["obj"],
                     "ord": r["ord"], "in": r["in"], "mvp": r["mvp"], "mis": r["mis"]})

    rows.sort(key=lambda x: -x["delta"])
    print(f"\n{'参数':<30} {'因子':>6} {'obj':>10} {'Δ':>9}")
    for r in rows[:15]:
        print(f"{r['param']:<30} x{r['factor']:<5.2f} {r['obj']:>10.4f} {r['delta']:>+9.4f}")
    print("  ... (完整表见 json)")

    better = [r for r in rows if r["delta"] > 1e-9]
    print(f"\n优于锚点的扰动: {len(better)} / {len(rows)}")
    if better:
        print("⇒ 锚点不是单轴峰顶, 存在可利用余量:")
        for r in better[:20]:
            print(f"   {r['param']:<28} x{r['factor']:.2f}  Δ={r['delta']:+.4f}")
    else:
        print("⇒ 锚点已是**单轴局部峰顶**: 42 个参数在 ±%s 内任一方向都劣化 (或持平)."
              % "/".join(f"{d:.0%}" for d in deltas))

    with open(os.path.join(OUT, f"{TAG}.json"), "w") as f:
        json.dump({"anchor": anchor_r, "deltas": deltas, "rows": rows}, f, indent=1)
    print(f"→ {os.path.join(OUT, TAG + '.json')}")


if __name__ == "__main__":
    main()
