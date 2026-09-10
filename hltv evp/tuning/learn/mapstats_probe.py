"""mapstatsid 页抓取 (预热 + 导航): 先开普通页建立会话过 CF, 再进 mapstatsid.
用法: ./.venv/bin/python tuning/learn/mapstats_probe.py [mapstatsid或完整URL]
"""
import os, re, sys, time

os.chdir("/home/hongbin/Desktop/hltv/hltv evp")
sys.path.insert(0, os.getcwd())
import undetected_chromedriver as uc

ARG = sys.argv[1] if len(sys.argv) > 1 else "https://www.hltv.org/stats/matches/performance/mapstatsid/237427/parivision-vs-tyloo"
if ARG.startswith("http"):
    URL = ARG
    tag = re.sub(r"[^A-Za-z0-9]+", "_", ARG.split("/")[-1])[:50]
else:
    URL = f"https://www.hltv.org/stats/matches/performance/mapstatsid/{ARG}"
    tag = ARG
OUT = f"/home/hongbin/Desktop/hltv/hltv evp/tuning/learn/mapstats_{tag}.html"

# 完全对齐 hltvnew 已验证可跑的最小调用 (version_main=152, 不带 options/executable)
drv = uc.Chrome(version_main=152)

def wait_real(url, tries=18, wait=3):
    """打开 url, 轮询直到出现 <table> 且非 CF 挑战页 (请稍候/Just a moment)."""
    drv.get(url)
    for _ in range(tries):
        time.sleep(wait)
        html = drv.page_source
        if "<table" in html and "请稍候" not in html and "Just a moment" not in html:
            return html, True
    return drv.page_source, False

try:
    # 1) 预热: 普通站内页 (赛果列表), 等挑战自动过
    h1, ok1 = wait_real("https://www.hltv.org/matches", tries=12)
    print(f"[warm] len={len(h1)} real={ok1} title=", end="")
    m = re.search(r"<title>(.*?)</title>", h1, re.S)
    print(repr(m.group(1).strip()[:60]) if m else None, flush=True)

    # 2) 目标 mapstatsid 页
    h2, ok2 = wait_real(URL, tries=18)
    open(OUT, "w", encoding="utf-8").write(h2)
    print(f"[mapstats] saved {OUT} len={len(h2)} real={ok2}", flush=True)
    if not ok2:
        for tok in ["请稍候", "Just a moment", "Cloudflare", "challenge"]:
            if tok in h2:
                print("  CF marker:", tok)
        sys.exit(0)
    # 解析表结构
    tabs = re.findall(r"<table[^>]*>.*?</table>", h2, re.S)
    print(f"  <table> count: {len(tabs)}", flush=True)
    for ti, t in enumerate(tabs[:5]):
        heads = re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)
        heads = [re.sub(r"<[^>]+>", "", x).strip() for x in heads]
        trs = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
        row1 = trs[1] if len(trs) > 1 else ""
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row1, re.S)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells][:20]
        print(f"  table{ti}: th({len(heads)})={heads[:16]}", flush=True)
        print(f"          row1={cells}", flush=True)
    # Round Swing 上下文: 找 swing / 逐局相关文本
    for tok in ["Round Swing", "Swing", "round", "KPR", "kill per round"]:
        c = h2.count(tok)
        if c:
            idx = h2.find(tok)
            print(f"  token {tok!r}: {c}  ctx: ...{h2[max(0,idx-60):idx+80]!r}...", flush=True)
finally:
    drv.quit()
