"""预检 v5: 机制已写回后的残差增量判别 (决定能否扩维 2D → 3-5D).

v3 在 cfg0(机制全0) 的 total_score 上边界配对, 选出 kprw_e(0.628)/dpr(0.417) 两轴并已写回
(0.19/0.04, 全量 obj 161.2287→162.3726). 但 v3 原始判别里 kast 0.644 / adr 0.644 / kpr 0.639
其实高于已用轴 — 当时因与 rating3 共线 0.73-0.93 被排除. 问题是: 若先对公式内 rating (r30≡rating3,
corr 1.000) 残差化, 这些共线特征剩下的残差是否还携带官方偏好的独立增量?

方法 (比 v3 更严):
1. 配对总分用 cfg1 (机制 0.19/0.04 已生效) → 候选轴须在"公式+机制"之上仍有增量.
2. 事件内 demean r30 与候选特征 f; pooled OLS f_dm ~ r30_dm (无截距) 取 β_f → 残差 f_dm − β_f·r30_dm.
   此残差 = 该轴中公式(rating)解释不掉的部分 (同一赛事内对手强度等已被 demean 吸收).
3. 在 cfg1 边界配对 (官方 vs 最接近落选, |Δscore|≤10%跨度, 不重复用落选) 上比较残差:
   P(res_o > res_n) > 0.5 显著 = 残差仍有独立判别 → 该轴值得扩维; ≈0.5 = 公式已把它吃完, 不加.
4. r30 自身作对照应 → 0 (被完全残差化掉), 验证管线正确.

若任一候选残差判别显著 → 扩 mapstats 机制维再搜; 全无 → 诚实停 (机制已达该字段集边界).
用法: .venv/bin/python tuning/learn/precheck_cs2_mapstats_v5.py
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
from tuning.learn.precheck_cs2_mapstats import player_features, FEATS

# cfg1 = 生产现状 (两段线 + CS2 机制已写回 0.19/0.04)
cfg = dict(evp_exp.EVP_CONFIG)
print(f"[cfg1] CS2_CLUTCH_W={cfg['CS2_CLUTCH_W']}  CS2_DPR_W={cfg['CS2_DPR_W']}", flush=True)

# 候选: kprw_e 已用仍测(应衰减到部分), 主看 kast/adr/kpr/mk (共线但可能残差有增量);
# swing 无信息(v3 0.506)不测; r30 作对照应为 0.
FOCAL = ["kprw_e", "kprw_avg", "kpr", "kast", "mk", "adr", "dpr", "r30"]


def main():
    official = ev.load_official()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()
    buf = io.StringIO()

    allrows = []          # 每 (eid, player) 选手级特征行 (官方+全部落选)
    pair_data = []        # cfg1 边界配对的 (eid, 残差向量 o, 残差向量 n)
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
        df = summary.sort_values("total_score", ascending=False).reset_index(drop=True)
        df = df[df["player"].isin(feats)].copy()
        if len(df) < N + 1:
            continue
        df["official"] = df["player"].isin(set(ops))
        # 选手级特征表 (事件内, 供 demean)
        feat_df = pd.DataFrame({p: feats[p] for p in df["player"]}).T
        feat_df = feat_df[[f for f in FEATS if f in feat_df.columns]]
        for fk in FOCAL:
            if fk in feat_df.columns:
                feat_df[fk] = pd.to_numeric(feat_df[fk], errors="coerce")
        feat_df = feat_df.dropna(subset=["r30"])
        if len(feat_df) < N + 1:
            continue
        # 事件内 demean r30 (公式 rating 的事件均值 = 对手强度尺度, 需剔除)
        df = df[df["player"].isin(feat_df.index)].copy()
        df = df.merge(feat_df[FOCAL], left_on="player", right_index=True,
                      how="left")
        if df["r30"].std(ddof=0) <= 0 or len(df) < 3:
            continue
        n_events += 1
        # 记录 demean 前的原始值 (残差化在全局 β 后用原始值 - 事件均值 - β*中心r30)
        rows_ev = df[["player", "official", "total_score"] + FOCAL].copy()
        rows_ev["eid"] = eid
        allrows.append(rows_ev)

        # ---- cfg1 边界配对 (同 v3, 在机制后总分上) ----
        offs = df[df["official"]]
        nons = df[~df["official"]]
        rng = float(df["total_score"].max() - df["total_score"].min())
        if rng <= 0 or len(nons) == 0:
            continue
        band = 0.10 * rng
        used_n = set()
        ev_pairs = []
        for _, o in offs.iterrows():
            so = float(o["total_score"])
            cand = nons[(nons["total_score"] - so).abs() <= band]
            cand = cand[~cand["player"].isin(used_n)]
            if len(cand) == 0:
                continue
            nn = cand.loc[(cand["total_score"] - so).abs().idxmin()]
            used_n.add(nn["player"])
            ev_pairs.append((o["player"], nn["player"]))
        if len(ev_pairs) >= 2:
            pair_data.append((eid, ev_pairs))

    allrows = pd.concat(allrows, ignore_index=True)
    print(f"事件={n_events}  选手行={len(allrows)}  配对事件(≥2对)={len(pair_data)}", flush=True)

    # ---- 全局 pooled 残差化: f_dm ~ r30_dm (无截距) ----
    print("\n[pooled 残差化斜率 β_f (f_dm ~ r30_dm): 高 β = 该轴大多是公式 rating 的投影]")
    residuals = {}
    for fk in FOCAL:
        if fk not in allrows.columns or allrows[fk].notna().sum() < 30:
            continue
        # 事件内 demean (用事件均值)
        ev_mean = allrows.groupby("eid")[fk].transform("mean")
        r_mean = allrows.groupby("eid")["r30"].transform("mean")
        f_dm = allrows[fk] - ev_mean
        r_dm = allrows["r30"] - r_mean
        ok = allrows[fk].notna() & allrows["r30"].notna()
        num = float((f_dm[ok] * r_dm[ok]).sum())
        den = float((r_dm[ok] ** 2).sum())
        beta = num / den if den > 0 else 0.0
        residuals[fk] = f_dm - beta * r_dm
        print(f"  {fk:>10}: β={beta:+.3f}  残差sd={float(residuals[fk].std()):.4f}", flush=True)
    resid_df = pd.DataFrame(residuals)
    resid_df["player"] = allrows["player"]
    resid_df["eid"] = allrows["eid"]

    # ---- 配对残差判别: P(res_o > res_n) + 配对 t ----
    print(f"\n[cfg1 边界配对 残差判别 (控制 r30 后): 机制之上还有多少官方增量]\n"
          f"{'特征':>10} | {'对数':>5} | {'o>n比例':>7} | {'95%CI下界':>8} | {'t':>5} | 判读")
    cache_res = resid_df.set_index(["eid", "player"])
    for fk in FOCAL:
        if fk not in resid_df.columns:
            print(f"{fk:>10} | {0:>5} | 无残差列")
            continue
        hits, gaps = [], []
        for eid, ev_pairs in pair_data:
            for po, pn in ev_pairs:
                try:
                    ro = float(cache_res.loc[(eid, po), fk])
                    rn = float(cache_res.loc[(eid, pn), fk])
                except (KeyError, TypeError):
                    continue
                if ro != ro or rn != rn:
                    continue
                hits.append(1 if ro > rn else (0 if ro < rn else 0.5))
                gaps.append(ro - rn)
        if not hits:
            print(f"{fk:>10} | {0:>5} | 无配对")
            continue
        n = len(hits)
        fr = float(np.mean(hits))
        se = float(np.sqrt(fr * (1 - fr) / n)) if n > 1 else 0.5
        lo = fr - 1.96 * se
        d = np.asarray(gaps)
        t = float(d.mean() / (d.std(ddof=1) / np.sqrt(n))) if d.std(ddof=1) > 0 else 0.0
        # 判读: 显著 >0.5 = 独立增量候选; 0.5± = 公式已吃完; r30 应 ≈0 (对照)
        if fr >= 0.54 and lo > 0.5:
            tag = "★ 残差增量显著 — 值得扩维"
        elif fr >= 0.52:
            tag = "弱正 (信号不足)"
        elif fr <= 0.46:
            tag = "反向? (残差更低)"
        else:
            tag = "≈0.5 无增量 (公式已吃完)" + (" [对照 ✓]" if fk == "r30" else "")
        print(f"{fk:>10} | {n:>5} | {fr:>7.3f} | {lo:>8.3f} | {t:>5.2f} | {tag}")

    # ---- 决策 ----
    print("\n[决策] 残差显著(★)的轴 = 机制扩维候选; 全无 ★ → 停在现 2 轴 (诚实收束)")


if __name__ == "__main__":
    main()
