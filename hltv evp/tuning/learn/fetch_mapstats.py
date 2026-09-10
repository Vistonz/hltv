"""抓一个 HLTV stats/matches/performance/mapstatsid 页面, 落盘 HTML + 打印表格列结构与首行数据.
用法: ./.venv/bin/python tuning/learn/fetch_mapstats.py [mapstatsid]
"""
import os
import sys

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())

import undetected_chromedriver as uc

ARG = sys.argv[1] if len(sys.argv) > 1 else "237427"
if ARG.startswith("http"):
    URL = ARG
    tag = ARG.split("/")[-1] or ARG.rstrip("/").split("/")[-2]
    OUT = f"/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/page_{tag}.html"
else:
    MID = ARG
    URL = f"https://www.hltv.org/stats/matches/performance/mapstatsid/{MID}"
    OUT = f"/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/mapstats_{MID}.html"

opts = uc.ChromeOptions()
opts.add_argument("--blink-settings=imagesEnabled=false")
opts.add_argument("--window-size=1600,1200")
drv = uc.Chrome(options=opts, version_main=152,
                browser_executable_path="/usr/bin/google-chrome-stable")
try:
    drv.get(URL)
    import time
    # Cloudflare 挑战页 ("请稍候…") JS 自动通过后页面才刷新; 轮询等表格出现
    for _ in range(15):
        time.sleep(2)
        html = drv.page_source
        if "<table" in html and "请稍候" not in html:
            break
    else:
        # 最后再多等一轮
        time.sleep(5)
        html = drv.page_source
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"saved {OUT} len={len(html)}")
    # 定位数据表: 不限 class, 打印每个 <table> 的表头与首两行
    tabs = drv.find_elements("xpath", "//table")
    print(f"tables found: {len(tabs)}")
    for ti, t in enumerate(tabs[:4]):
        try:
            heads = [h.text.strip() for h in t.find_elements("xpath", ".//th")]
            row1 = [c.text.strip() for c in t.find_elements("xpath", ".//tbody//tr[1]//td")]
            row2 = [c.text.strip() for c in t.find_elements("xpath", ".//tbody//tr[2]//td")]
            print(f"  table{ti} headers({len(heads)}): {heads}")
            print(f"  table{ti} row1: {row1}")
            if row2:
                print(f"  table{ti} row2: {row2}")
        except Exception as e:
            print(f"  table{ti} parse err: {e}")
finally:
    drv.quit()
