"""CS2 mapstats 机制预检 v3: score-matched 边界配对 (决定版).

v1 (Δpct) 被回归效应污染 (官方入选 score_pct 近 1, 特征 pct 回归均值 → 假性全负).
v2 (窗口 AUC) 窗口内官方仍整体高分 → AUC 高仍是 score 代理.

v3 干净口径: 每赛事把每位官方入选者与"total_score 最接近的落选者"配对, 只保留
分差 ≤ 10% 事件分数跨度 的配对 (分数可比 = 控制住总分). 在此类"边界配对"上,
官方 vs 落选 的特征差异 = 真正的排序外增量信息:
  frac_o_higher > 0.5 → 同分下官方入选者该特征更高 → 机制正号权重可把官方推过线
  < 0.5 → 官方反而偏好低值 (对 dpr/swingG 等负向特征即"偏好低值"= 正信号需取反)
  ≈ 0.5 → 无增量 (官方在同分人群内不按该特征选择)
"""
import io
import os
import sys
from collections import defaultdict
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import eval_full as ev
import evp_experiment as evp_exp

cfg = dict(evp_exp.EVP_CONFIG)

_REQ = ["map_kprw", "map_won_kills", "map_kpr", "map_dpr", "map_kast", "map_mk_rating",
        "map_swing_total", "map_swing_added", "map_swing_given", "map_adr", "map_rating30"]
FEATS = ["kprw_e", "kprw_avg", "kpr", "dpr", "kast", "mk",
         "swing_sum", "swing_avg", "swingA_sum", "swingG_sum", "adr", "r30"]


def player_features(df):
    if not all(c in df.columns for c in _REQ):
        return None
    d = df.dropna(subset=["player"]).copy()
    feats = {}
    for p, g in d.groupby("player"):
        wg = g[g["map_kprw"] > 0]
        won_k = pd.to_numeric(wg["map_won_kills"], errors="coerce").fillna(0)
        eff = pd.to_numeric(wg["map_won_kills"], errors="coerce") / \
            pd.to_numeric(wg["map_kprw"], errors="coerce")
        denom = eff.fillna(0).sum()
        feats[p] = {
            "kprw_e": (won_k.sum() / denom) if denom > 0 else np.nan,
            "kprw_avg": pd.to_numeric(g["map_kprw"], errors="coerce").mean(),
            "kpr": pd.to_numeric(g["map_kpr"], errors="coerce").mean(),
            "dpr": pd.to_numeric(g["map_dpr"], errors="coerce").mean(),
            "kast": pd.to_numeric(g["map_kast"], errors="coerce").mean(),
            "mk": pd.to_numeric(g["map_mk_rating"], errors="coerce").mean(),
            "swing_sum": pd.to_numeric(g["map_swing_total"], errors="coerce").sum(),
            "swing_avg": pd.to_numeric(g["map_swing_total"], errors="coerce").mean(),
            "swingA_sum": pd.to_numeric(g["map_swing_added"], errors="coerce").sum(),
            "swingG_sum": pd.to_numeric(g["map_swing_given"], errors="coerce").sum(),
            "adr": pd.to_numeric(g["map_adr"], errors="coerce").mean(),
            "r30": pd.to_numeric(g["map_rating30"], errors="coerce").mean(),
        }
    return feats


def main():
    official = ev.load_official()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()
    buf = io.StringIO()

    # feat -> list of (o_val > n_val ? 1:0, 0.5 ties), 配对跨赛事池化
    pair_hits = defaultdict(list)
    per_event_frac = defaultdict(list)   # feat -> per-event 配对中 o>n 的比例 (≥2对才记)
    pair_gaps = []
    n_events = 0

    for eid, (mvp_slug, evp_slugs) in official.items():
        if eid not in cache or ev.segment_of(eid) != "cs2":
            continue
        raw = cache[eid]
        feats = player_features(raw)
        if feats is None:
            continue
        slugs = [s for s in ([mvp_slug] if mvp_slug else []) + list(evp_slugs) if s]
        if not slugs:
            continue
        N = len(slugs)
        with redirect_stdout(buf):
            summary, *_ = evp_exp.run_experiment(None, None, None, cfg=cfg,
                                                 save=False, raw_df=raw)
        smap = ev.build_name_index(summary["player"], slugs, slug2nick)
        ops = [smap[s] for s in slugs if s in smap]
        if len(ops) < N:
            continue
        n_events += 1
        df = summary.sort_values("total_score", ascending=False).reset_index(drop=True)
        df = df[df["player"].isin(feats)].copy()
        if len(df) < N + 1:
            continue
        official_set = set(ops)
        df["official"] = df["player"].isin(official_set)
        rng = float(df["total_score"].max() - df["total_score"].min())
        if rng <= 0:
            continue
        band = 0.10 * rng
        offs = df[df["official"]]
        nons = df[~df["official"]]
        if len(nons) == 0:
            continue
        ev_used = {fk: 0 for fk in FEATS}
        used_n = set()
        for _, o in offs.iterrows():
            so = float(o["total_score"])
            cand = nons[(nons["total_score"] - so).abs() <= band]
            if len(cand) == 0:
                continue
            cand = cand[~cand["player"].isin(used_n)]
            if len(cand) == 0:
                continue
            nn = cand.loc[(cand["total_score"] - so).abs().idxmin()]
            pair_gaps.append(abs(float(nn["total_score"]) - so) / rng)
            po, pn = o["player"], nn["player"]
            fo, fn = feats[po], feats[pn]
            used_n.add(pn)
            for fk in FEATS:
                vo, vn = fo.get(fk), fn.get(fk)
                if vo is None or vn is None or (isinstance(vo, float) and np.isnan(vo)) \
                        or (isinstance(vn, float) and np.isnan(vn)):
                    continue
                pair_hits[fk].append(1 if vo > vn else (0 if vo < vn else 0.5))
                ev_used[fk] += 1
        # 每事件比例 (≥3对才记, 避免噪声)
        ev_counter = defaultdict(int)
        for fk in FEATS:
            # 事件内已在上层循环记入 pair_hits, 无法从 pair_hits 反推事件边界
            pass
        # 直接每事件累计事件级 o>n 计数
        # (简化: pair_hits 已池化, 事件级一致性用另一途径 - 见下 per_event_frac 需按事件收集,
        #  为省事改用 pool 级二项即可)

    print(f"CS2 评估赛事(可配对): {n_events}")
    print(f"配对分数gap均值(占事件跨度): {np.mean(pair_gaps):.3f}  (应 ≤0.10 = 总分控制有效)")
    print(f"\n{'特征':>10} | {'对数':>5} | {'o>n比例':>7} | {'95%CI下界':>8} | 判读")
    for fk in FEATS:
        hs = pair_hits[fk]
        if not hs:
            print(f"{fk:>10} | {0:>5} | {'-':>7} |")
            continue
        n = len(hs)
        fr = float(np.mean(hs))
        se = float(np.sqrt(fr * (1 - fr) / n)) if n > 1 else 0.5
        lo = fr - 1.96 * se
        # 负向特征 dpr/swingG 的解读: frac<0.5 = 官方偏好更低值
        neg = fk in ("dpr", "swingG_sum")
        if fr >= 0.55 and lo > 0.5:
            tag = "★ 正号候选 (同分下官方入选者更高)"
        elif fr >= 0.53:
            tag = "弱正 (信号不足, 慎用)"
        elif fr <= 0.45 and (1 - lo) < 0.5:
            base = "☆ 官方偏好低值" if neg else "☆ 负号候选"
            tag = f"{base} (frac={fr:.2f})"
        else:
            tag = "≈0.5 无增量"
        print(f"{fk:>10} | {n:>5} | {fr:>7.3f} | {lo:>8.3f} | {tag}")


if __name__ == "__main__":
    main()
