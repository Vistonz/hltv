"""抓 match 结果页里的真实 mapstatsid 链接(无 /performance/), 验证与 performance 版等价 + 解析 Round swing 区.
用法: ./.venv/bin/python tuning/learn/mapstats_rs_probe.py [mapstatsid_url]
"""
import os, re, sys, time

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import undetected_chromedriver as uc

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.hltv.org/stats/matches/mapstatsid/237427/parivision-vs-tyloo"
# match 结果页里的链接无 /performance/ 段, 直接冷请求会触发 CF 挑战; 补段到已验证可抓的 performance 版
if "/stats/matches/mapstatsid/" in URL and "/performance/" not in URL:
    URL = URL.replace("/stats/matches/mapstatsid/", "/stats/matches/performance/mapstatsid/", 1)
    print("rewritten URL ->", URL, flush=True)
tag = re.sub(r"[^A-Za-z0-9]+", "_", URL.split("/")[-1])[:50]
OUT = f"/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/mapstats_perf_{tag}.html"

opts = uc.ChromeOptions()
opts.add_argument("--blink-settings=imagesEnabled=false")
drv = uc.Chrome(version_main=152, browser_executable_path="/usr/bin/google-chrome-stable", options=opts)
try:
    drv.get("https://www.hltv.org")
    for _ in range(10):
        time.sleep(2)
        h = drv.page_source
        if "Just a moment" not in h and "请稍候" not in h and len(h) > 150000:
            break
    drv.get(URL)
    c = ""
    for _ in range(14):
        time.sleep(2)
        c = drv.page_source
        if "Round swing" in c or "Performance" in c:
            break
    open(OUT, "w", encoding="utf-8").write(c)
    print(f"saved {OUT} len={len(c)}")
    body = re.sub(r"<script.*?</script>", "", c, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"&nbsp;", " ", body)
    body = re.sub(r"\s+", " ", body)
    i = body.find("Round swing")
    print("round-swing section:", body[max(0, i - 200):i + 1100] if i >= 0 else "NOT FOUND")
    j = body.find("Performance overview")
    print("\nperf-overview section:", body[j:j + 220] if j >= 0 else "NOT FOUND")
    # 该页是否含逐局事件流
    k = body.find("Round 1")
    print("\nround-by-round present:", k >= 0, "| ctx:", body[max(0, k - 60):k + 160] if k >= 0 else "")
finally:
    drv.quit()
