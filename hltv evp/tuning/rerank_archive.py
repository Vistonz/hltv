"""离线重排 CMA 搜索档案 — 换 objective 权重不必重跑搜索.

原理: obj = W_ORD·100·ord + W_IN·100·in + W_MVP·100·mvp − W_MIS·mis.
每个配置的四个分量 (ord/in/mvp/mis) 都与权重无关 → 同一批评估点在任意权重下都能
精确重算 obj, 只是线性组合的系数变了. 所以:

  - CMA 跑一次, 把每点的分量存进 <TAG>_archive.jsonl (search_cma.py 已实现);
  - 之后想知道换个 W_IN 时的最优解 → 直接重排档案, **零次重新评估**.

注意: 重排只能回答"在这批已评估的点里谁最好", 不能替代对新权重重新搜索 —— 但配合
"排序不变性"(见记忆 evp-calibration-rules) 足以判断旧峰顶是否仍然成立.

用法:
  .venv/bin/python tuning/rerank_archive.py <space.json> <archive.jsonl> [W_IN_LIST]
  例: ... tuning/win045/cma45_space.json tuning/win045/cma45_archive.jsonl 1.0,0.7,0.45,0.3,0.0
"""
import json
import os
import sys


def obj_at(row, w_in, w_ord, w_mvp, w_mis):
    return (w_ord * row["ord"] * 100 + w_in * row["in"] * 100
            + w_mvp * row["mvp"] * 100 - w_mis * row["mis"])


def decode(uvec, space):
    """u∈[0,1]^n → {参数路径: 值}."""
    out = {}
    for (path, lo, hi), u in zip(space, uvec):
        u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
        out[path] = lo + u * (hi - lo)
    return out


def main():
    space_json, archive_jsonl = sys.argv[1], sys.argv[2]
    meta = json.load(open(space_json))
    space = [(p, lo, hi) for p, lo, hi in meta["space"]]
    w_ord, w_mvp, w_mis = meta["w_ord"], meta["w_mvp"], meta["w_mis"]
    rows = [json.loads(l) for l in open(archive_jsonl) if l.strip()]
    wins = ([float(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3
            else [1.0, 0.7, 0.45, 0.3, 0.0])

    print(f"档案 {len(rows)} 点 | 空间 {len(space)} 维 | 存档时 W_IN={meta['win']}")
    print(f"固定权重 W_ORD={w_ord} W_MVP={w_mvp} W_MIS={w_mis}\n")
    print(f"{'W_IN':>6} {'argmax obj':>11} {'ord':>7} {'in':>7} {'mvp':>6} {'mis':>8}  排序是否变")
    base_rank = None
    for w in wins:
        scored = sorted(((obj_at(r, w, w_ord, w_mvp, w_mis), i) for i, r in enumerate(rows)),
                        key=lambda t: -t[0])
        best_obj, best_i = scored[0]
        r = rows[best_i]
        top5 = [i for _, i in scored[:5]]
        rank_key = tuple(top5)
        changed = "" if base_rank is None else ("= 同" if rank_key == base_rank else "≠ 变了")
        base_rank = base_rank or rank_key
        print(f"{w:>6.2f} {best_obj:>11.4f} {r['ord']:>7.4f} {r['in']:>7.4f} "
              f"{r['mvp']:>6.3f} {r['mis']:>8.2f}  {changed}")

    # 当前档位的最优解参数 (只打印相对锚点变化 >2% 的项)
    w_now = meta["win"]
    scored = sorted(((obj_at(r, w_now, w_ord, w_mvp, w_mis), i) for i, r in enumerate(rows)),
                    key=lambda t: -t[0])
    best_i = scored[0][1]
    params = decode(rows[best_i]["u"], space)
    anchor = decode(meta["x0u"], space)
    print(f"\n当前 W_IN={w_now} 档案最优 (obj={scored[0][0]:.4f}) 相对锚点漂移 >2% 的参数:")
    n = 0
    for p, v in params.items():
        a = anchor[p]
        if a and abs(v / a - 1.0) > 0.02:
            print(f"  {p:<28} {v:>10.5f}  (x{v/a:.3f})")
            n += 1
    if n == 0:
        print("  (无 — 最优解就是锚点本身, 搜索未找到更优点)")


if __name__ == "__main__":
    main()
