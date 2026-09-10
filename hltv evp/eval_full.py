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
  - line_mismatch (两段产品线绝对线判据, 2026-09-09 用户定案:
      产品段 CS:GO→4.0 / CS2→4.5, 取代 2026-09-01 的三档年线). 每赛事:
      hi = 官方入选最低分, lo = 官方落选最高分,
      e_mis = max(0, line−hi) + max(0, lo−line). 全 0 = 线以上的人都入选、线以下都没入选.

obj = W_ord*ordered*100 + W_in*in_topn*100 + W_mvp*mvp_ok*100 − W_MIS*line_mismatch
      (mismatch 曾停用: 跨年代分数尺度不统一 → 改用分年代线吸收官方标准迁移, 2026-09-01 加回)
      (2026-09-10: W_in 1.0 → 0.45 — in_topn 覆盖 255/255 场却判别力弱却占近半权重,
       降权以让"顺序"信号主导; 0.45 使 W_in/(W_ord+W_in)=31% ≈ 用户要求的"占30%左右";
       保留非零值维持选人约束, 见下方权重常量注释)
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
# 2026-08-31 晚: in_topn 权重加满 → W_IN 0.5 → 1.0
# 2026-09-10 用户指令: in_topn 权重过高, 稀释了顺序信号 → 降权至占"顺序相关权重"约 30%.
#   口径 (用户原话): "比例占30%左右, 权重大概应该在0.45左右"
#     → W_IN/(W_ORD+W_IN) = 0.45/1.45 = 31.0% (顺序 1.0 : 选人 0.45).
#   依据: ① 各候选对照中 in_topn 几乎不动 (9 轴 +0.25pp / 机制 +0.11pp), 却占 obj 近半权重;
#         ② 覆盖不对称 —— in_topn 255/255 场, ordered 仅 58/255 (CS:GO 17/190, CS2 41/65),
#            两分法下 in 只做"选人"约束的配角, 不做主导;
#         ③ 去掉它的极端口径 (W_IN=0) 下 9 轴样本外仍两折全负 (−3.40/−3.34), 说明降权不改变
#            此前的参数/机制定案结论;
#         ④ 不能归零: ordered 在 |d|≥3 后饱和归零且对官方人缺位不罚, 无法单独承担选人约束.
#   EVP_W_IN 环境变量可覆盖 (调权实验用), 默认 0.45.
W_ORD, W_MVP = 1.0, 0.4
W_IN = float(os.environ.get("EVP_W_IN", "0.45"))
W_MIS = 0.1   # 分年代线 mismatch 惩罚权重 (2026-09-01: 0.5→0.2→0.1, 命中主导/mismatch 弱约束)
# ordered 距离加权 (2026-09-01 双向口径, 用户定): 每判定点 score = max(0, 1 - DIST_ALPHA·|d|)
#   d = pos - (i+1) = 官方第 i 人在算法榜名次偏离理想位置的幅度; 提前/挤出对称惩罚.
#   距离越远扣分越多; |d| ≥ 1/DIST_ALPHA 归零. 替代原二值"前缀包含"命中率.
#   α=0.33: 差1名得0.67, 差2名得0.34, 差3名及以上归零 (用户 2026-09-01 定案).
DIST_ALPHA = 0.33

# 两段产品线 (2026-09-09 用户指令: 分代从三档年线改为产品段 CS:GO/CS2)
CS2_START_DATE = "2023-09-27"           # CS2 首发日 (含) → CS2 段
# CS2 单段线 4.5 定案依据 (Phase1.5 基线, 2026-09-09): 63 CS2 评估赛事在现 42 参数下,
#   均匀单线 4.5 的 mismatch 和最小 (70.9 < 5.0 的 73.9 < 4.0 的 79.0), obj 161.18 两段最优.
SEG_LINE = {"csgo": 4.0, "cs2": 4.5}

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
    if not os.path.exists(SLUG2NICK):
        return {}  # /tmp 清理后缺失: 主策略 (slug 归一化直接匹配) 仍可用, 仅缺昵称变体补充
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
             cs2_overrides=None, quiet=True):
    """cache: {eid: raw_df}. 返回指标 dict.

    cfg: CS:GO 段配置 (= EVP_CONFIG). CS2 段事件改用
      evp_exp.cfg_for('cs2', base=cfg, cs2_overrides=cs2_overrides) — base 的 42 核心 +
      CS2 专属机制轴权重. cs2_overrides=None → 模块 CS2_OVERRIDES (生产默认);
      {} → 强制 CS2 机制关 (闸门基线); dict → 搜索逐点传入的 CS2 覆写.
      (2026-09-10 前此参数受 "CS:GO 逐字节冻结" 约束; 用户决策「C 解冻写回」后已解除,
       42 核参数现为两段共用 —— 见记忆 evp-final-config-20260910.)
    """
    discard_ordered = discard_ordered or set()
    in_hit = in_tot = 0
    ord_hit = ord_tot = 0
    ord_dist = 0.0   # ordered 距离加权得分总和 (双向, 2026-09-01 新口径)
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
        # 两套分拆 (2026-09-09): CS2 事件用 base+CS2 覆写, CS:GO 事件用 cfg 原样
        # (段间隔离: CS:GO 不 merge CS2 机制轴 —— 架构层面, 与冻结策略无关).
        if segment_of(eid) == "cs2":
            use_cfg = evp_exp.cfg_for("cs2", base=cfg, cs2_overrides=cs2_overrides)
        else:
            use_cfg = cfg
        summary, *_ = evp_exp.run_experiment(None, None, None, cfg=use_cfg,
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
        # line_mismatch: 分年代绝对线判据 (官方入选最低 ≥ 线 ≥ 官方落选最高)
        scores = dict(zip(df["player"], df["total_score"]))
        in_names = set(official_players)
        out_names = set(df["player"]) - in_names
        line = segment_line(segment_of(eid))
        e_mis = 0.0
        if in_names:
            hi = min(scores[p] for p in in_names if p in scores)
            e_mis += max(0.0, line - hi)
        else:
            hi = None
        if out_names:
            lo = max(scores[p] for p in out_names if p in scores)
            e_mis += max(0.0, lo - line)
        else:
            lo = None
        mis_sum += e_mis
        # ordered (新闻有序 且 与详情页一致 且 未被剔除)
        # 新闻存昵称, 详情页存 slug → 经 slug2nick 变体把新闻昵称映射为实际选手.
        # 两种形态:
        #   A) 新闻集合 ⊆ 详情页全名单 且 含 MVP → [新闻顺序] (2025+ 完整或截断名单)
        #   B) 新闻集合 == 详情页 EVP 集合 → [详情MVP] + [新闻EVP顺序] (老赛事纯EVP)
        #   否则 (新闻含非官方成员如 7732 的 'im', 名单不一致) → 不参与 ordered.
        ord_i = ord_t = 0
        ord_dist_e = 0.0   # 本赛事距离加权得分和 (双向, 每点 max(0, 1-DIST_ALPHA·|d|))
        if eid in ordered and eid not in discard_ordered:
            news_seq = ordered[eid]
            # 昵称变体 → 实际选手. 最可靠变体是 raw summary 的 player 昵称本身 (几乎=slug),
            # slug2nick (/tmp 可清理) 只作补充变体. 2026-09-01 改为不依赖 /tmp.
            nick2player = {}
            for s, p in slug_map.items():
                for n in ([p] + list(slug2nick.get(s, ()))):
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
                rank_of = {p: i + 1 for i, p in enumerate(df["player"])}
                for i, p in enumerate(seq):
                    ord_t += 1
                    pos = rank_of.get(p)
                    if pos is None:
                        continue  # 官方人在算法榜缺位, 不计
                    d = pos - (i + 1)
                    ord_dist_e += max(0.0, 1.0 - DIST_ALPHA * abs(d))
                    if p in set(df["player"].head(i + 1)):
                        ord_i += 1
        ord_hit += ord_i
        ord_tot += ord_t
        ord_dist += ord_dist_e
        per_event[str(eid)] = {
            "official": N, "matched": len(official_players),
            "topN_ok": sum(1 for p in official_players if p in topN),
            "mvp_ok": 1 if official_players and official_players[0] == df["player"].iloc[0] else 0,
            "ordered": ord_i / ord_t if ord_t else None,
            "ord_hit": ord_i, "ord_tot": ord_t,
            "miss": e_mis, "line": line, "hi": hi, "lo": lo,
        }
    in_v = in_hit / in_tot if in_tot else 0
    ord_v = ord_dist / ord_tot if ord_tot else 0   # 距离加权率 (新口径) 替代二值命中率
    mvp_v = mvp_ok_n / mvp_tot if mvp_tot else 0
    n_ev = len(per_event)
    mis_avg = mis_sum / n_ev if n_ev else 0
    # line_mismatch 分年代线惩罚进入 obj (2026-09-01 加回).
    obj = W_ORD * ord_v * 100 + W_IN * in_v * 100 + W_MVP * mvp_v * 100 - W_MIS * mis_sum
    return {"obj": obj, "in_topn": in_v, "in_hit": in_hit, "in_tot": in_tot,
            "ordered": ord_v, "ord_dist": ord_dist,
            "ord_hit": ord_hit, "ord_tot": ord_tot,
            "mvp_ok": mvp_v, "mvp_n": mvp_ok_n, "mvp_tot": mvp_tot,
            "mismatch": mis_sum, "n_ev": n_ev, "per_event": per_event}


# 7912 (BLAST Open London 2025 Finals) 官方 EVP 名单覆盖整个 London 赛事(含 Online 阶段):
#   donk 仅打 Online 被选为 EVP, 其余 4 人有 Online + LAN 决赛.
#   → 评估须用主赛事 7907 (blast-open-london-2025) 全量 raw (Online+决赛, 80 选手).
#   已验证 7912 决赛 raw 的 QF/SF/GF (50/40/50 行) 与 7907 完全一致, 7912 是 7907 子集.
#   7907 自身无官方名单(不进评估集), 别名无双重计数.
RAW_ALIAS = {7912: 7907}

_META_CACHE = {}


def _meta_start(eid):
    """赛事 meta start_date 字符串 (RAW_ALIAS 别名解析). 惰性缓存, 只首次读盘. 失败 → None."""
    if eid in _META_CACHE:
        return _META_CACHE[eid]
    src = RAW_ALIAS.get(eid, eid)
    meta = os.path.join(BASE, str(src), f"event_{src}_meta.json")
    d = None
    try:
        with open(meta, encoding="utf-8") as f:
            d = json.load(f).get("start_date")
    except Exception:
        pass
    _META_CACHE[eid] = d
    return d


def _event_year(eid):
    """赛事开始年份 (meta start_date 前4位). 解析失败 → None. 供按年分析/分组."""
    d = _meta_start(eid)
    if not d:
        return None
    try:
        return int(str(d).strip()[:4])
    except (TypeError, ValueError):
        return None


def segment_of(eid):
    """赛事产品段: start_date >= CS2_START_DATE → 'cs2', 否则 'csgo'. 解析失败按 'cs2' 保守."""
    d = _meta_start(eid)
    if d is None:
        return "cs2"
    return "cs2" if str(d).strip()[:10] >= CS2_START_DATE else "csgo"


def segment_line(segment):
    """两段产品线 EVP 标准线 (2026-09-09 定案): CS:GO→4.0, CS2→4.5. 未知段按 CS2 线保守."""
    return SEG_LINE.get(segment, SEG_LINE["cs2"])


def load_cache(official):
    cache = {}
    for eid in official:
        src = RAW_ALIAS.get(eid, eid)
        raw = os.path.join(BASE, str(src), f"raw_event_{src}_data.xlsx")
        if os.path.exists(raw):
            cache[eid] = pd.read_excel(raw)
            _meta_start(eid)  # 预填充 meta start_date 缓存 (segment_of/_event_year 共用)
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
