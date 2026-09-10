"""单图 mapstats 解析 CLI (薄委托): 调 mapstats_parser.build_summary, 落两份产物并打印.

解析逻辑唯一来源: /home/hongbin/Desktop/hltv/hltv evp/mapstats_parser.py
  - {out_dir}/{out_prefix}_per_map_players.csv  每选手1行: pid/nick/team/map_label + 7统计 + 事件导出
  - {out_dir}/{out_prefix}_events.csv           逐 round,event 明细 (action/alive/winprob/equip/swings)
用法: ./.venv/bin/python tuning/learn/parse_mapstats_events.py <html> [out_dir] [map_label]
"""
import os
import sys
import csv

HERE = os.path.dirname(os.path.abspath(__file__))              # .../tuning/learn
ROOT = os.path.dirname(os.path.dirname(HERE))                   # repo 根 (含 mapstats_parser.py)
sys.path.insert(0, ROOT)
from mapstats_parser import build_summary, parse_events  # noqa: E402


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "mapstats_parivision_vs_tyloo.html")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(src))
    map_label = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(src).replace(".html", "")
    h = open(src, encoding="utf-8", errors="ignore").read()
    rows, meta = build_summary(h)

    pfile = os.path.join(out_dir, f"{map_label}_per_map_players.csv")
    fields = ["pid", "nick", "team", "map_label", "kills", "won_kills", "lost_kills", "kprw",
              "swing_total", "swing_added", "swing_given", "kpr", "dpr", "kast",
              "mk_rating", "swing", "adr", "rating30"]
    with open(pfile, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for pid in sorted(rows, key=lambda p: (rows[p]["team"], rows[p]["nick"])):
            row = dict(rows[pid], map_label=map_label)
            w.writerow({k: row.get(k, "") for k in fields})

    eb = parse_events(h)
    efile = os.path.join(out_dir, f"{map_label}_events.csv")
    with open(efile, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["round", "event", "action", "alive", "winprob", "equip", "swings"])
        for r in sorted(eb):
            for k in sorted(eb[r]):
                it = eb[r][k]
                w.writerow([r, k, it["title"], ("%dv%d" % it["alive"]) if it["alive"] else "",
                            ("%.1f/%.1f" % it["prob"]) if it["prob"] else "",
                            ";".join("%s=%s" % e for e in it["equip"]),
                            ";".join("%s %s" % s for s in it["swings"])])

    print(f"meta: n_rounds={meta['n_rounds']} teams={meta['teams']} team_wins={meta['team_wins']} n_players={meta['n_players']}")
    print(f"per_map -> {pfile}  |  events -> {efile}\n")
    hdr = (f"{'nick':11s}{'team':11s}{'kpr':>5s}{'dpr':>5s}{'kast':>6s}{'mk':>5s}{'swing':>7s}"
           f"{'adr':>6s}{'r3':>5s} | {'kills':>5s}{'KPRW':>6s}{'swing+':>7s}{'swing-':>7s}")
    print(hdr)
    print("-" * len(hdr))
    for pid in sorted(rows, key=lambda p: rows[p]["team"] + rows[p]["nick"]):
        r = rows[pid]
        print(f"{r['nick']:11s}{r['team']:11s}{r.get('kpr',''):>5s}{r.get('dpr',''):>5s}"
              f"{r.get('kast',''):>6s}{r.get('mk_rating',''):>5s}{r.get('swing',''):>7s}"
              f"{r.get('adr',''):>6s}{r.get('rating30',''):>5s} | {r['kills']:5d}"
              f"{r['kprw']:>6}{r['swing_added']:>7}{r['swing_given']:>7}")


if __name__ == "__main__":
    main()
