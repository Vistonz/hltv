"""全量评估器 (详情页官方名单口径) — 以赛事详情页 MVP/EVP 名单为准.

数据源 (均为权威, 详情页优先级最高):
  - database/event/official_evp_lists.xlsx: 详情页提取的 MVP + EVP (无序 TopN 集合)
  - official_ordered_evp.xlsx: 新闻有序名单 (仅当与详情页集合一致时用于 ordered 指标)
  - /tmp/slug2nick.json: slug -> [nickname变体] (从新闻 HTML 提取)
  - raw_event_{id}_data.xlsx: 每赛事 raw (选手按图表现)

评估集: 有 raw + 有详情页名单的赛事 (全量, 不止 58 个有序赛事).
指标:
  - in_topn (核心): 官方名单成员 ⊆ 算法 top N (N = 官方人数)
  - mvp_ok: 官方 MVP == 算法第1
  - ordered: 仅对 (新闻有序 且 与详情页集合一致) 的赛事: 官方名单[i] ∈ 算法 top[:i+1]
  - mismatch 分数差: 漏选 + 挤占 的累计分差 (每赛事平均, 仅报告不再计入 obj)

obj = W_in*in_topn*100 + W_ord*ordered*100 + W_mvp*mvp_ok*100
      (mismatch 已停用: 老赛事评分尺度与近两年不统一, 跨年代分数差不可比, 用户 2026-08-31 拍板移除)
"""
import json
import os
import re
import sys

import pandas as pd

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402

BASE = "/home/hongbin/Desktop/hltv/database/event"
OFF_XLSX = os.path.join(BASE, "official_evp_lists.xlsx")
ORD_XLSX = os.path.join(BASE, "official_ordered_evp.xlsx")
SLUG2NICK = "/tmp/slug2nick.json"

# 新 obj 权重 (mismatch 已停用, 见 docstring)
# 2026-08-31 用户指令: MVP 预测正确翻倍加分 → W_MVP 0.2 → 0.4
W_ORD, W_IN, W_MVP = 1.0, 0.5, 0.4

# 差异过大的新闻有序赛事 (详情页为准, 不参与 ordered 指标, 但仍参与 in_topn/mvp/mismatch)
# 由 extract_all_lists.py 对比自动标出到 /tmp/discard_ordered.json; 此处可覆盖.
DISCARD_ORDERED = set()
_DISCARD_FILE = "/tmp/discard_ordered.json"
if os.path.exists(_DISCARD_FILE):
    try:
        DISCARD_ORDERED = set(json.load(open(_DISCARD_FILE)))
    except Exception:
        pass


def norm_name(s):
    """归一化选手名: 小写, 去零宽空格/引号/特殊字符."""
    s = str(s).strip().lower()
    s = s.replace("⁠", "").replace("⁡", "").replace("﻿", "")
    s = re.sub(r"[\"“”' ​]", "", s)
    return s


def load_slug2nick():
    return {s: {norm_name(n) for n in nicks}
            for s, nicks in json.load(open(SLUG2NICK)).items()}


def load_official():
    """详情页官方名单: {eid: (mvp_slug, [evp_slugs...])}. 无序 TopN 集合."""
    df = pd.read_excel(OFF_XLSX)
    official = {}
    for _, r in df.iterrows():
        eid = int(r["ID"])
        mvp = str(r["MVP"]).strip() if pd.notna(r.get("MVP")) else ""
        evps = []
        for i in range(1, 16):
            col = f"EVP{i}"
            if col in r and pd.notna(r[col]):
                v = str(r[col]).strip()
                if v and v != "nan":
                    evps.append(v)
        official[eid] = (mvp, evps)
    return official


def load_ordered():
    """新闻有序名单: {eid: [mvp?, evp1, ...]}. 用于 ordered 指标 (需与详情页一致).

    注意: 2018-2022 老赛事新闻文章是纯 EVP 有序名单 (不含 MVP), 首位被误存为 MVP 列.
    评估时: 若新闻集合 == 详情页 EVP 集合 → 有序序列 = [详情页MVP] + [新闻EVP顺序];
            若新闻集合 == 详情页全名单 → 直接 [新闻顺序] (2025+ 含 MVP).
    """
    if not os.path.exists(ORD_XLSX):
        return {}
    df = pd.read_excel(ORD_XLSX)
    ordered = {}
    for _, r in df.iterrows():
        eid = int(r["ID"])
        names = [str(r["MVP"])] + [str(r[f"EVP{i}"]) for i in range(1, 11)
                                   if pd.notna(r.get(f"EVP{i}")) and str(r[f"EVP{i}"])]
        # 归一化为小写 slug (新闻提取时可能有 REZ/Xyp9x 大小写, 详情页全小写)
        names = [norm_name(n.strip()) for n in names if n.strip() and n != "nan"]
        ordered[eid] = names
    return ordered


def build_name_index(players, needed_slugs, slug2nick):
    """选手名集合 → slug 映射 (仅覆盖 needed_slugs).

    主策略: slug 自身归一化后直接匹配 summary 昵称 (raw 数据昵称几乎=slug);
    补充1: slug2nick 变体 (覆盖大小写/拼写差异);
    补充2: 剥离连字符/下划线的模糊匹配 (NBK- ↔ nbk, GeT_RiGhT ↔ get-right), 仅当唯一.
    """
    p2norm = {}
    stripped = {}
    for p in players:
        n = norm_name(p)
        p2norm.setdefault(n, p)
        s = n.replace("-", "").replace("_", "").replace(" ", "")
        stripped.setdefault(s, set()).add(p)
    slug_map = {}
    for s in needed_slugs:
        nl = norm_name(s)
        if nl in p2norm:
            slug_map[s] = p2norm[nl]
            continue
        hit = None
        for n in slug2nick.get(s, ()):
            if norm_name(n) in p2norm:
                hit = p2norm[norm_name(n)]
                break
        if hit:
            slug_map[s] = hit
            continue
        sl = nl.replace("-", "").replace("_", "").replace(" ", "")
        if sl in stripped and len(stripped[sl]) == 1:
            slug_map[s] = next(iter(stripped[sl]))
    return slug_map


def eval_cfg(cfg, cache, official, ordered, slug2nick, discard_ordered=None,
             quiet=True):
    """cache: {eid: raw_df}. 返回指标 dict."""
    discard_ordered = discard_ordered or set()
    in_hit = in_tot = 0
    ord_hit = ord_tot = 0
    mvp_ok_n = mvp_tot = 0
    mis_sum = 0.0
    per_event = {}
    for eid, (mvp_slug, evp_slugs) in official.items():
        if eid not in cache:
            continue
        slugs = ([mvp_slug] if mvp_slug else []) + list(evp_slugs)
        slugs = [s for s in slugs if s]
        if not slugs:
            continue
        N = len(slugs)
        summary, *_ = evp_exp.run_experiment(None, None, None, cfg=cfg,
                                             save=False, raw_df=cache[eid])
        df = summary.sort_values("total_score", ascending=False).reset_index(drop=True)
        slug_map = build_name_index(df["player"], slugs, slug2nick)
        official_players = []
        missing = []
        for s in slugs:
            if s in slug_map:
                official_players.append(slug_map[s])
            else:
                missing.append(s)
        if len(official_players) < N:
            if not quiet:
                print(f"  [{eid}] 名单匹配缺失 {len(missing)}: {missing}")
            continue  # raw 覆盖不全 → 该赛事无法评估
        # in_topn
        topN = set(df["player"].head(N))
        in_hit += sum(1 for p in official_players if p in topN)
        in_tot += N
        # mvp_ok
        mvp_tot += 1
        if official_players and official_players[0] == df["player"].iloc[0]:
            mvp_ok_n += 1
        # mismatch 分数差
        scores = dict(zip(df["player"], df["total_score"]))
        in_names = set(official_players)
        algo_topN = topN
        off_scores = [scores[p] for p in official_players if p in scores]
        algo_scores = [scores[p] for p in algo_topN]
        e_mis = 0.0
        if off_scores:
            off_min = min(off_scores)
            for p in algo_topN - in_names:
                if scores[p] > off_min:
                    e_mis += scores[p] - off_min
            if len(algo_scores) >= N:
                lineN = min(algo_scores)
                for p in in_names - algo_topN:
                    if scores[p] < lineN:
                        e_mis += lineN - scores[p]
        mis_sum += e_mis
        # ordered (新闻有序 且 与详情页一致 且 未被剔除)
        # 新闻存昵称, 详情页存 slug → 经 slug2nick 变体把新闻昵称映射为实际选手.
        # 两种形态:
        #   A) 新闻集合 ⊆ 详情页全名单 且 含 MVP → [新闻顺序] (2025+ 完整或截断名单)
        #   B) 新闻集合 == 详情页 EVP 集合 → [详情MVP] + [新闻EVP顺序] (老赛事纯EVP)
        #   否则 (新闻含非官方成员如 7732 的 'im', 名单不一致) → 不参与 ordered.
        ord_i = ord_t = 0
        if eid in ordered and eid not in discard_ordered:
            news_seq = ordered[eid]
            # 昵称变体 → 实际选手 (来自本赛事详情 slug 的变体集)
            nick2player = {}
            for s, p in slug_map.items():
                for n in slug2nick.get(s, ()):
                    nl = norm_name(n)
                    if nl:
                        nick2player.setdefault(nl, set()).add(p)
            mapped = []
            ok = True
            for n in news_seq:
                cand = nick2player.get(norm_name(n))
                if cand and len(cand) == 1:
                    mapped.append(next(iter(cand)))
                else:
                    ok = False  # 昵称歧义或无映射 → 该赛事有序不可靠
                    break
            seq = None
            if ok:
                mapped_set = set(mapped)
                full_players = set(official_players)
                evp_players = set(slug_map[s] for s in evp_slugs if s in slug_map)
                if (official_players and official_players[0] in mapped_set
                        and mapped_set <= full_players):
                    seq = mapped  # A: 含 MVP 的完整/截断新闻名单
                elif mapped_set == evp_players:
                    seq = [official_players[0]] + mapped  # B: MVP前置 + 新闻EVP顺序
            if seq:
                for i, p in enumerate(seq):
                    ord_t += 1
                    if p in set(df["player"].head(i + 1)):
                        ord_i += 1
        ord_hit += ord_i
        ord_tot += ord_t
        per_event[str(eid)] = {
            "official": N, "matched": len(official_players),
            "topN_ok": sum(1 for p in official_players if p in topN),
            "ordered": ord_i / ord_t if ord_t else None,
            "miss": e_mis,
        }
    in_v = in_hit / in_tot if in_tot else 0
    ord_v = ord_hit / ord_tot if ord_tot else 0
    mvp_v = mvp_ok_n / mvp_tot if mvp_tot else 0
    n_ev = len(per_event)
    mis_avg = mis_sum / n_ev if n_ev else 0
    # mismatch 已停用 (跨年代分数尺度不统一, 用户 2026-08-31): 仅报告不进入 obj.
    obj = W_ORD * ord_v * 100 + W_IN * in_v * 100 + W_MVP * mvp_v * 100
    return {"obj": obj, "in_topn": in_v, "in_hit": in_hit, "in_tot": in_tot,
            "ordered": ord_v, "ord_hit": ord_hit, "ord_tot": ord_tot,
            "mvp_ok": mvp_v, "mvp_n": mvp_ok_n, "mvp_tot": mvp_tot,
            "mismatch": mis_sum, "n_ev": n_ev, "per_event": per_event}


# 7912 (BLAST Open London 2025 Finals) 官方 EVP 名单覆盖整个 London 赛事(含 Online 阶段):
#   donk 仅打 Online 被选为 EVP, 其余 4 人有 Online + LAN 决赛.
#   → 评估须用主赛事 7907 (blast-open-london-2025) 全量 raw (Online+决赛, 80 选手).
#   已验证 7912 决赛 raw 的 QF/SF/GF (50/40/50 行) 与 7907 完全一致, 7912 是 7907 子集.
#   7907 自身无官方名单(不进评估集), 别名无双重计数.
RAW_ALIAS = {7912: 7907}


def load_cache(official):
    cache = {}
    for eid in official:
        src = RAW_ALIAS.get(eid, eid)
        raw = os.path.join(BASE, str(src), f"raw_event_{src}_data.xlsx")
        if os.path.exists(raw):
            cache[eid] = pd.read_excel(raw)
    return cache


if __name__ == "__main__":
    cfg = dict(evp_exp.EVP_CONFIG)
    overrides = {}
    if len(sys.argv) > 1:
        for pair in sys.argv[1].split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                try:
                    v = float(v)
                except ValueError:
                    pass
                overrides[k] = v
    cfg.update(overrides)
    slug2nick = load_slug2nick()
    official = load_official()
    ordered = load_ordered()
    cache = load_cache(official)
    r = eval_cfg(cfg, cache, official, ordered, slug2nick,
                 discard_ordered=DISCARD_ORDERED, quiet=False)
    print(f"overrides={overrides}")
    print(f"评估赛事={r['n_ev']}  in_topn={r['in_topn']:.4f} ({r['in_hit']}/{r['in_tot']}) "
          f"ordered={r['ordered']:.4f} ({r['ord_hit']}/{r['ord_tot']}) "
          f"mvp={r['mvp_ok']:.3f} ({r['mvp_n']}/{r['mvp_tot']}) "
          f"mismatch={r['mismatch']:.2f}  obj={r['obj']:.4f}")
    # 未匹配赛事检查
    for eid, e in sorted(r["per_event"].items()):
        if e["matched"] < e["official"]:
            print(f"  ⚠ {eid}: 官方{e['official']} 匹配{e['matched']} 人")
