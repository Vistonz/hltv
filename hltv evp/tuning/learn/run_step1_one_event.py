"""单赛事 Step1 (mapstats 补抓升级) 运行器. 仅跑 Step1, 不动 Step1.5/2/3.

用法: ./.venv/bin/python tuning/learn/run_step1_one_event.py <eid> [--full]
  --full: 忽略 eid, 对全赛事名单跑 run_step1_scrape_data() (CS2 缺 map_* 列者重建升级).
不带 --full: 只处理 eid 一个赛事 (从模块 event_urls 里按 id 定位其完整 URL), 用于试点验证.
"""
import os
import sys
import importlib.util

REPO = "/home/hongbin/Desktop/hltv/hltv evp"
sys.path.insert(0, REPO)
MOD = os.path.join(REPO, "hltv evp.py")


def load_module():
    spec = importlib.util.spec_from_file_location("hltv_evp", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)   # 顶层会加载 MVP 名单 → event_urls/eventfilter
    return mod


def main():
    args = sys.argv[1:]
    full = "--full" in args
    eid = [a for a in args if a.isdigit()]
    mod = load_module()
    if full:
        print("== 全赛事 Step1 (mapstats 升级) ==")
        mod.run_step1_scrape_data()
        return
    if not eid:
        print("需提供 eid (或 --full)")
        sys.exit(2)
    eid = eid[0]
    # 定位该 eid 的完整 URL 与 filter
    idx = None
    for i, u in enumerate(mod.event_urls):
        m = mod.get_event_id_from_url(u)
        if m == eid:
            idx = i
            break
    if idx is None:
        print(f"名单中无 eid={eid}")
        sys.exit(2)
    mod.event_urls = [mod.event_urls[idx]]
    mod.eventfilter = [f"&event={eid}"]
    print(f"== 单赛事 Step1 试点: eid={eid} url={mod.event_urls[0]} ==")
    mod.run_step1_scrape_data()


if __name__ == "__main__":
    main()
