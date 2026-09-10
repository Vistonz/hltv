"""抓一个 Bo3 结果页, 打印其内部 mapstatsid 链接(带出现顺序)与图相关锚点.
用法: ./.venv/bin/python tuning/learn/fetch_match_page.py <matchurl>
"""
import os, re, sys, time

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import undetected_chromedriver as uc

# 本机同时装了 chromium 151 与 google-chrome 152; 不锁定 executable 时 uc 偶发搜到
# chromium 151 -> chromedriver 152 mismatch ("only supports version 152")。
# 显式锁定 Chrome 152 (hltv evp.py ensure_driver / rank.py 全量回溯同款配置)。
opts = uc.ChromeOptions()
opts.add_argument("--blink-settings=imagesEnabled=false")
drv = uc.Chrome(version_main=152, browser_executable_path="/usr/bin/google-chrome-stable",
                options=opts)

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.hltv.org/matches/2397600/parivision-vs-tyloo-fissure-playground-3"
tag = re.sub(r"[^A-Za-z0-9]+", "_", URL.split("/")[-1])[:50]
OUT = f"/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/match_{tag}.html"
try:
    # 预热
    drv.get("https://www.hltv.org")
    for _ in range(12):
        time.sleep(2)
        h = drv.page_source
        if "Just a moment" not in h and "请稍候" not in h and len(h) > 150000:
            break
    drv.get(URL)
    c = ""
    for _ in range(14):
        time.sleep(2)
        c = drv.page_source
        if "statsPlayerName" in c:
            break
    open(OUT, "w", encoding="utf-8").write(c)
    print(f"saved {OUT} len={len(c)}")
    seen = []
    for m in re.finditer(r'href="(/stats/matches/performance/mapstatsid/\d+[^"]*)"', c):
        u = m.group(1)
        if u not in seen:
            seen.append(u)
    for u in seen:
        print("MPS>", u)
    print("n_mapstatsid_uniq:", len(seen))
    # 出现位置上下文: 首个 mapstatsid 前 300 字符
    i = c.find("mapstatsid")
    if i > 0:
        seg = re.sub(r"\s+", " ", c[max(0, i - 400):i + 200])
        print("CTX>", seg[-520:])
finally:
    drv.quit()
