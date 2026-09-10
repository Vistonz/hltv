"""单赛事全字段抓取 runner (自愈): 目标赛事 -> 全池选手 -> tuning/learn/evpnew_{eid}.xlsx.

run_yearly_scrape 会把已存在 xlsx 里『同名+同图池数』的选手跳过 (增量续写), 因此
Chrome 中途崩溃后重跑同一命令即续跑. 本脚本用循环把崩掉的重启, 直到正常收尾或轮次用尽.
用法: ./.venv/bin/python tuning/learn/run_one_event.py <eid> [minrating]
"""
import os, sys, time, traceback

sys.path.insert(0, "/home/hongbin/Desktop/hltv/hltv year")
os.chdir("/home/hongbin/Desktop/hltv/hltv year")

import hltvnew  # noqa: E402

EID = sys.argv[1] if len(sys.argv) > 1 else "8301"
MR = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
OUT = f"/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/evpnew_{EID}.xlsx"
FILTER = f"?event={EID}"
MAX_ROUNDS = 14

# 之前旧的单赛事采样文件若残留同名会被当续稿, 避开
if os.path.exists(OUT):
    # 保留 (续跑场景): 重启会跳过已完成的
    pass

for rnd in range(1, MAX_ROUNDS + 1):
    print(f"\n===== round {rnd}/{MAX_ROUNDS}  eid={EID} minrating={MR} =====", flush=True)
    t0 = time.time()
    try:
        hltvnew.run_yearly_scrape(
            eventfilter=FILTER, bigeventfilter=FILTER, eliteeventfilter=FILTER,
            supereliteeventfilter=FILTER, arenafilter=FILTER,
            minMapCountfilter="&minMapCount=0", minrating=MR,
            file_path=OUT, chrome_version=152,
        )
        print(f"DONE-CLEAN round {rnd} in {time.time()-t0:.0f}s", flush=True)
        break
    except KeyboardInterrupt:
        print("KEYBOARD-INTERRUPT", flush=True)
        raise
    except Exception as e:
        kind = type(e).__name__
        print(f"CRASH round {rnd}: {kind}: {e}", flush=True)
        traceback.print_exc(limit=1)
        # 数一下已落盘行数
        try:
            from openpyxl import load_workbook
            wb = load_workbook(OUT)
            ws = wb.active
            print(f"  so-far rows (incl header): {ws.max_row}", flush=True)
        except Exception:
            pass
        time.sleep(4)
print("ALL-DONE", flush=True)
