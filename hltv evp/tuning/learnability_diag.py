"""可学性诊断: 官方相对公式的残差是否可学?

回答三问 (GroupKFold 按赛事切, 训练不含验证赛事任何官方信息):
  Q1 原始输入(RAW)能否学出超过公式的赛事内排序?   → M1 vs 公式 86.3%
  Q2 公式外字段 match_baseline_rating 是否有增量?  → M2(RAW+BL) vs M1(RAW)
  Q3 全特征(RAW+BL+FM+TS)上限在哪?                → M3
对照 M0: 仅公式总分 total_score → "公式判别力"基线 (等效公式排序).

评估口径:
  - 全池 AUC       (负样本=同赛事 raw 其余所有人; 偏乐观, 强弱分明)
  - 边界池 AUC     (formula_rank<=max(3N,15) 的选手; 贴任务, 反映纠偏能力)
  - 赛事内重排 in_topn (OOF proba 排 top N ∩ 官方 / N; 与生产 86.3% 同口径)
  - mvp top1 命中
用法: ./.venv/bin/python tuning/learnability_diag.py
"""
import os
import sys

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold

DS = "/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/dataset.pkl"

RAW = ["n_maps", "rating_mean", "rating_max", "rating_std", "win_frac",
       "frac_r110", "frac_r130", "rd_mean", "n_win_bo", "n_grp",
       "rating_grp_mean", "n_po", "rating_po_mean", "n_gf", "rating_gf_mean",
       "opp_rank_mean", "n_vs_top5", "n_vs_top10", "rating_vs_top5_mean"]
BL = ["base_mean", "over_mean", "over_frac"]          # match_baseline_rating 族 (公式外)
FM = [f"fm_{c}" for c in ["n_bo_games", "group_win_maps", "group_len_factor",
                          "group_exempt", "group_bo_total", "group_effective",
                          "group_soft_capped", "playoff_bo_total",
                          "playoff_soft_capped"]]
TS = ["total_score"]
META = ["eid", "year", "player", "N_official", "n_players", "y", "is_mvp",
        "formula_rank", "formula_topN"]

LGB = dict(objective="binary", learning_rate=0.05, num_leaves=31,
           min_data_in_leaf=20, feature_fraction=0.85, bagging_fraction=0.85,
           bagging_freq=1, verbose=-1, num_threads=8, seed=42)
N_ROUND = 500


def event_topn_hit(df):
    """df 含 OOF proba 列 + y: 每赛事 top N_official 内官方成员占比."""
    s = []
    for eid, g in df.groupby("eid"):
        top = set(g.nlargest(int(g["N_official"].iloc[0]), "proba")["player"])
        hit = g.loc[g["y"] == 1, "player"].isin(top).sum()
        s.append(hit / int(g["y"].sum()))
    return float(np.mean(s))


def event_mvp(df):
    hit = tot = 0
    for eid, g in df.groupby("eid"):
        tot += 1
        if g.loc[g["proba"].idxmax(), "is_mvp"] == 1:
            hit += 1
    return hit / tot if tot else 0.0


def run_model(df, feats, tag):
    X = df[feats].copy()
    # 纯数值, bool→float; NaN 保留 (LGB 原生处理空段)
    for c in X.columns:
        if X[c].dtype == bool:
            X[c] = X[c].astype(float)
    y = df["y"].values
    gkf = GroupKFold(n_splits=5)
    groups = df["eid"].values
    df = df.copy()
    df["proba"] = np.nan
    oof_auc = []
    for tr, va in gkf.split(X, y, groups):
        m = lgb.train(LGB, lgb.Dataset(X.iloc[tr], y[tr]), num_boost_round=N_ROUND)
        df.iloc[va, df.columns.get_loc("proba")] = m.predict(X.iloc[va],
                                                             num_iteration=N_ROUND)
        # fold AUC (logistic)
        from sklearn.metrics import roc_auc_score
        oof_auc.append(roc_auc_score(y[va], df.loc[va, "proba"]))
    # 全池/边界池 AUC 直接在 OOF 上重算 (保证单折不泄漏)
    auc_all = roc_auc_score(y, df["proba"])
    # 边界池: 每赛事仅保留 formula_rank <= max(3*N, 15) 的选手
    bd = df[df.apply(lambda r: r["formula_rank"] <= max(3 * r["N_official"], 15), axis=1)]
    auc_bd = roc_auc_score(bd["y"], bd["proba"])
    res = {
        "tag": tag, "n_feat": len(feats),
        "auc_all": auc_all, "auc_fold_mean": float(np.mean(oof_auc)),
        "auc_boundary": auc_bd,
        "topn_hit": event_topn_hit(df),
        "mvp": event_mvp(df),
        "proba": df[["eid", "player", "y", "is_mvp", "N_official", "proba",
                     "formula_rank"]],
    }
    return res


def main():
    df = pd.read_pickle(DS)
    pos = df[df["y"] == 1]
    print(f"样本 {len(df)} 选手 × {df['eid'].nunique()} 赛事 | 正 {len(pos)} "
          f"({df['y'].mean()*100:.1f}%) | 官方名单平均 {df['N_official'].mean():.1f} 人")
    # 生产对照: 公式自身 in_topn (同数据集, y=1 里 formula_topN 占比)
    prod_topn = pos["formula_topN"].mean() * 100
    print(f"公式对照: in_topn={prod_topn:.2f}%  mvp top1={pos.groupby('eid')['is_mvp'].first().mean()*100:.2f}%  "
          f"(生产 eval 同口径 in_topn 86.32%)")
    print()

    models = [
        ("M0  仅公式分 total_score", TS),
        ("M1  原始输入 (无公式/无baseline)", RAW),
        ("M2  原始 + baseline (公式外字段)", RAW + BL),
        ("M3  全特征 (RAW+BL+FM+TS)", RAW + BL + FM + TS),
    ]
    results, probas = [], {}
    for tag, feats in models:
        print(f"== {tag}  ({len(feats)} 维) ==")
        r = run_model(df, feats, tag)
        print(f"  AUC 全池={r['auc_all']:.4f} (fold均 {r['auc_fold_mean']:.4f}) | "
              f"AUC 边界池={r['auc_boundary']:.4f}")
        print(f"  赛事内重排 in_topn={r['topn_hit']*100:.2f}% | mvp top1={r['mvp']*100:.2f}%")
        results.append(r)
        probas[tag] = r["proba"]
        print()

    print("=" * 60)
    print(f"{'模型':<38}{'AUC全':>7}{'AUC边界':>8}{'in_topn':>8}{'mvp':>7}")
    print(f"{'公式(生产对照)':<38}{'-':>7}{'-':>8}{prod_topn:>7.2f}%"
          f"{pos.groupby('eid')['is_mvp'].first().mean()*100:>6.2f}%")
    for r in results:
        print(f"{r['tag']:<38}{r['auc_all']:>7.3f}{r['auc_boundary']:>8.3f}"
              f"{r['topn_hit']*100:>7.2f}%{r['mvp']*100:>6.2f}%")
    pd.to_pickle(probas, "/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/oof_probas.pkl")

    # M3 特征重要性
    X = df[RAW + BL + FM + TS]
    m = lgb.train(LGB, lgb.Dataset(X, df["y"]), num_boost_round=N_ROUND)
    imp = pd.Series(m.feature_importance("gain"), index=X.columns).sort_values(ascending=False)
    print("\nM3 特征重要性 (gain) top 20:")
    for k, v in imp.head(20).items():
        print(f"  {k:<28}{v:>10.0f}")


if __name__ == "__main__":
    main()
