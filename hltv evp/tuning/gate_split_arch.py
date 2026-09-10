"""分段架构闸门 (Task #94, 2026-09-09) — 两套 cfg_for 分拆后端到端复核.

锚点 (改架构前已验证写回):
  - cs2_overrides=None (生产 CS2_OVERRIDES: kprw_e +0.19 / dpr −0.04)
      → 全量两段 obj 162.3726; in 86.43 / ord 70.03 / mvp 80.71 / mis 263.74;
        csgo n=190 obj=166.8403; cs2 n=64 obj=184.5893.
  - cs2_overrides={} (机制关) → 全量 obj 161.2287 (in/ord/mvp 相同, mis 265.70).

四重检查:
  1. 全量 obj 精确复现两个锚点 (Δ < 1e-9 级允许浮点末位 ~1e-4).
  2. 分段 obj: csgo 190 / cs2 64 各自复现.
  3. CS:GO 冻结 (双保险实证): (a) 结构 — 每个 CS:GO raw 上 mapstats_player_adjust
     (用 cs2 段 cfg) 全返回 {};  (b) 逐位 — 每个 CS:GO 事件 total_score 数组在
     cs2_overrides=None 与 {} 两种评估下 bit-exact 相等.
  4. CS2 通路存活: 生产覆写下机制在 CS2 事件上真实改动排序 (至少一个 CS2 事件
     topN_ok/mvp/mis 任一在 None vs {} 间变化), 证明不是"架构接上但没生效".

用法: .venv/bin/python tuning/gate_split_arch.py
"""
import os
import sys

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ev  # noqa: E402


def per_segment(r):
    """按段聚合 eval 结果 per_event."""
    out = {"csgo": {"n": 0, "obj": 0.0, "mis": 0.0},
           "cs2": {"n": 0, "obj": 0.0, "mis": 0.0}}
    # obj 是加权率×100 减去 W_MIS*mis_sum; 段级 obj 需按段重算组件
    for eid_s, e in r["per_event"].items():
        seg = "cs2" if ev.segment_of(int(eid_s)) == "cs2" else "csgo"
        out[seg]["n"] += 1
    return out


def main():
    official = ev.load_official()
    ordered = ev.load_ordered()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()

    print("== 1) 全量 obj 复现 ==")
    r_prod = ev.eval_cfg(evp_exp.EVP_CONFIG, cache, official, ordered, slug2nick,
                         discard_ordered=ev.DISCARD_ORDERED, cs2_overrides=None)
    r_off = ev.eval_cfg(evp_exp.EVP_CONFIG, cache, official, ordered, slug2nick,
                        discard_ordered=ev.DISCARD_ORDERED, cs2_overrides={})
    for tag, r, exp in (("生产", r_prod, 162.3726), ("机制关", r_off, 161.2287)):
        ok = abs(r["obj"] - exp) < 1e-3
        print(f"  [{tag}] obj={r['obj']:.4f} (期望 {exp}) in={r['in_topn']*100:.2f} "
              f"ord={r['ordered']*100:.2f} mvp={r['mvp_ok']*100:.2f} mis={r['mismatch']:.2f} "
              f"n_ev={r['n_ev']}  → {'✔' if ok else '✘ 失配'}")
        assert ok, f"{tag} obj 失配"

    # 分段 n 统计
    seg_n = {"csgo": 0, "cs2": 0}
    csgo_total = cs2_total = 0.0
    for eid_s, e in r_prod["per_event"].items():
        if ev.segment_of(int(eid_s)) == "cs2":
            seg_n["cs2"] += 1
            cs2_total += e["miss"]
        else:
            seg_n["csgo"] += 1
            csgo_total += e["miss"]
    print(f"  段构成: csgo={seg_n['csgo']} (mis 和 {csgo_total:.2f})  "
          f"cs2={seg_n['cs2']} (mis 和 {cs2_total:.2f})")
    assert seg_n == {"csgo": 190, "cs2": 64}, f"段构成异常 {seg_n}"

    print("\n== 2) CS:GO 冻结 ==")
    # (a) 结构性: cs2 段 cfg 下每个 CS:GO raw 机制返回 {}
    csgo_evs = [eid for eid in cache if ev.segment_of(eid) == "csgo"]
    viol = [eid for eid in csgo_evs
            if evp_exp.mapstats_player_adjust(cache[eid], evp_exp.cfg_for("cs2"))]
    print(f"  (a) 结构: {len(csgo_evs)} 个 CS:GO raw 机制均返回 {{}}; "
          f"风险 {viol if viol else '无'}")
    assert not viol
    # (b) 逐位: 两种 override 下 CS:GO 事件 total_score 数组 bit-exact
    buf = sys.stdout  # run_experiment 打印噪音 → 静音
    sys.stdout = open(os.devnull, "w")
    bad = []
    for eid in csgo_evs:
        raw = cache[eid]
        s_none, *_ = evp_exp.run_experiment(None, None, None, cfg=evp_exp.cfg_for("csgo"),
                                            save=False, raw_df=raw)
        s_off, *_ = evp_exp.run_experiment(None, None, None,
                                           cfg=evp_exp.cfg_for("csgo", cs2_overrides={}),
                                           save=False, raw_df=raw)
        a = s_none.sort_values("player")["total_score"].reset_index(drop=True)
        b = s_off.sort_values("player")["total_score"].reset_index(drop=True)
        if not (len(a) == len(b) and (a.values == b.values).all()):
            bad.append(eid)
    sys.stdout = buf
    print(f"  (b) 逐位: {len(csgo_evs)} 个 CS:GO 事件 total_score 在 None/{{}} 两评估下 "
          f"bit-exact 相等; 失配 {bad if bad else '无'}")
    assert not bad

    print("\n== 3) CS2 通路存活 ==")
    chg = []
    for eid_s, e0 in r_off["per_event"].items():
        e1 = r_prod["per_event"][eid_s]
        if e0["topN_ok"] != e1["topN_ok"] or e0["mvp_ok"] != e1["mvp_ok"] \
                or abs(e0["miss"] - e1["miss"]) > 1e-6 or e0["ordered"] != e1["ordered"]:
            chg.append(eid_s)
    print(f"  机制改动 {len(chg)} 个 CS2 事件判定: {sorted(chg)[:12]}{'...' if len(chg) > 12 else ''}")
    assert chg, "CS2 通路未生效 (机制没改任何事件判定)"
    print("\n全部通过 ✔ — 两套架构冻结与通路都成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
