"""CS2 全候选轴回归采纳闸门 (Task #96, 2026-09-09).

读 search_cs2_axes_cma.py 产出的 cs2axes_best.json (9 轴拟合权重), 对照生产 2 轴定案:
  1. 全量两段 obj: 生产 162.3726 (基准) vs 全轴候选 → 净增益 > 0 才采纳.
  2. 逐轴消融: 把拟合权重逐轴归零 (其余保持), 测 obj 损失 — |损失|~0 的轴是噪声
     (共线冗余), 提议修剪回 2 轴或少数有效轴; 损失明显的轴才是真增量.
  3. CS:GO 冻结复验 (架构保证, 抽样即可 + 结构性铁证全扫).
  4. CS2 分赛事明细: topN/mvp/mismatch 变化来源可解释.

用法: .venv/bin/python tuning/gate_cs2_axes.py [cs2axes_best.json]
"""
import json
import os
import sys

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ev  # noqa: E402

BEST = "/home/hongbin/.claude/jobs/75f6c437/tmp/cs2axes_best.json"
PROD_OBJ = 162.3726          # 生产 2 轴全量 obj (已写回验证)
PROD_CS2 = 184.5893          # 生产 2 轴 CS2-only obj
AXES = ["KPRW_E", "DPR", "KPRW_AVG", "KPR", "KAST", "MK", "ADR", "SWING_SUM", "SWING_AVG"]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else BEST
    d = json.load(open(src))
    w = d["weights"]   # 键 = 裸轴名
    print(f"候选: obj(CS2-only)={d['obj']:.4f}  tag={d.get('tag')}  权重:")
    for ax in AXES:
        print(f"    CS2_{ax}_W = {w.get(ax, 0.0):+.4f}")

    official = ev.load_official()
    ordered = ev.load_ordered()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()
    # 机制全轴的候选覆写 (含 0 值轴 = 显式关)
    ov = {f"CS2_{ax}_W": w.get(ax, 0.0) for ax in AXES}

    # --- 1) 全量 obj: 生产 vs 候选 ---
    rp = ev.eval_cfg(evp_exp.EVP_CONFIG, cache, official, ordered, slug2nick,
                     discard_ordered=ev.DISCARD_ORDERED, cs2_overrides=None)
    rc = ev.eval_cfg(evp_exp.EVP_CONFIG, cache, official, ordered, slug2nick,
                     discard_ordered=ev.DISCARD_ORDERED, cs2_overrides=ov)
    delta = rc["obj"] - rp["obj"]
    print(f"\n[1] 全量两段 obj  生产={rp['obj']:.4f} (期望 {PROD_OBJ})  候选={rc['obj']:.4f}  "
          f"Δ={delta:+.4f}")
    print(f"      in {rp['in_topn']*100:.2f}→{rc['in_topn']*100:.2f}  "
          f"ord {rp['ordered']*100:.2f}→{rc['ordered']*100:.2f}  "
          f"mvp {rp['mvp_ok']*100:.2f}→{rc['mvp_ok']*100:.2f}  "
          f"mis {rp['mismatch']:.2f}→{rc['mismatch']:.2f}")
    assert abs(rp["obj"] - PROD_OBJ) < 1e-3, f"生产锚点失配 {rp['obj']}"
    adopt = delta > 0.0
    print(f"      → {'✔ 净增益, 可采纳' if adopt else '✘ 无净增益 — 停在生产 2 轴'}")

    # --- 2) 逐轴消融 (在候选全轴上把某轴归零) ---
    print("\n[2] 逐轴消融 (归零该轴, 其余保持候选值):")
    abl = {}
    for ax in AXES:
        ov2 = dict(ov)
        ov2[f"CS2_{ax}_W"] = 0.0
        ra = ev.eval_cfg(evp_exp.EVP_CONFIG, cache, official, ordered, slug2nick,
                         discard_ordered=ev.DISCARD_ORDERED, cs2_overrides=ov2)
        abl[ax] = rc["obj"] - ra["obj"]   # >0: 该轴贡献为正 (去掉变差)
        tag = "★ 真增量" if abl[ax] > 0.05 else ("噪声(~0)" if abl[ax] > -0.05 else "负贡献?")
        print(f"    CS2_{ax}_W 归零 → obj {ra['obj']:.4f}  (损失 {abl[ax]:+.4f})  [{tag}]")
    keep = [ax for ax in AXES if abl[ax] > 0.05]
    print(f"    → 保留轴: {keep if keep else '(无 — 建议回生产 2 轴或按符号重标定)'}")

    # --- 3) CS:GO 冻结 (结构性铁证) ---
    go = [eid for eid in cache if ev.segment_of(eid) == "csgo"]
    viol = [eid for eid in go if evp_exp.mapstats_player_adjust(cache[eid], ov)]
    print(f"\n[3] CS:GO 冻结: {len(go)} raw 上全轴覆写机制返回 {{}}; "
          f"触发 {viol if viol else '无 (架构冻结 ✔)'}")
    assert not viol

    # --- 4) CS2 分赛事判定变化 ---
    print("\n[4] CS2 评估赛事变化 (topN_ok / mvp / mis):")
    n = 0
    for eid_s, e1 in sorted(rc["per_event"].items(), key=lambda kv: kv[0]):
        e0 = rp["per_event"].get(eid_s)
        if not e0:
            continue
        t, m, ms = (e0["topN_ok"], e1["topN_ok"]), (e0["mvp_ok"], e1["mvp_ok"]), \
            (round(e0["miss"], 3), round(e1["miss"], 3))
        if t[0] != t[1] or m[0] != m[1] or abs(ms[0] - ms[1]) > 1e-6:
            n += 1
            tag = ("topN" if t[0] != t[1] else "") + (" mvp" if m[0] != m[1] else "") \
                + (" mis" if ms[0] != ms[1] else "")
            print(f"    {eid_s}: topN {t[0]}→{t[1]}  mvp {m[0]}→{m[1]}  mis {ms[0]:.2f}→{ms[1]:.2f}"
                  f"  [{tag.strip()}]")
    print(f"    (共 {n} 个 CS2 事件判定变化)" if n else "    (无判定变化)")
    return adopt


if __name__ == "__main__":
    main()
