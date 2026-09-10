"""导出可学性诊断样本集: 每(赛事, 选手)一行, 摊平 原始单图聚合特征 + 公式中间量 + 公式总分 + 官方标签.

目的: 回答"官方相对我们公式的残差是否可学".
  - 正样本 = 官方 EVP 名单成员 (详情页 official_evp_lists.xlsx, 经 eval_full 同一别名匹配)
  - 负样本 = 同赛事 raw 其余全部选手
特征组:
  - x_*      raw/map_all 单图聚合 (rating/rd/胜率/阶段/对手强度) — 公式的输入重表示
  - bl_*     match_baseline_rating 类 (rating − 赛前基线 = 超预期) — 公式从未使用的字段
  - fm_*     summarize_players 中间量 (group/playoff 双轨分段分等) — 公式解构
  - total_score / formula_rank — 公式最终输出
标签/排序:
  - y=1 官方名单成员; is_mvp; N_official; formula_topN = 公式 rank<=N (即生产 in_topn 判定)
产物: tuning/learn/dataset.pkl
用法: ./.venv/bin/python tuning/learnability_export.py
"""
import contextlib
import io
import os
import sys
from concurrent.futures import ProcessPoolExecutor

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())

import numpy as np
import pandas as pd  # noqa: E402

import eval_full as ef  # noqa: E402
import evp_experiment as evp_exp  # noqa: E402

OUT = "/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/dataset.pkl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

_WORKER = {}


def _worker_init():
    os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
    sys.path.insert(0, os.getcwd())
    import eval_full as ef2
    import evp_experiment as E2
    _WORKER["ef"] = ef2
    _WORKER["E"] = E2
    _WORKER["slug2nick"] = ef2.load_slug2nick()


def _run_experiment(eid, raw_df):
    E = _WORKER["E"]
    # 可学性诊断的"公式输出"须为纯公式口径 → 裸 EVP_CONFIG (CS2 机制-off);
    # mapstats 机制加成属公式外字段, 增量已由独立预检 (2 轴 / 9 轴回归) 单独验证.
    cfg = dict(E.EVP_CONFIG)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return E.run_experiment(None, None, None, cfg=cfg, save=False, raw_df=raw_df)


def agg_map_all(map_all):
    """map_all 单图表现 → 每选手原始聚合 (公式输入重表示). 空时返回空 dict."""
    g = map_all.groupby("player")
    r110 = (map_all["rating"] >= 1.10).astype(int)
    r130 = (map_all["rating"] >= 1.30).astype(int)
    r = pd.DataFrame({
        "player": map_all["player"], "rating": map_all["rating"],
        "win": map_all["win"].astype(int),
        "r110": r110.values, "r130": r130.values,
        "rd": map_all["round_differential"],
        "n_vs_top5": (map_all["opponent_rank"] <= 5).astype(int).values,
        "n_vs_top10": (map_all["opponent_rank"] <= 10).astype(int).values,
    })
    win_bo_bo = map_all[map_all["win_bo"]].groupby("player")["bo_id"].nunique()
    po = ~map_all["match_stage"].isin(evp_exp.EVP_CONFIG["GROUP_STAGES"])
    gf = map_all["match_stage"] == "Grand final"
    opp_rank = map_all["opponent_rank"].replace({999: np.nan, 0: np.nan})
    f = g.agg(n_maps=("rating", "size"))
    f["rating_mean"] = g["rating"].mean()
    f["rating_max"] = g["rating"].max()
    f["rating_std"] = g["rating"].std()
    f["win_frac"] = r.groupby("player")["win"].mean()
    f["frac_r110"] = r.groupby("player")["r110"].mean()
    f["frac_r130"] = r.groupby("player")["r130"].mean()
    f["rd_mean"] = r.groupby("player")["rd"].mean()
    f["n_win_bo"] = win_bo_bo.reindex(f.index).fillna(0).astype(int)
    # 阶段拆分
    gg = map_all[~po].groupby("player")
    pg = map_all[po].groupby("player")
    fg = map_all[gf].groupby("player")
    f["n_grp"] = gg["rating"].size()
    f["rating_grp_mean"] = gg["rating"].mean()
    f["n_po"] = pg["rating"].size()
    f["rating_po_mean"] = pg["rating"].mean()
    f["n_gf"] = fg["rating"].size()
    f["rating_gf_mean"] = fg["rating"].mean()
    # 对手强度
    opp = map_all.assign(opp_rank=opp_rank.values)
    f["opp_rank_mean"] = opp.groupby("player")["opp_rank"].mean()
    f["n_vs_top5"] = r.groupby("player")["n_vs_top5"].sum()
    f["n_vs_top10"] = r.groupby("player")["n_vs_top10"].sum()
    rv5 = map_all[map_all["opponent_rank"] <= 5].groupby("player")["rating"].mean()
    f["rating_vs_top5_mean"] = rv5
    f = f.reset_index()
    return f.to_dict("records") if len(f) else []


def agg_baseline(raw):
    """match_baseline_rating 类: 公式从未使用的字段 → 超预期信号."""
    b = raw.groupby("player")["match_baseline_rating"].mean()
    over = (raw["rating"] - raw["match_baseline_rating"])
    odf = pd.DataFrame({"player": raw["player"], "over": over.values})
    f = pd.DataFrame({"base_mean": b})
    f["over_mean"] = odf.groupby("player")["over"].mean()
    f["over_frac"] = (odf["over"] > 0).astype(int).groupby(odf["player"]).mean()
    return f.reset_index().to_dict("records")


def _match_official(eid, summary, ef_mod):
    """官方名单 → raw player 名集合/顺序. 返回 (matched_players列表[首位=mvp?], N, missing)."""
    official = ef_mod.load_official()
    mvp_slug, evp_slugs = official[eid]
    slugs = ([mvp_slug] if mvp_slug else []) + list(evp_slugs)
    slugs = [s for s in slugs if s]
    if not slugs:
        return [], 0, []
    players = list(summary["player"])
    slug_map = ef_mod.build_name_index(players, slugs, _WORKER["slug2nick"])
    matched, missing = [], []
    for s in slugs:
        if s in slug_map:
            matched.append(slug_map[s])
        else:
            missing.append(s)
    return matched, len(matched), missing


def _one_event(eid):
    ef_mod = _WORKER["ef"]
    src = ef_mod.RAW_ALIAS.get(eid, eid)
    raw_path = os.path.join(ef_mod.BASE, str(src), f"raw_event_{src}_data.xlsx")
    if not os.path.exists(raw_path):
        return None
    raw = pd.read_excel(raw_path)
    summary, _bo_all, map_all, _det = _run_experiment(eid, raw)
    matched, n_match, missing = _match_official(eid, summary, ef_mod)
    N = len(matched)
    if N == 0 or n_match < N:
        return None  # 匹配不全 → 同 eval_full 丢弃
    official_set = set(matched)
    mvp_name = matched[0]  # 匹配顺序 = [mvp] + evps
    map_recs = {p["player"]: p for p in agg_map_all(map_all)}
    bl_recs = {p["player"]: p for p in agg_baseline(raw)}
    sdf = summary.reset_index(drop=True)
    n_players = len(sdf)
    rows = []
    year = ef_mod._event_year(eid) or 0
    for _, r in sdf.iterrows():
        p = r["player"]
        d = {"eid": eid, "year": year, "player": p,
             "N_official": N, "n_players": n_players,
             "y": 1 if p in official_set else 0,
             "is_mvp": 1 if p == mvp_name else 0,
             "formula_rank": int(r["rank"]),
             "formula_topN": 1 if r["rank"] <= N else 0,
             "total_score": float(r["total_score"])}
        d.update(map_recs.get(p, {}))
        d.update(bl_recs.get(p, {}))
        for c in ["n_bo_games", "group_win_maps", "group_len_factor",
                  "group_exempt", "group_bo_total", "group_effective",
                  "group_soft_capped", "playoff_bo_total", "playoff_soft_capped"]:
            v = r[c]
            d["fm_" + c] = float(v) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else (1.0 if v is True else (0.0 if v is False else v))
        rows.append(d)
    return rows


def main():
    official = ef.load_official()
    ordered = ef.load_ordered()
    eids = [eid for eid in official
            if os.path.exists(os.path.join(ef.BASE, str(ef.RAW_ALIAS.get(eid, eid)),
                                          f"raw_event_{ef.RAW_ALIAS.get(eid, eid)}_data.xlsx"))]
    print(f"候选赛事 {len(eids)}")
    all_rows = []
    with ProcessPoolExecutor(max_workers=12, initializer=_worker_init) as ex:
        for i, res in enumerate(ex.map(_one_event, eids, chunksize=4)):
            if res:
                all_rows.extend(res)
            if (i + 1) % 40 == 0:
                print(f"  {i+1}/{len(eids)} 赛事, 累计 {len(all_rows)} 行")
    df = pd.DataFrame(all_rows)
    df.to_pickle(OUT)
    print(f"\n✓ 样本集: {len(df)} 选手 × {df['eid'].nunique()} 赛事  → {OUT}")
    print("正样本(官方名单成员):", int(df["y"].sum()),
          f"({df['y'].mean()*100:.1f}%), 含 MVP:", int(df["is_mvp"].sum()))
    print("公式 in_topn 复现(生产对照):", f"{df.groupby('eid')['formula_topN'].mean().mean()*100:.2f}%")


if __name__ == "__main__":
    main()
