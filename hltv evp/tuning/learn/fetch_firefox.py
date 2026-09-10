"""用 Firefox (用户实测可过 HLTV Cloudflare) 抓一个页面, 落盘 + 打印表格结构.

geckodriver 由 Selenium Manager 自动获取.
用法: ./.venv/bin/python tuning/learn/fetch_firefox.py <url> [--headed]
"""
import os
import re
import sys
import time

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())

from selenium import webdriver
from selenium.webdriver.firefox.options import Options

URL = sys.argv[1]
headed = "--headed" in sys.argv
tag = re.sub(r"[^A-Za-z0-9]+", "_", URL.split("/")[-1] or "page")[:60]
OUT = f"/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/page_{tag}.html"

opts = Options()
if not headed:
    opts.add_argument("-headless")
opts.set_preference("intl.accept_languages", "zh-CN,zh;q=0.9,en;q=0.8")
opts.set_preference("general.useragent.override",
                    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0")

drv = webdriver.Firefox(options=opts)
try:
    drv.get(URL)
    ok = False
    for _ in range(20):  # 最多等 ~60s 让 CF 挑战自动过
        time.sleep(3)
        html = drv.page_source
        if "<table" in html and ("请稍候" not in html and "Just a moment" not in html):
            ok = True
            break
    if not ok:
        time.sleep(8)
        html = drv.page_source
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"saved {OUT} len={len(html)}  real_content={ok}")
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    print("title:", title.group(1).strip()[:80] if title else None)
    for tok in ["请稍候", "Just a moment", "Round Swing", "Swing", "K-D", "ADR",
                "KAST", "clutch", "rating 3.0", "KPR"]:
        if html.count(tok):
            print(f"  token {tok!r}: {html.count(tok)}")
finally:
    drv.quit()
