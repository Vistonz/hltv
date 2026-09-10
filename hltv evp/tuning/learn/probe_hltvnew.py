"""最小化试跑新版 hltvnew: 所有 filter 缩成单赛事 8301, 验证能否真取到数据.
用法: hltv evp/.venv/bin/python tuning/learn/probe_hltvnew.py
"""
import os
import sys

sys.path.insert(0, "/home/hongbin/Desktop/hltv/hltv year")
os.chdir("/home/hongbin/Desktop/hltv/hltv year")

import hltvnew  # noqa: E402

BASE = "?event=8301"
OUT = "/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/probe_8301.xlsx"
print("run_yearly_scrape with 8301-only filters, chrome 152...", flush=True)
hltvnew.run_yearly_scrape(
    eventfilter=BASE, bigeventfilter=BASE, eliteeventfilter=BASE,
    supereliteeventfilter=BASE, arenafilter=BASE,
    minMapCountfilter="&minMapCount=0", minrating=0.9,
    file_path=OUT, chrome_version=152,
)
print("DONE", flush=True)
