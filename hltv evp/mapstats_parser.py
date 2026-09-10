"""HLTV mapstatsid (performance 单图) HTML 解析 -> 每图选手级统计. (2026 CS2 performance 页)

被 hltv evp.py Step1 (CS2 赛事每图补抓) 与 tuning/learn/parse_mapstats_events.py (CLI 演示) 共用.

页面结构:
  A) round-swing-player 块 x10: roster (pid/nick/team/图级 swing total)
  B) highlighted-player 卡片 x10: 每卡内嵌 FusionCharts JSON, 7 label: KPR/DPR/KAST/MK rating/
     Swing/ADR/Rating 3.0 (displayValue=真实值). 卡片头部 /player/{pid}/ + <span class=player-nick>
  C) tooltip_player{pid}_match_round{N}: 局末比分. 列内 <div class="team"> 带 team-logo title=队名,
     固定 side0-first (经实测两选手同列同值, 非"己队优先")
  D) tooltip_player{pid}_round{N}_event{K}: 每局内每事件 (10 份冗余, 按 (round,event) 合并取并集)

build_summary(html) -> (rows{pid: {...}}, meta). 每选手行含 7 统计 + 事件导出:
  kills/won_kills/lost_kills/kprw (赢局内击杀/胜局数), swing_added(Σ+), swing_given(Σ|−|), swing_total.
"""
import re
import collections

WANT = ["KPR", "DPR", "KAST", "MK rating", "Swing", "ADR", "Rating 3.0"]
COL = {"KPR": "kpr", "DPR": "dpr", "KAST": "kast", "MK rating": "mk_rating",
       "Swing": "swing", "ADR": "adr", "Rating 3.0": "rating30"}
KILL_RE = re.compile(r"^(\S+) killed (\S+)$")


# ---------------------------------------------------------------- A) roster
def parse_roster(h):
    """round-swing-player 块 -> {pid: (nick, team, swing_total)}."""
    roster = {}
    for blk in re.findall(r'<div class="round-swing-player.*?(?=<div class="round-swing-player"|$)', h, re.S):
        pm = re.search(r'data-toggle-value="PlayerId\(playerId=(\d+)\)"', blk)
        nick = re.search(r'<div class="player-nick text-ellipsis">([^<]+)</div>\s*'
                         r'<div class="player-round-swing-total">([^<]*)</div>', blk)
        team = re.search(r'class="bodyShot-team"[^>]*title="([^"]+)"', blk)
        if pm and nick:
            roster[pm.group(1)] = (nick.group(1).strip(),
                                   (team.group(1) if team else "?").strip(),
                                   nick.group(2).strip())
    return roster


# --------------------------------------------------- B) highlighted-player 卡片
def parse_player_cards(h):
    """highlighted-player 卡片 -> {pid: {kpr:.., dpr:.., kast:.., mk_rating:.., swing:.., adr:.., rating30:..}}."""
    out = {}
    for c in re.finditer(r'<div class="highlighted-player">', h):
        seg = h[c.start():c.start() + 8000]
        pm = re.search(r'/player/(\d+)/', seg)
        nm = re.search(r'<span class="player-nick">([^<]+)</span>', seg)
        if not (pm and nm):
            continue
        pid, nick = pm.group(1), nm.group(1).strip()
        got = {}
        for lab, val in re.findall(r'&quot;label&quot;:&quot;([^&]+?)&quot;[^>]*?&quot;displayValue&quot;:&quot;([^&]+?)&quot;', seg):
            if lab in WANT and lab not in got:
                got[lab] = val.strip()
            if len(got) == len(WANT):
                break
        if got:
            out[pid] = {COL[k]: v for k, v in got.items()}
    return out


# --------------------------------------- C) 局末比分: match_round tooltip, 列头带队名
def parse_scores(h):
    """-> score_by_team[r] = {teamName: score}. 每列 team-logo title 绑定 team-stat, 固定 side0-first."""
    score_by_team = {}
    for m in re.finditer(r'id="tooltip_player\d+_match_round(\d+)">', h):
        r = int(m.group(1))
        end = h.find('<div class="tooltip"', m.end())
        inner = h[m.end():end if end != -1 else len(h)]
        pairs = re.findall(r'<div class="team"><img[^>]*title="([^"]+)"[^>]*>\s*'
                           r'<div class="team-stat">(\d+)</div>', inner)
        if len(pairs) == 2:
            score_by_team[r] = {t: int(s) for t, s in pairs}
    return score_by_team


# ------------------------------------------- D) 事件流 (round,event) 合并
def parse_events(h):
    """-> events_by_round[r][k] = {title, alive, prob, swings:[(nick,val)], equip:[(team,val)]}."""
    eb = collections.defaultdict(dict)
    for m in re.finditer(r'<div class="tooltip" id="tooltip_player\d+_round(\d+)_event(\d+)">', h):
        r, k = int(m.group(1)), int(m.group(2))
        end = h.find('<div class="tooltip"', m.end())
        inner = h[m.end():end if end != -1 else len(h)]
        it = eb[r].setdefault(k, {"title": None, "alive": None, "prob": None,
                                  "swings": [], "equip": [], "_eq": set()})
        t = re.search(r'<strong class="title">([^<]+)</strong>', inner)
        if t and it["title"] is None:
            it["title"] = t.group(1).strip()
        a = re.search(r'>(\d+) vs (\d+)<', inner)
        if a and it["alive"] is None:
            it["alive"] = (int(a.group(1)), int(a.group(2)))
        p = re.findall(r'<div class="team-stat">([\d.]+)%</div>', inner)
        if len(p) >= 2 and it["prob"] is None:
            it["prob"] = (float(p[0]), float(p[1]))
        for nn, st in re.findall(r'<div class="player-nick">([^<]+)</div>\s*<span class="stat">([^<]*)</span>', inner):
            nn, st = nn.strip(), st.strip()
            em = re.match(r"(.{1,24}) equipment value:\s*$", nn)   # 装备值 (Round started): "X equipment value:" -> val
            if em:
                key = (em.group(1).strip(), st)
                if key not in it["_eq"]:
                    it["_eq"].add(key)
                    it["equip"].append(key)
                continue
            pair = (nn, st)
            if pair not in it["swings"]:
                it["swings"].append(pair)
    return eb


# ---------------------------------------------------------------- 汇总
def build_summary(h):
    """-> (rows{pid: {...}}, meta{...})."""
    roster = parse_roster(h)
    cards = parse_player_cards(h)
    scores = parse_scores(h)
    eb = parse_events(h)
    teams = sorted({v[1] for v in roster.values()})

    def winner_team(r):
        cur = scores.get(r)
        if not cur:
            return None
        prev = scores.get(r - 1) or {t: 0 for t in teams}
        for team in teams:
            if cur[team] > prev[team]:
                return team
        return None

    team_wins = collections.Counter()
    for r in scores:
        w = winner_team(r)
        if w:
            team_wins[w] += 1

    agg = collections.defaultdict(lambda: {"kills": 0, "won_kills": 0, "lost_kills": 0,
                                           "swing_pos": 0.0, "swing_neg": 0.0})
    nick2pid = {v[0]: pid for pid, v in roster.items()}
    for r in sorted(eb):
        wt = winner_team(r)
        for it in eb[r].values():
            mm = KILL_RE.match(it["title"] or "")
            if mm and mm.group(1) in nick2pid:
                pid = nick2pid[mm.group(1)]
                agg[pid]["kills"] += 1
                key = "won_kills" if (wt and roster[pid][1] == wt) else "lost_kills"
                agg[pid][key] += 1
            for nn, st in it["swings"]:
                if nn not in nick2pid:
                    continue
                try:
                    v = float(st.rstrip("%"))
                except ValueError:
                    continue
                agg[nick2pid[nn]]["swing_pos" if v >= 0 else "swing_neg"] += v

    n_rounds = max(scores) if scores else 0
    out = {}
    for pid, (nick, team, sw_total) in roster.items():
        c = cards.get(pid, {})
        a = agg[pid]
        wins = team_wins.get(team, 0)
        row = {"pid": pid, "nick": nick, "team": team,
               "kprw": round(a["won_kills"] / wins, 3) if wins else "",
               "won_kills": a["won_kills"], "lost_kills": a["lost_kills"],
               "kills": a["kills"], "swing_added": round(a["swing_pos"], 2),
               "swing_given": round(-a["swing_neg"], 2), "swing_total": sw_total}
        row.update(c)
        out[pid] = row
    meta = {"n_rounds": n_rounds, "teams": teams, "n_players": len(roster), "team_wins": dict(team_wins)}
    return out, meta


# ------------------------------------------------- 数字归一化 + 入库列
def _f(v):
    """'0.79' / '+4.04%' / '83.3%' / '76.0' / '' / None -> float 或 None."""
    if v is None:
        return None
    s = str(v).replace("%", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def enrich_cols(r):
    """选手级 summary 行 -> raw 行新增的 map_* 数字列 (并入 hltv evp.py 的 raw dict)."""
    return {
        "map_kpr": _f(r.get("kpr")), "map_dpr": _f(r.get("dpr")),
        "map_kast": _f(r.get("kast")), "map_mk_rating": _f(r.get("mk_rating")),
        "map_swing_total": _f(r.get("swing")), "map_adr": _f(r.get("adr")),
        "map_rating30": _f(r.get("rating30")),
        "map_kprw": _f(r.get("kprw")),
        "map_swing_added": _f(r.get("swing_added")), "map_swing_given": _f(r.get("swing_given")),
        "map_kills": int(r["kills"]) if r.get("kills") not in (None, "") else None,
        "map_won_kills": int(r["won_kills"]) if r.get("won_kills") not in (None, "") else None,
    }
