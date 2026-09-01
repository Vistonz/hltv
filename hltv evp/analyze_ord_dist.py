"""ordered 判定点的位置偏差分布诊断.

对每个参与 ordered 的赛事, 官方有序序列 seq[i] 在算法总分榜中的实际名次 pos_i:
  d_i = pos_i - (i+1)  (i 是 0-based, 理想位置 = i+1)
  d>0 = 被外来者挤出 d 名; d<0 = 比理想位置提前; d=0 = 恰好原位.
输出: 偏差分布直方 + 外来者挤入分析 (top(i+1) 中非官方人数量).
"""
import os
import sys
from collections import Counter

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import eval_full as ef  # noqa: E402
import evp_experiment as evp_exp  # noqa: E402

official = ef.load_official()
ordered_map = ef.load_ordered()
cache = ef.load_cache(official)
slug2nick = ef.load_slug2nick()

dists = Counter()        # d_i 分布
worst = []               # (eid, i, player, pos, d) 最严重挤出的点
total_points = 0
hit_points = 0
miss_points = 0
foreign_in_topk = Counter()   # 每个 miss 位置 top(i+1) 里非官方人的数量
miss_d_bucket = Counter()

def run_event(eid, mvp_slug, evp_slugs):
    global total_points, hit_points, miss_points
    if eid not in cache:
        return  # raw 缺失, 无法评估 (同 eval_cfg 行为)
    slugs = ([mvp_slug] if mvp_slug else []) + list(evp_slugs)
    slugs = [s for s in slugs if s]
    if not slugs:
        return
    N = len(slugs)
    summary, *_ = evp_exp.run_experiment(None, None, None, cfg=evp_exp.EVP_CONFIG,
                                         save=False, raw_df=cache[eid])
    df = summary.sort_values("total_score", ascending=False).reset_index(drop=True)
    slug_map = ef.build_name_index(df["player"], slugs, slug2nick)
    official_players = []
    for s in slugs:
        if s in slug_map:
            official_players.append(slug_map[s])
        else:
            return  # raw 覆盖不全, 该赛事无法评估
    if eid not in ordered_map or eid in ef.DISCARD_ORDERED:
        return
    news_seq = ordered_map[eid]
    nick2player = {}
    for s, p in slug_map.items():
        for n in ([p] + list(slug2nick.get(s, ()))):
            nl = ef.norm_name(n)
            if nl:
                nick2player.setdefault(nl, set()).add(p)
    mapped = []
    ok = True
    for n in news_seq:
        cand = nick2player.get(ef.norm_name(n))
        if cand and len(cand) == 1:
            mapped.append(next(iter(cand)))
        else:
            ok = False
            break
    if not ok:
        return
    mapped_set = set(mapped)
    full_players = set(official_players)
    evp_players = set(slug_map[s] for s in evp_slugs if s in slug_map)
    seq = None
    if official_players and official_players[0] in mapped_set and mapped_set <= full_players:
        seq = mapped
    elif mapped_set == evp_players:
        seq = [official_players[0]] + mapped
    if not seq:
        return
    # 算法名次表
    rank_of = {p: i + 1 for i, p in enumerate(df["player"])}
    for i, p in enumerate(seq):
        total_points += 1
        pos = rank_of.get(p)
        if pos is None:
            continue  # 官方人在算法榜找不到 (数据缺失, 不计)
        d = pos - (i + 1)
        dists[d] += 1
        if d <= 0:
            hit_points += 1
        else:
            miss_points += 1
            miss_d_bucket[d] += 1
            foreign = len([pp for pp in df["player"].head(i + 1) if pp not in full_players])
            foreign_in_topk[foreign] += 1
            worst.append((eid, i, p, pos, d))


# ---- 主循环 (模块级) ----
for eid, (mvp, evps) in official.items():
    run_event(eid, mvp, evps)

print(f"总判定点 {total_points}: 命中 {hit_points} ({hit_points/total_points:.1%}), "
      f"miss {miss_points} ({miss_points/total_points:.1%})")
print("\n=== 偏差 d = pos-(i+1) 分布 (全点) ===")
for d in sorted(dists):
    bar = "#" * min(60, dists[d])
    print(f"d={d:>4}: {dists[d]:>5}  {bar}")

print("\n=== miss 点的挤出距离分布 ===")
for d in sorted(miss_d_bucket):
    print(f"挤出 {d} 名: {miss_d_bucket[d]} 点")

print("\n=== miss 点 top(i+1) 中非官方人数量 ===")
for f in sorted(foreign_in_topk):
    print(f"{f} 个外来者: {foreign_in_topk[f]} 点")

print("\n=== 最严重的 15 个挤出点 ===")
for eid, i, p, pos, d in sorted(worst, key=lambda x: -x[4])[:15]:
    print(f"  [{eid}] 官方第{i+1}位 {p}: 算法第{pos}名 (被挤出 {d} 名)")

print("\n=== 距离加权 ord_score 随 α (双向对称, score=max(0,1-α|d|)) ===")
total = sum(dists.values())
bins = {f"{b}": 0 for b in ["d=0", "|d|=1", "|d|=2", "|d|=3", "|d|=4", "|d|>=5"]}
for d, c in dists.items():
    if d == 0:
        bins["d=0"] += c
    elif abs(d) == 1:
        bins["|d|=1"] += c
    elif abs(d) == 2:
        bins["|d|=2"] += c
    elif abs(d) == 3:
        bins["|d|=3"] += c
    elif abs(d) == 4:
        bins["|d|=4"] += c
    else:
        bins["|d|>=5"] += c
print("  分布:", {k: v for k, v in bins.items()}, f"(总 {total})")
for a in [0.05, 0.1, 0.2, 0.33, 0.5, 0.75, 1.0]:
    sc = sum(max(0.0, 1.0 - a * abs(d)) * c for d, c in dists.items())
    print(f"  α={a:<5} ord_score={sc/total*100:6.2f}%  (obj 中该项=W_ORD×{sc/total*100:.2f})")
# 参考: 二值命中率 (d<=0)
hit = sum(c for d, c in dists.items() if d <= 0)
print(f"  参考: 二值命中率(d<=0) = {hit/total*100:.2f}%")
