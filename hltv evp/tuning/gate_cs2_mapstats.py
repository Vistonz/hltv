"""Phase 3b 收尾闸门 — CS2 mapstats 机制采纳判定 (2026-09-09).

⚠ 弃用 (2026-09-10): 机制键已迁到 CS2_OVERRIDES (cfg_for 两套架构)。历史存档勿重跑,
改用 tuning/decision_cs2_axes.py + tuning/robust_cs2_axes.py 判采纳。

读 cs2mapstats_best.json 的 (CS2_CLUTCH_W, CS2_DPR_W), 对照机制全 0 基线:
  1. 全量 obj (两段线) 净增益 > 0 → 采纳; 否则报"机制无净增益, 停在基线".
  2. CS:GO 冻结保证 (结构性): 每个 CS:GO raw 上 mapstats_player_adjust 返回 {}
     (机制以 CS2 专属列存在为触发前提, CS:GO 无列 → 永不触发). 逐列扫描铁证.
  3. CS2 分赛事明细: per_event 差分 (topN/mvp/mismatch 变化) → 增益来源可解释.

用法: .venv/bin/python tuning/gate_cs2_mapstats.py [best.json]
"""
import os
import sys
import json
import copy

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ev  # noqa: E402

BEST = "/home/hongbin/.claude/jobs/75f6c437/tmp/cs2mapstats_best.json"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else BEST
    d = json.load(open(src))
    cw, dw = d["pair"]
    print(f"闸门候选: CS2_CLUTCH_W={cw}  CS2_DPR_W={dw}  (obj(CS2-only)={d['obj']:.4f})")

    official = ev.load_official()
    ordered = ev.load_ordered()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()

    cfg0 = copy.deepcopy(evp_exp.EVP_CONFIG)
    cfg1 = copy.deepcopy(evp_exp.EVP_CONFIG)
    cfg1["CS2_CLUTCH_W"], cfg1["CS2_DPR_W"] = cw, dw

    # --- 1) 全量 obj 对照 ---
    r0 = ev.eval_cfg(cfg0, cache, official, ordered, slug2nick,
                     discard_ordered=ev.DISCARD_ORDERED)
    r1 = ev.eval_cfg(cfg1, cache, official, ordered, slug2nick,
                     discard_ordered=ev.DISCARD_ORDERED)
    delta = r1["obj"] - r0["obj"]
    print(f"\n[1] 全量两段 obj  基线={r0['obj']:.4f}  最终={r1['obj']:.4f}  Δ={delta:+.4f}")
    print(f"      in_topn {r0['in_topn']*100:.2f}→{r1['in_topn']*100:.2f}  "
          f"ordered {r0['ordered']*100:.2f}→{r1['ordered']*100:.2f}  "
          f"mvp {r0['mvp_ok']*100:.2f}→{r1['mvp_ok']*100:.2f}  "
          f"mismatch {r0['mismatch']:.2f}→{r1['mismatch']:.2f}")
    adopt = delta > 0.0
    print(f"      → {'✔ 净增益, 可采纳' if adopt else '✘ 无净增益 — 停在基线, 机制不采纳'}")

    # --- 2) CS:GO 冻结 (结构性铁证) ---
    go_events = [eid for eid, raw in cache.items() if ev.segment_of(eid) == "csgo"]
    viol = [eid for eid in go_events if evp_exp.mapstats_player_adjust(cache[eid], cfg1)]
    print(f"\n[2] CS:GO 冻结验尸: {len(go_events)} 个 CS:GO raw 上机制均返回 {{}}; "
          f"触发风险: {viol if viol else '无 (结构铁证)'}")

    # --- 3) CS2 分赛事明细 (从 per_event 差分) ---
    print("\n[3] CS2 评估赛事变化 (topN_ok / mvp_ok / mismatch):")
    n_chg = 0
    for eid_s, e1 in sorted(r1["per_event"].items(), key=lambda kv: kv[0]):
        e0 = r0["per_event"][eid_s]
        t = (e0["topN_ok"], e1["topN_ok"])
        m = (e0["mvp_ok"], e1["mvp_ok"])
        ms = (round(e0["miss"], 3), round(e1["miss"], 3))
        if t != (t[1], t[1]) or t[0] != t[1] or m[0] != m[1] or abs(ms[0] - ms[1]) > 1e-6:
            n_chg += 1
            tag = "topN" if t[0] != t[1] else ""
            tag += " mvp" if m[0] != m[1] else ""
            tag += " mis" if ms[0] != ms[1] else ""
            print(f"    {eid_s}: topN {t[0]}→{t[1]}  mvp {m[0]}→{m[1]}  "
                  f"mis {ms[0]:.2f}→{ms[1]:.2f}  [{tag.strip()}]")
    if n_chg == 0:
        print("    (无官方判定变化 — 机制改了排序但未改判定; 若净增益来自 mismatch 则可能有误)")
    return adopt


if __name__ == "__main__":
    main()
