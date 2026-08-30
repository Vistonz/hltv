import re
import os
import random
import time
import datetime
import undetected_chromedriver as uc
from openpyxl import Workbook

# --- 1. 准备工作 ---
# 用脚本所在位置推导 database/rank 的绝对路径, 避免从不同 cwd 运行时相对路径错位
_HERE = os.path.dirname(os.path.abspath(__file__))
base_save_dir = os.path.join(os.path.dirname(_HERE), "database", "rank")

# Chrome 配置默认值 (与 hltv evp.py Step1 对齐)
CHROME_VERSION = 152
CHROME_EXECUTABLE = "/usr/bin/google-chrome-stable"


def build_chrome_options():
    """构造 Chrome 启动参数: 禁用图片加载, 减少带宽/渲染压力,
    降低连续大量请求触发 HLTV Cloudflare 限速/挑战的概率."""
    options = uc.ChromeOptions()
    options.add_argument("--blink-settings=imagesEnabled=false")
    return options


def ensure_driver(driver, chrome_version=CHROME_VERSION, browser_executable_path=CHROME_EXECUTABLE):
    """探测 driver 是否仍可用 (窗口未关闭); 已关闭/崩溃则重建新实例.

    之前全量回溯在 2021 年后段 Chrome 窗口中途被关闭 (no such window),
    后续所有请求都打到死窗口上导致 2022~2024 整年失败; 此处用轻量探测
    (current_url) 在每次请求前确认窗口存活, 崩溃则自动重启."""
    try:
        driver.current_url  # 窗口关闭时此调用会抛异常
        return driver
    except Exception:
        print("检测到浏览器窗口已关闭, 正在重启 Chrome...")
        try:
            driver.quit()
        except Exception:
            pass
        return uc.Chrome(version_main=chrome_version, browser_executable_path=browser_executable_path,
                         options=build_chrome_options())

# --- 2. URL 生成函数 (增加了特例处理) ---
def get_all_mondays_urls(year: int):
    mondays = []
    urls = []
    
    # 设定当年的第一天
    d = datetime.date(year, 1, 1)
    
    # 寻找当年的第一个周一
    while d.weekday() != 0:
        d += datetime.timedelta(days=1)
    
    # 循环获取全年
    while d.year == year:
        # === 特殊处理开始 ===
        # 定义一个 target_date 用于生成 URL，默认就是当天的 d (周一)
        target_date = d
        
        # 判断：如果是 2025年9月1日，改为 9月2日
        if d == datetime.date(2025, 9, 1):
            print("Detected exception: Changing 2025-09-01 to 2025-09-02")
            target_date = datetime.date(2025, 9, 2)
        # === 特殊处理结束 ===

        # 使用 target_date 来生成 URL 和文件名
        month_name = target_date.strftime("%B").lower()
        day_num = str(target_date.day)
        
        url = f"https://www.hltv.org/ranking/teams/{year}/{month_name}/{day_num}"
        
        # 将修正后的日期和 URL 加入列表
        mondays.append(target_date)
        urls.append(url)
        
        # 注意：这里仍然对原始的 d 进行 +7 操作
        # 这样下一次循环依然会回到正常的周一轨道 (即 9月8日)，不会变成周二
        d += datetime.timedelta(days=7)
        
    return mondays, urls

# --- 3. 单周排名抓取 ---
def scrape_single_rank_page(driver, url, date_obj, base_save_dir):
    print(f"--------------------------------")
    print(f"正在爬取: {url}")

    try:
        driver.get(url)
        time.sleep(2.5)  # HLTV 加载慢, 从 0.5s 提升, 避免页面未就绪时取到空源码

        content = driver.page_source

        # 正则提取
        teams = re.findall(r'"><span class="name">(.*?)<', content)
        # 优化后的正则，直接提取括号内的数字
        points_raw = re.findall(r'<span class="points">\((.*?)<', content)

        # 简单校验
        if not teams:
            print(f"{url} 未找到数据，可能未发布或加载失败")
            return False

        min_len = min(len(teams), len(points_raw))

        # 创建 Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Team Ranking"
        ws.append(["Rank", "Team Name", "Points"])

        for i in range(min_len):
            ws.append([i + 1, teams[i], points_raw[i]])

        # 保存文件名，使用 target_date 生成
        # 9月的那份文件会自动保存为 2025-09-02.xlsx
        filename = f"{date_obj.strftime('%Y-%m-%d')}.xlsx"
        file_path = os.path.join(base_save_dir, filename)

        wb.save(file_path)
        print(f"保存成功: {filename}")
        return True

    except Exception as e:
        print(f"错误: {e}")
        return False

# --- 4. 年度周排名全量爬取主入口 ---
def scrape_rank_week(driver, target_monday, base_save_dir, today, start_date, only_missing=True,
                     chrome_version=CHROME_VERSION, browser_executable_path=CHROME_EXECUTABLE):
    """抓取目标周一代表的『该周排名』.

    HLTV 排名发布时间不固定为周一 (常提前到周日或延后到周二~周四),
    因此目标周一直接抓不到时, 在其前后 ±3 天 (该周内部, 触碰到上周/下周边界即停)
    逐个尝试实际发布日; 找到的第一个有数据的日期以『实际发布日期』命名保存.
    返回: (状态, driver) — 状态 1=新抓, 0=已存在跳过, -1=该周无数据 (失败);
    driver 可能在崩溃后被重建, 调用方需以返回值更新引用.
    """
    candidates = [target_monday]
    for s in range(1, 4):  # 前后各 3 天: 周日/周二, 周六/周三, 周五/周四
        candidates.append(target_monday - datetime.timedelta(days=s))
        candidates.append(target_monday + datetime.timedelta(days=s))

    # 已存在检查: 窗口内任一日期命名的快照都代表该周已抓过
    if only_missing:
        for d in candidates:
            if d > today:
                continue
            if start_date is not None and d < start_date:
                continue
            if os.path.exists(os.path.join(base_save_dir, f"{d.strftime('%Y-%m-%d')}.xlsx")):
                return 0, driver

    # 逐个候选尝试: 周一 → 周日/周二 → 周六/周三 → 周五/周四
    for d in candidates:
        if d > today:
            continue  # 未来日期未发布
        if start_date is not None and d < start_date:
            continue
        driver = ensure_driver(driver, chrome_version, browser_executable_path)  # 崩溃后自动重启
        url = f"https://www.hltv.org/ranking/teams/{d.year}/{d.strftime('%B').lower()}/{d.day}"
        if scrape_single_rank_page(driver, url, d, base_save_dir):
            return 1, driver  # 抓到实际发布日, 已以该日期命名保存
        time.sleep(random.uniform(1.0, 2.0))  # 请求间隔, 降低被限速概率
    return -1, driver


def crawl_yearly_rankings(year=2026, base_save_dir=base_save_dir, chrome_version=CHROME_VERSION,
                          browser_executable_path=CHROME_EXECUTABLE, only_missing=True,
                          start_date=None, driver=None, return_driver=False):
    """增量/全量爬取年度周排名快照.

    only_missing=True (默认): 只爬『已发布(日期<=今天)且本地缺失』的周一快照,
    已存在的跳过 — 每次运行只补新周, 已最新时秒过 (0 新抓)。
    start_date: 爬取的最早日期 (datetime.date), 早于它的周跳过 (默认 None=当年年初,
                即只处理当前年份); 传 2015-10-01 可回溯 HLTV 排名起始。
    driver: 可复用外部 driver (多年份连续爬取时共享, 避免反复启动 Chrome);
            缺省则函数内部自建并退出。
    return_driver=True: 返回 (scraped, skipped, failed, driver), 便于调用方同步
            崩溃后重建的 driver; 默认返回 (scraped, skipped, failed) 兼容旧调用。
    chrome_version / browser_executable_path 对齐 hltv evp.py Step1 的 Chrome 配置。
    """
    if not os.path.exists(base_save_dir):
        os.makedirs(base_save_dir)
    own_driver = False
    if driver is None:
        driver = uc.Chrome(version_main=chrome_version, browser_executable_path=browser_executable_path,
                           options=build_chrome_options())
        own_driver = True
    today = datetime.date.today()
    scraped = skipped = failed = 0
    try:
        target_dates, _hltv_urls = get_all_mondays_urls(year)
        for date_obj in target_dates:
            if date_obj > today:
                continue  # 未来周 (HLTV 尚未发布), 跳过
            if start_date is not None and date_obj < start_date:
                continue  # 早于起始日期 (如 2015-10-01) 的历史周, 跳过
            r, driver = scrape_rank_week(driver, date_obj, base_save_dir, today, start_date,
                                         only_missing, chrome_version, browser_executable_path)
            if r == 1:
                scraped += 1
            elif r == 0:
                skipped += 1
            else:
                failed += 1
    finally:
        if own_driver:
            driver.quit()
        print("所有任务完成。")
    print(f"增量结果: 新抓 {scraped}, 已存在跳过 {skipped}, 失败 {failed}")
    if return_driver:
        return scraped, skipped, failed, driver
    return scraped, skipped, failed

if __name__ == "__main__":
    # 全量回溯: 从 HLTV 排名起始 (2015-10-01) 爬取全部已发布周, 已存在的跳过.
    # 多年份共享一个 Chrome 实例, 避免反复启动; 崩溃后自动重建并同步引用.
    start = datetime.date(2015, 10, 1)
    current_year = datetime.date.today().year
    driver = uc.Chrome(version_main=CHROME_VERSION, browser_executable_path=CHROME_EXECUTABLE,
                       options=build_chrome_options())
    total_s = total_sk = total_f = 0
    try:
        for y in range(start.year, current_year + 1):
            driver = ensure_driver(driver)  # 每年开头探测, 窗口关闭则重建
            s, sk, f, driver = crawl_yearly_rankings(year=y, start_date=start, driver=driver,
                                                     return_driver=True)
            total_s += s; total_sk += sk; total_f += f
    finally:
        driver.quit()
    print(f"\n==== 总汇总: 新抓 {total_s}, 已存在跳过 {total_sk}, 失败 {total_f} ====")