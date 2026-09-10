"""预检 v4: 决定机制轴集 (在 v3 的 score-matched 配对上的联合条件分析).

目标: 从 ~12 个候选里挑 ≤4 个互相正交且携带独立边界信号的轴.
方法: (1) 全 CS2 选手特征相关矩阵 → 剔除共线冗余;
      (2) 在 v3 边界配对 (总分已配对平衡) 上跑联合 logit
          official ~ z(各特征), 系数显著者 = 独立于其它特征仍解释官方偏好的轴.
"""
import io
import os
import sys
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import eval_full as ev
import evp_experiment as evp_exp
from tuning.learn.precheck_cs2_mapstats import player_features, _REQ, FEATS

cfg = dict(evp_exp.EVP_CONFIG)


def zscore(series):
    sd = series.std()
    return (series - series.mean()) / sd if sd and sd > 0 else series * 0


def main():
    official = ev.load_official()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()
    buf = io.StringIO()

    allrows = []      # 全选手: 每行一选手特征 (池化, 供相关矩阵)
    pairs = []        # (z-feature vector of official, of non-official) on matched pairs
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
        # 全选手特征表 (此事件内) — 只保留有 total_score 的选手
        df = summary.sort_values("total_score", ascending=False).reset_index(drop=True)
        df = df[df["player"].isin(feats)].copy()
        df["official"] = df["player"].isin(set(ops))
        for _, r in df.iterrows():
            row = {"official": int(r["official"]), "eid": eid}
            for fk in FEATS:
                v = feats[r["player"]].get(fk)
                row[fk] = v
            allrows.append(row)
        # 边界配对 (同 v3 逻辑, 但记录整行 z 向量)
        rng = float(df["total_score"].max() - df["total_score"].min())
        if rng <= 0:
            continue
        band = 0.10 * rng
        offs = df[df["official"]]
        nons = df[~df["official"]]
        if len(nons) == 0:
            continue
        # z 基准: 事件内所有有特征选手 (从 feats dict 建表)
        ev_feat = pd.DataFrame({p: {fk: feats[p][fk] for fk in FEATS}
                                for p in df["player"]}).T
        zdf = ev_feat.apply(zscore)
        zdf["player"] = zdf.index
        df = df.merge(zdf, on="player", how="left")
        offs = df[df["official"]]
        nons = df[~df["official"]]
        used_n = set()
        for _, o in offs.iterrows():
            so = float(o["total_score"])
            cand = nons[(nons["total_score"] - so).abs() <= band]
            cand = cand[~cand["player"].isin(used_n)]
            if len(cand) == 0:
                continue
            nn = cand.loc[(cand["total_score"] - so).abs().idxmin()]
            used_n.add(nn["player"])
            pairs.append((zdf.loc[o["player"]], zdf.loc[nn["player"]]))

    print(f"事件={n_events}  全选手行={len(allrows)}  边界配对={len(pairs)}")

    # ---- (1) 相关矩阵 (全选手池, 非官方/官方混合) ----
    pool = pd.DataFrame(allrows)
    corr = pool[FEATS].corr()
    # 只显示 |corr|>=0.6 的高共线对
    print("\n[高共线对 |r|>=0.7]")
    shown = set()
    for a in FEATS:
        for b in FEATS:
            if a < b:
                r = corr.loc[a, b]
                if abs(r) >= 0.7 and (a, b) not in shown:
                    print(f"  {a:>10} ~ {b:>10}: r={r:+.2f}")
                    shown.add((a, b))

    # ---- (2) 配对 logit: official 领先特征 是否被其它轴解释掉 ----
    # 每对构造 差分向量 δ = z_official - z_non; 因配对已平衡总分, δ>0 = 该轴官方领先.
    from scipy import stats as _  # noqa
    import statsmodels.api as sm
    rows = []
    for zo, zn in pairs:
        rows.append({fk: zo[fk] - zn[fk] for fk in FEATS})
    D = pd.DataFrame(rows)
    # 全模型
    X = sm.add_constant(D[FEATS])
    y = np.ones(len(D))
    try:
        fit = sm.Logit(y, X).fit(disp=0)
        print(f"\n[配对联合 logit — 全 12 轴, 系数解释力]\n{'轴':>11} | {'coef':>7} | {'p':>6} | 方向")
        for fk, c, p in zip(FEATS, fit.params[1:], fit.pvalues[1:]):
            star = "**" if p < 0.01 else ("*" if p < 0.05 else ("." if p < 0.1 else " "))
            print(f"{fk:>11} | {c:>+7.3f} | {p:>6.3f} | {star}")
    except Exception as e:
        print(f"全模型 logit 失败: {e}")
        # 退化: 单轴显著性 (分对数 z 检验 vs 0)
        print("\n[单轴配对差分检验 (o>n 偏向)]")
        for fk in FEATS:
            d = D[fk].dropna()
            z = d.mean() / (d.std() / np.sqrt(len(d))) if d.std() > 0 else 0
            from scipy import stats as st
            p = 2 * (1 - st.norm.cdf(abs(z)))
            print(f"{fk:>11} | dbar={d.mean():+.3f} | z={z:+.2f} | p={p:.3f}")


if __name__ == "__main__":
    main()
