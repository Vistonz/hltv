"""按年份聚合 4 个评估指标 (in_topn/ordered/mvp/mismatch).

用法: .venv/bin/python analyze_by_year.py
读 eval_full.eval_cfg 的 per_event (已含 ord_hit/ord_tot/mvp_ok), 按赛事年份 (eval_full._event_year) 分组.
"""
import os
import sys
from collections import defaultdict

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import eval_full as ef  # noqa: E402

official = ef.load_official()
ordered = ef.load_ordered()
cache = ef.load_cache(official)
slug2nick = ef.load_slug2nick()
# 诊断用纯公式口径 (裸 EVP_CONFIG, cs2_overrides=None) → CS2 赛事机制-off.
# 基线/分年线画像沿用此口径; 若要生产镜像 (机制-on), 传 cs2_overrides=ef.evp_exp.CS2_OVERRIDES.
r = ef.eval_cfg(ef.evp_exp.EVP_CONFIG, cache, official, ordered, slug2nick,
                discard_ordered=ef.DISCARD_ORDERED)

agg = defaultdict(lambda: {"n": 0, "in_hit": 0, "in_tot": 0,
                           "ord_hit": 0, "ord_tot": 0, "mvp": 0, "mvp_tot": 0, "mis": 0.0})
for eid, e in r["per_event"].items():
    y = ef._event_year(int(eid))
    y = y if y is not None else 0  # 未知年份 → 0, 单独一行
    a = agg[y]
    a["n"] += 1
    a["in_hit"] += e["topN_ok"]; a["in_tot"] += e["official"]
    a["ord_hit"] += e["ord_hit"]; a["ord_tot"] += e["ord_tot"]
    a["mvp"] += e["mvp_ok"]; a["mvp_tot"] += 1
    a["mis"] += e["miss"]

print(f"{'年份':<6}{'赛事':>4}{'in_topn':>10}{'ordered':>10}{'mvp':>8}{'mismatch':>10}")
print("-" * 50)
for y in sorted(agg):
    a = agg[y]
    in_v = a["in_hit"] / a["in_tot"] * 100 if a["in_tot"] else 0
    ord_v = a["ord_hit"] / a["ord_tot"] * 100 if a["ord_tot"] else float("nan")
    mvp_v = a["mvp"] / a["mvp_tot"] * 100 if a["mvp_tot"] else 0
    print(f"{y:<6}{a['n']:>4}{in_v:>9.1f}%{ord_v:>9.1f}%{a['mvp']:>6}/{a['mvp_tot']}{a['mis']:>10.1f}")

# 三年段对比 (用户关注 25-26 vs 之前)
buckets = {"≤2023": lambda y: y and y <= 2023, "2024": lambda y: y == 2024, "≥2025": lambda y: y and y >= 2025}
print("\n三年段:")
print(f"{'段':<8}{'赛事':>4}{'in_topn':>10}{'ordered':>10}{'mvp':>8}{'mismatch':>10}")
for name, fn in buckets.items():
    in_h = in_t = ord_h = ord_t = mv = mt = 0
    mis = 0.0
    n = 0
    for eid, e in r["per_event"].items():
        if not fn(ef._event_year(int(eid))):
            continue
        n += 1
        in_h += e["topN_ok"]; in_t += e["official"]
        ord_h += e["ord_hit"]; ord_t += e["ord_tot"]
        mv += e["mvp_ok"]; mt += 1
        mis += e["miss"]
    if n == 0:
        continue
    print(f"{name:<8}{n:>4}{in_h/in_t*100:>9.1f}%{ord_h/ord_t*100 if ord_t else float('nan'):>9.1f}%{mv:>6}/{mt}{mis:>10.1f}")
