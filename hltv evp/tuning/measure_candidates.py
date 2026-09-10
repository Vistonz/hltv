"""候选配置在全量 255 场上的分量对照 — 一次测出 (ord/in/mvp/mis), 之后任意权重可重排.

背景: obj = W_ORD·100·ord + W_IN·100·in + W_MVP·100·mvp − W_MIS·mis, 四个分量与权重无关.
所以"某个候选在 W_IN=X 下好不好"不需要在每个 X 重跑 —— 测一次分量, 线性组合即可.

本脚本测的是**全量 255 场**口径 (CS2_OVERRIDES 只影响 CS2 事件, CS:GO 恒为冻结源).
旧档案 cs2axes_best.json / cs2mapstats_best.json 存的是 CS2-only 子集口径 (n_ev=64),
不能与全量锚点直接线性比较, 故必须在此重测全量.

用法: .venv/bin/python tuning/measure_candidates.py [输出json]
"""
import copy
import io
import json
import os
import sys
from contextlib import redirect_stdout

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ef  # noqa: E402

OUT = "/home/hongbin/.claude/jobs/75f6c437/tmp/win045/candidates.json"

# 候选: (名称, cs2_overrides) — None=生产默认, {}=机制强制关, dict=逐轴覆写
CANDS = [
    ("生产2轴", None),
    ("机制关", {}),
    ("9轴", {"KPRW_E": 0.28195860051952193, "DPR": -0.17046274174982917,
             "KPRW_AVG": -0.029770073083906112, "KPR": 0.2498601127020158,
             "KAST": -0.3433319052678362, "MK": -0.10141801973297487,
             "ADR": -0.14701451785673447, "SWING_SUM": -0.27344612923109285,
             "SWING_AVG": 0.25380691361604546}),
    ("网格(0.175,-0.025)", {"KPRW_E": 0.175, "DPR": -0.025}),
    ("推大(0.282,-0.1705)", {"KPRW_E": 0.282, "DPR": -0.1705}),
]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else OUT
    official = ef.load_official()
    ordered = ef.load_ordered()
    cache = ef.load_cache(official)
    slug2nick = ef.load_slug2nick()

    rows = []
    for name, ov in CANDS:
        if ov is None:
            cs2ov = None
        else:
            cs2ov = {f"CS2_{k}_W": v for k, v in ov.items()}
        with redirect_stdout(io.StringIO()):
            r = ef.eval_cfg(copy.deepcopy(evp_exp.EVP_CONFIG), cache, official,
                            ordered, slug2nick, discard_ordered=ef.DISCARD_ORDERED,
                            cs2_overrides=cs2ov)
        rows.append({"name": name, "ord": r["ordered"], "in": r["in_topn"],
                     "mvp": r["mvp_ok"], "mis": r["mismatch"],
                     "in_hit": r["in_hit"], "in_tot": r["in_tot"],
                     "mvp_n": r["mvp_n"]})
        print(f"{name:<22} ord={r['ordered']:.4f} in={r['in_topn']:.4f} "
              f"mvp={r['mvp_ok']:.4f} mis={r['mismatch']:.2f}", flush=True)

    print(f"\n权重 W_ORD={ef.W_ORD} W_MVP={ef.W_MVP} W_MIS={ef.W_MIS}")
    for w in (1.0, 0.7, 0.45, 0.3, 0.0):
        scored = sorted(((ef.W_ORD * r["ord"] * 100 + w * r["in"] * 100
                          + ef.W_MVP * r["mvp"] * 100 - ef.W_MIS * r["mis"], r["name"])
                         for r in rows), key=lambda t: -t[0])
        ranking = " > ".join(n for _, n in scored)
        print(f"  W_IN={w:<4} 排序: {ranking}")

    with open(out, "w") as f:
        json.dump({"w_ord": ef.W_ORD, "w_mvp": ef.W_MVP, "w_mis": ef.W_MIS,
                   "candidates": rows}, f, indent=1)
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
