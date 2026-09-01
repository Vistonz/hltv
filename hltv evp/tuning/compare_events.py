"""逐赛事对比: 精调2 (cma_refine_best.json) vs 生产 EVP_CONFIG.

输出每个参与评估赛事的 in_topn/mvp/ordered/mismatch 变化,
重点标出: mvp 失败场次、ordered 大幅变化、in_topn 变化、mismatch 恶化.
用法: .venv/bin/python tuning/compare_events.py [--json /path/cma_refine_best.json]
"""
import copy
import io
import json
import contextlib
import os
import sys

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ef  # noqa: E402


def eval_with(cfg, cache, official, ordered, slug2nick):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return ef.eval_cfg(cfg, cache, official, ordered, slug2nick,
                           discard_ordered=ef.DISCARD_ORDERED)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else (
        "/home/hongbin/.claude/jobs/75f6c437/tmp/cma_refine_best.json")
    base = json.load(open(src))
    new_cfg = copy.deepcopy(evp_exp.EVP_CONFIG)
    for p, v in base["params"].items():
        node = new_cfg
        ks = p.split(".")
        for k in ks[:-1]:
            node = node[k]
        node[ks[-1]] = v

    slug2nick = ef.load_slug2nick()
    official = ef.load_official()
    ordered = ef.load_ordered()
    cache = ef.load_cache(official)

    prod = eval_with(evp_exp.EVP_CONFIG, cache, official, ordered, slug2nick)
    new = eval_with(new_cfg, cache, official, ordered, slug2nick)

    pe_p, pe_n = prod["per_event"], new["per_event"]
    eids = sorted(pe_p, key=lambda e: (ef._event_year(int(e)) or 0, int(e)))

    print(f"{'eid':<6}{'年':<5}{'N':>3} {'in_topn':>11} {'mvp':>4} {'ord_2值':>8} "
          f"{'mis':>8}  {'变化'}")

    n_mvp_lost = n_mvp_gain = 0
    n_in_up = n_in_dn = 0
    n_ord_delta = 0
    rows = []
    for eid in eids:
        p, n = pe_p[eid], pe_n[eid]
        year = ef._event_year(int(eid)) or 0
        N = p["official"]
        in_p, in_n = p["topN_ok"], n["topN_ok"]
        m_p, m_n = p["mvp_ok"], n["mvp_ok"]
        op = (p["ord_hit"], p["ord_tot"])
        on = (n["ord_hit"], n["ord_tot"])
        mis_p, mis_n = p["miss"], n["miss"]
        changes = []
        if m_n != m_p:
            changes.append(f"mvp {'✗→✓' if m_n and not m_p else '✓→✗'}")
            if m_n and not m_p:
                n_mvp_gain += 1
            else:
                n_mvp_lost += 1
        if in_n != in_p:
            changes.append(f"in{in_p}→{in_n}")
            if in_n > in_p:
                n_in_up += 1
            else:
                n_in_dn += 1
        ord_str = f"{op[0]}/{op[1]}"
        ord_s = f"{on[0]}/{on[1]}"
        if op != on:
            n_ord_delta += 1
            changes.append(f"ord {ord_str}→{ord_s}")
        if abs(mis_n - mis_p) > 1e-6:
            changes.append(f"mis {mis_p:.2f}→{mis_n:.2f}")
        flag = "⚠" if m_n != m_p or (in_n < in_p) or abs(mis_n - mis_p) > 1.0 else " "
        rows.append((eid, year, N, in_n, in_p, m_n, m_p, on, op, mis_n, mis_p, flag,
                     "; ".join(changes) if changes else "-"))

    # 排序: mvp 变化在前, 其次 in_topn 下降, 其次 mismatch 恶化
    rows.sort(key=lambda r: (0 if r[5] != r[6] else 1,     # mvp 变化在前
                             0 if r[3] < r[4] else 1,     # in_topn 下降在前
                             0 if r[9] > r[10] + 1.0 else 1))

    for eid, year, N, in_n, in_p, m_n, m_p, on, op, mis_n, mis_p, flag, ch in rows:
        in_s = f"{in_n}/{N}" if in_n != in_p else f"{in_n}/{N}"
        m_s = "✓" if m_n else "✗"
        if m_n != m_p:
            m_s = f"{'✓' if m_p else '✗'}→{'✓' if m_n else '✗'}"
        ord_n = f"{on[0]}/{on[1]}" if on[1] else "-"
        print(f"{eid:<6}{year:<5}{N:>3} {in_s:>7}{'':>4} {m_s:>4} {ord_n:>8} "
              f"{mis_n:>8.2f}  {flag}{ch}")

    print("\n=== 汇总 ===")
    print(f"mvp: 生产 {prod['mvp_n']}/{prod['mvp_tot']} → 精调 {new['mvp_n']}/{new['mvp_tot']} "
          f"(丢失 {n_mvp_lost} 场, 挽回 {n_mvp_gain} 场)")
    print(f"in_topn: 生产 {prod['in_hit']}/{prod['in_tot']} → 精调 {new['in_hit']}/{new['in_tot']} "
          f"(+{n_in_up} 场, -{n_in_dn} 场)")
    print(f"ordered 二值: 生产 {prod['ord_hit']}/{prod['ord_tot']} → 精调 {new['ord_hit']}/{new['ord_tot']} "
          f"({n_ord_delta} 场变化)")
    print(f"mismatch 总和: 生产 {prod['mismatch']:.2f} → 精调 {new['mismatch']:.2f}")


if __name__ == "__main__":
    main()
