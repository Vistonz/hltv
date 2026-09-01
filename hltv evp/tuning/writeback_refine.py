"""把 CMA 精调 best.json 的扁平参数写回 evp_experiment.py 的 EVP_CONFIG.

用法: .venv/bin/python tuning/writeback_refine.py [best.json]
支持嵌套 key (GROUP_CAP_EXEMPT.soft 等, 单行 dict): 行内同时含 parent 与 child 才替换.
每个 key 必须唯一匹配一行, 否则中止 (防误改).
"""
import json
import re
import sys

SRC = "/home/hongbin/Desktop/hltv/hltv evp/evp_experiment.py"
BEST = (sys.argv[1] if len(sys.argv) > 1
        else "/home/hongbin/.claude/jobs/75f6c437/tmp/cma_refine_best.json")

params = json.load(open(BEST))["params"]
lines = open(SRC, encoding="utf-8").read().splitlines(keepends=True)

unmatched = []
for key, val in params.items():
    child = key.split(".")[-1]
    if "." in key:
        parent = key.split(".", 1)[0]
        idxs = [i for i, l in enumerate(lines)
                if f'"{parent}"' in l and f'"{child}":' in l]
    else:
        idxs = [i for i, l in enumerate(lines)
                if f'"{key}":' in l and not l.strip().startswith("#")]
    if len(idxs) != 1:
        unmatched.append((key, len(idxs)))
        continue
    i = idxs[0]
    new_val = repr(round(float(val), 12))
    pat = re.compile(r'("' + re.escape(child) + r'":\s*)[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')
    newline, n = pat.subn(lambda m: m.group(1) + new_val, lines[i], count=1)
    if n == 0:
        unmatched.append((key, -1))  # 当前值非纯数字 (如表达式), 拒绝覆盖
        continue
    lines[i] = newline

if unmatched:
    for k, n in unmatched:
        print(f"⚠ {k}: 匹配行数={n} 或值非数字")
    raise SystemExit(f"写回中止: {len(unmatched)} 个 key 未唯一匹配")

open(SRC, "w", encoding="utf-8").writelines(lines)
print(f"✓ 已写回 {len(params)} 个参数 → evp_experiment.py")
