"""CS2 全候选轴回归 — 决策脚本 (Task #96).

CMA (search_cs2_axes_cma) 在 CS2-only obj 上拟合出 9 轴权重, 但共线轴同时进入时
权重会出现符号对消 (KAST −0.34 / KPR +0.25 / swing_sum −0.27 …) = 过拟合信号.
本脚本做三层剥离, 判断"真增量"落在哪:
  1. 全量两段 obj: 生产 2 轴 (162.3726) vs 9 轴候选 → 净增益才采纳.
  2. CS2-only 对照三态: 生产 / 9轴全量 / **CMA点只留 kprw_e+dpr 两轴** (隔离
     "CMA 把原两轴推大" 与 "新增轴" 各自贡献; 旧 2D 网格 refine 没扫过这两点:
     kprw_e>0.27 与 dpr 负侧都未测).
  3. 逐轴消融 (CS2 子集, CS:GO 恒常数): 在 9 轴全量上把每轴归零看 obj 损失.
     |损失|~0 → 共线噪声; 明显 → 真增量. 据此给写回建议.

用法: .venv/bin/python tuning/decision_cs2_axes.py [cs2axes_best.json]
"""
import contextlib
import io
import json
import os
import sys

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import evp_experiment as evp_exp  # noqa: E402
import eval_full as ev  # noqa: E402

BEST = "/home/hongbin/.claude/jobs/75f6c437/tmp/cs2axes_best.json"
AXES = ["KPRW_E", "DPR", "KPRW_AVG", "KPR", "KAST", "MK", "ADR", "SWING_SUM", "SWING_AVG"]


def main():
    w = json.load(open(BEST))["weights"]     # 键 = 裸轴名 ("KPRW_E", …)
    ov9 = {f"CS2_{ax}_W": w.get(ax, 0.0) for ax in AXES}
    print("CMA 9 轴权重:")
    for ax in AXES:
        print(f"    CS2_{ax}_W = {ov9[f'CS2_{ax}_W']:+.4f}")

    official = ev.load_official()
    ordered = ev.load_ordered()
    cache = ev.load_cache(official)
    slug2nick = ev.load_slug2nick()
    cache_cs2 = {eid: df for eid, df in cache.items() if ev.segment_of(eid) == "cs2"}
    kw = dict(discard_ordered=ev.DISCARD_ORDERED)

    def _silent(fn, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*a, **k)

    def ev_cs2(ov):
        return _silent(ev.eval_cfg, evp_exp.EVP_CONFIG, cache_cs2, official, ordered,
                       slug2nick, cs2_overrides=ov, **kw)

    def ev_full(ov):
        return _silent(ev.eval_cfg, evp_exp.EVP_CONFIG, cache, official, ordered,
                       slug2nick, cs2_overrides=ov, **kw)

    # --- 1) 全量 obj: 生产 vs 9 轴候选 ---
    fp = ev_full(None)
    fb = ev_full(ov9)
    print(f"\n[1] 全量两段 obj  生产={fp['obj']:.4f} (期望 162.3726)  9轴候选={fb['obj']:.4f}  "
          f"Δ={fb['obj']-fp['obj']:+.4f}")
    print(f"      in {fp['in_topn']*100:.2f}→{fb['in_topn']*100:.2f}  "
          f"ord {fp['ordered']*100:.2f}→{fb['ordered']*100:.2f}  "
          f"mvp {fp['mvp_ok']*100:.2f}→{fb['mvp_ok']*100:.2f}  "
          f"mis {fp['mismatch']:.2f}→{fb['mismatch']:.2f}")
    assert abs(fp["obj"] - 162.3726) < 1e-3

    # --- 2) CS2-only 三态剥离 ---
    print("\n[2] CS2-only obj 三态 (隔离新轴 vs 原两轴推大):")
    c_prod = ev_cs2(None)
    c_9 = ev_cs2(ov9)
    ov2 = {f"CS2_{ax}_W": (ov9[f'CS2_{ax}_W'] if ax in ("KPRW_E", "DPR") else 0.0)
           for ax in AXES}
    c_2 = ev_cs2(ov2)
    print(f"    A 生产 2 轴(0.19/-0.04)      = {c_prod['obj']:.4f}   (期望 184.5893)")
    print(f"    B CMA点只留 kprw_e+dpr       = {c_2['obj']:.4f}   Δvs A {c_2['obj']-c_prod['obj']:+.4f}")
    print(f"    C 9 轴全量                  = {c_9['obj']:.4f}   Δvs B {c_9['obj']-c_2['obj']:+.4f}"
          f"  ← 新增 7 轴的边际")
    # B vs A 的完整 obj (潜在写回点)
    f2 = ev_full(ov2)
    print(f"    → B 在全量上的 obj = {f2['obj']:.4f} (Δvs 生产 {f2['obj']-fp['obj']:+.4f})")

    # --- 3) 逐轴消融 (CS2 子集): 在 9 轴全量上把每轴归零 ---
    print("\n[3] 逐轴消融 (CS2 子集, 归零该轴其余保持):")
    abl = {}
    for ax in AXES:
        ovz = dict(ov9)
        ovz[f"CS2_{ax}_W"] = 0.0
        rz = ev_cs2(ovz)
        abl[ax] = c_9["obj"] - rz["obj"]   # >0 去掉变差 = 该轴有正贡献
        tag = "★ 真增量" if abl[ax] > 0.05 else ("噪声(~0)" if abl[ax] > -0.05 else "负贡献?")
        print(f"    CS2_{ax}_W={ov9[f'CS2_{ax}_W']:+.4f} 归零 → {rz['obj']:.4f}  (损失 {abl[ax]:+.4f})  [{tag}]")
    keep = [ax for ax in AXES if abl[ax] > 0.05]
    print(f"\n[4] 建议保留轴 (消融损失>0.05): {keep if keep else '(无)'}")
    # 写回候选的完整 obj (用于最终判定)
    rec = [ax for ax in AXES if ax in ("KPRW_E", "DPR")] + keep
    rec = list(dict.fromkeys(rec))  # 去重保序
    ov_rec = {f"CS2_{ax}_W": (ov9[f'CS2_{ax}_W'] if ax in rec else 0.0) for ax in AXES}
    fr = ev_full(ov_rec)
    print(f"    推荐写回轴 {rec} 全量 obj = {fr['obj']:.4f} (Δvs 生产 {fr['obj']-fp['obj']:+.4f})")


if __name__ == "__main__":
    main()
