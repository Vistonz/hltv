import re
import os
import json
import math
import time
import pandas as pd
from openpyxl.utils.dataframe import dataframe_to_rows
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# 新算法 (2026-08-30): 用 evp_experiment 的 EVP_CONFIG 定案 (obj=107.03) 替换旧 calculate_performance_score 计算.
# 保留: 赛事含金量权重 (event_scores_lookup.xlsx) + 产物输出结构 (EVP_Summary/Per_Map_Scores/透视表).
import evp_experiment as evp_exp
# 两套分拆的赛事分段判定 (segment_of: CS:GO/CS2) — 与评估口径同一权威源 (2026-09-10)
import eval_full as ev  # noqa: E402
# 赛事含金量 (eventrank): 计算赛事队伍积分/当期世界总积分 → event_scores_lookup.xlsx (Step 1.5)
import eventrank
# CS2 mapstatsid (每图 performance) 解析: 地图级 KPR/DPR/KAST/MK/Swing/ADR/Rating3.0 + 事件导出 (2026-09-08)
import mapstats_parser as msp

# ----------------------------------------------------------------------
# 1. 
# 全局配置区
# ----------------------------------------------------------------------

# 赛事名单: event_urls / eventfilter 不再写死, 改从 MVP 名单 (database/event/mvp_events.xlsx)
# 加载 (见下方 _load_mvp_event_urls), 失败时回退到内置 12 个 2026 赛事.

# (回合) 长度归一化参数 (幂)
POWER_PENALTY = 1
POWER_BOOST = 0.5
BASIC_EVP_POINT = 0
MULTIPLE_EVP_POINT = 5.5
UPPER_POWER = 1.2

# ----------------- [路径配置] -----------------
# 基础路径
base_directory = "/home/hongbin/Desktop/hltv/database/event"
# 排名数据库路径
rank_db_directory = "/home/hongbin/Desktop/hltv/database/rank"
# 赛事日期映射文件路径 (已提取到独立权重脚本中使用)
# date_mapping_file = "/home/hongbin/Desktop/hltv/hltv evp/副本2025年各赛事使用的HLTV排名日期.xlsx"

# ----------------- [MVP 赛事名单加载] -----------------
# MVP 名单 (2026-08-31 起): 从 HLTV stats/events?matchType=MvpEvents 提取全部 MVP 赛事,
# 完整 URL (含 slug) 由 Camoufox 抓取重定向后的真实 URL 写入 mvp_events.xlsx 的 url 列.
# 名单按 offset 抓取顺序排列 (时间从新到旧), Step1 遇到第一个早于 RANK_START_DATE 的赛事即 break,
# 其后的更旧赛事不再爬取.
RANK_START_DATE = "2015-10-01"          # HLTV 战队排名起始日 (2015-10-01 起才有周快照)
# CS2 边界 (2026-09-08): CS2 于 2023-09-27 发布. 仅 start_date >= 该日的赛事 (最早如 6865 IEM Sydney
# 2023-10-16) 补抓 mapstatsid 每图 performance 地图级字段; CS:GO 赛事无 Round Swing/这些数据, 保持原样.
CS2_START_DATE = "2023-09-27"
# 交付物写出范围 (2026-09-10): "all"=全部赛事 (默认); "cs2"/"csgo"=只写该段赛事的
# event_{id}_evp_summary.xlsx (另一段交付物不覆盖); 透视表始终用全部赛事行重算.
# 用途: 机制口径变更后只重生成 CS2 交付物 → EVP_WRITE_EVENTS=cs2;
#       CS 核参数变更 (2026-09-10 解冻后 42 核可改) → 默认 all 全段重生成.
WRITE_EVENTS = os.environ.get("EVP_WRITE_EVENTS", "all").strip().lower()
MVP_LIST_FILE = os.path.join(base_directory, "mvp_events.xlsx")

# 内置回退: 原写死的 12 个 2026 赛事 (名单文件缺失/无 url 列时保证脚本仍可独立运行)
_DEFAULT_EVENT_URLS = [
    "https://www.hltv.org/events/8246/blast-bounty-2026-season-1-finals",
    "https://www.hltv.org/events/8240/iem-krakw-2026",
    "https://www.hltv.org/events/8047/pgl-cluj-napoca-2026",
    "https://www.hltv.org/events/8412/EPL-S23",
    "https://www.hltv.org/events/8248/blast-open-rotterdam-2026",
    "https://www.hltv.org/events/8048/pgl-bucharest-2026",
    "https://www.hltv.org/events/8242/iem-rio-2026",
    "https://www.hltv.org/events/8250/blast-rivals-2026-season-1",
    "https://www.hltv.org/events/8049/pgl-astana-2026",
    "https://www.hltv.org/events/8243/iem-atlanta-2026",
    "https://www.hltv.org/events/8263/cs-asia-championships-2026",
    "https://www.hltv.org/events/8301/iem-cologne-major-2026"
]
_DEFAULT_EVENTFILTER = [
    "&event=8246",
    "&event=8240","&event=8047","&event=8413","&event=8248","&event=8048","&event=8242","&event=8250","&event=8049","&event=8243","&event=8263","&event=8301"
]


def _load_mvp_event_urls():
    """从 MVP 名单 (mvp_events.xlsx) 加载完整赛事 URL 列表与过滤参数.

    要求名单含 'url' (完整 URL, 时间新→旧) 与 'event_id' 列;
    失败时回退到内置 12 个 2026 赛事, 保证脚本仍可独立运行.
    返回: (event_urls, eventfilter).
    """
    try:
        df = pd.read_excel(MVP_LIST_FILE)
        if "url" not in df.columns:
            raise ValueError("名单缺少 url 列")
        urls = df["url"].dropna().astype(str).tolist()
        ids = df["event_id"].dropna().astype(int).tolist()
        if not urls:
            raise ValueError("名单 url 列为空")
        filters = [f"&event={int(i)}" for i in ids[:len(urls)]]
        print(f"[名单] 已从 MVP 名单加载 {len(urls)} 个赛事 (新→旧顺序): {MVP_LIST_FILE}")
        return urls, filters
    except Exception as e:
        print(f"[名单] 警告: 加载 MVP 名单失败 ({e}), 回退到内置 12 个 2026 赛事")
        return _DEFAULT_EVENT_URLS, _DEFAULT_EVENTFILTER


event_urls, eventfilter = _load_mvp_event_urls()

# (文件路径)
output_stats_file = os.path.join(base_directory, "global_stats.json")
event_score_file_path = os.path.join(base_directory, "event_scores_lookup.xlsx")
global_summary_file_path = os.path.join("/home/hongbin/Desktop/hltv/hltv evp", "global_evp_pivot_summary.xlsx")

# (权重和阶段定义)
stage_weight_map = {
    "Grand final": 1.75,
    "Semi-final": 1.25,
    "Quarter-final": 1,
    "3rd place": 0.3,
    "Groups": 0.3,
    "Online": 0.25,
}

# (分数) 价值归一化参数 (软上限基准 C)
GROUP_STAGE_SCORE_CAP = 30
SOFT_CAP_LOG_BASE = 5

BASE_WEIGHT_C = 0.5
RANK_K =  6
# (阶段定义)
PLAYOFF_STAGES = ["Grand final", "Semi-final", "Quarter-final", "3rd place"]


# ----------------------------------------------------------------------
# 2. 
# 辅助函数区
# ----------------------------------------------------------------------

def get_event_id_from_url(url):
    """从URL中提取赛事ID"""
    match = re.search(r"[-+]?\d+\.?\d*|\.\d+", url)
    if match:
        return match.group(0)
    return None

def ensure_driver(driver):
    """探测 driver 是否仍可用 (窗口未关闭); 已关闭/崩溃则重建新实例.

    与 hltv rank.py 同一策略: 长时间大量请求时 Chrome 窗口可能被系统/驱动关闭,
    后续请求全打到死窗口 (no such window) 导致该赛事数据不全;
    此处用轻量探测 (current_url) 在每次请求前确认窗口存活, 崩溃则自动重启."""
    try:
        driver.current_url  # 窗口关闭时此调用会抛异常
        return driver
    except Exception:
        print("检测到浏览器窗口已关闭, 正在重启 Chrome...")
        try:
            driver.quit()
        except Exception:
            pass
        return uc.Chrome(version_main=152, browser_executable_path="/usr/bin/google-chrome-stable")

def is_cs2_event(event_start_date):
    """是否 CS2 赛事: start_date(YYYY-MM-DD) >= CS2_START_DATE 即启用 mapstatsid 每图补抓."""
    return bool(event_start_date) and str(event_start_date) >= CS2_START_DATE

def event_meta_start_date(target_directory, event_id):
    """读取已落盘 event_{id}_meta.json 的 start_date; 无则返回 None."""
    try:
        mf = os.path.join(target_directory, f"event_{event_id}_meta.json")
        with open(mf, "r") as f:
            return json.load(f).get("start_date")
    except Exception:
        return None

def raw_has_mapstats(file_path):
    """raw xlsx 是否已含 mapstats 补抓列 (header 出现 map_kpr)."""
    try:
        cols = pd.read_excel(file_path, nrows=0).columns.tolist()
        return "map_kpr" in cols
    except Exception:
        return False

def ensure_perf_driver(driver):
    """兼容占位: performance 抓取复用主流程 driver (executable 152 配置经实测可过 performance 页).

    曾为 performance 页另起一个无 executable 的最小 Chrome, 但该启动方式在本机不可靠
    (SessionNotCreatedException: cannot connect to chrome), 而带 executable 的主 driver 已被
    现场验证能抓 /stats/matches/performance/* (6MB 有 highlighted-player, 无 CF). 故直接返回
    主 driver, 不再维护第二浏览器. 仅当主 driver 崩溃时返回 None (调用方放弃本场后续图)."""
    if driver is None:
        return None
    try:
        driver.current_url            # 窗口关闭/崩溃时抛异常
        return driver
    except Exception:
        print("  [mapstats] 主 driver 窗口已关闭, 放弃本场后续 performance 补抓")
        return None

def fetch_perf_html(driver, url):
    """单图 mapstatsid(performance) 页抓取 -> html 或 None (CF 未过/超时/异常)."""
    try:
        driver.get(url)
        for _ in range(20):
            time.sleep(3)
            html = driver.page_source
            if ("highlighted-player" in html and "Just a moment" not in html
                    and "请稍候" not in html and len(html) > 50000):
                return html
    except Exception as e:
        print(f"  [mapstats] 抓取异常 {type(e).__name__}: {e}")
    return None

def get_rank_weight(opponent_rank):
    weight = BASE_WEIGHT_C + (RANK_K / (opponent_rank + 5))
    return weight

def apply_symmetrical_soft_cap(score, cap=GROUP_STAGE_SCORE_CAP):
    if cap <= 0:
        return score
        
    abs_score = abs(score)
    sign = 1 if score >= 0 else -1
    
    if abs_score <= cap:
        return score
    else:
        # cap + C * log_BASE( (excess)/C + 1 )
        excess = abs_score - cap
        scaled_excess = cap * math.log(1 + (excess / cap), SOFT_CAP_LOG_BASE)
        final_abs = cap + scaled_excess
        return sign * final_abs
        
def calculate_performance_score(
    player_rating, stage_weight, rank_weight, 
    team_avg_rating, match_baseline_rating,
    round_differential 
    ):
    performance_delta = player_rating - (match_baseline_rating*2 - team_avg_rating)
    team_context_delta = player_rating - team_avg_rating
    if round_differential > 0:
        base_score = 1
    else:
        base_score = 0.5
    # (b) 基础表现分 (非线性)
    if performance_delta > 0:
        original_log_score = math.log1p(performance_delta)
        perf_delta_score = 0.2 * math.pow(original_log_score, UPPER_POWER)
    else:
        original_log_score = math.log1p( 0 - performance_delta)
        perf_delta_score = 0 - 0.2 * math.pow(original_log_score, UPPER_POWER)

    # (c) 团队贡献分 (非线性)
    if team_context_delta > 0:
        original_log_score = math.log1p(team_context_delta)
        team_context_score = 0.8 * math.pow(original_log_score, UPPER_POWER)
    else:
        original_log_score = math.log1p( 0 - team_context_delta)
        team_context_score = 0 - 0.8  * math.pow(original_log_score, UPPER_POWER)
    raw_score = (perf_delta_score + team_context_score)
    stage_adjusted_score = raw_score * stage_weight * rank_weight
    return stage_adjusted_score * base_score + 0.06 * stage_weight


# ----------------------------------------------------------------------
# 2.5
# (Step 0) 更新 HLTV 周排名快照 (增量, hltv rank.py)
# ----------------------------------------------------------------------

def run_step0_update_rank():
    """(Step 0, hltv rank) 增量抓取 HLTV 周排名快照 (database/rank/YYYY-MM-DD.xlsx).

    复用 hltv rank.py 的 crawl_yearly_rankings (only_missing=True):
    只补『已发布且本地缺失』的周一快照, 已最新时秒过 (0 新抓)。
    失败不阻断主流程 (已有快照仍可用), 仅打印警告。
    """
    print("\n===========================================================")
    print("  Step 0 (hltv rank): 更新 HLTV 世界排名快照 (增量)")
    print("===========================================================")
    try:
        import importlib
        hltv_rank = importlib.import_module("hltv rank")
        scraped, skipped, failed = hltv_rank.crawl_yearly_rankings()
        print(f"  -> 新抓 {scraped}, 已存在跳过 {skipped}, 失败 {failed}")
        if failed:
            print("  (部分周未抓到 — 可能是 HLTV 未发布, 不影响后续使用已有多数快照)")
        return True
    except Exception as e:
        print(f"警告: 更新排名快照失败 (将使用已有快照继续): {e}")
        return False


# ----------------------------------------------------------------------
# 3.
# (Step 1) 真实数据抓取 (保持不变)
# ----------------------------------------------------------------------

def run_step1_scrape_data():
    print("===========================================================")
    print("  运行 Step 1 (真实爬虫): 抓取原始数据 (按地图)")
    print("===========================================================")
        
    all_events_scraped_successfully = True
    failed_events = []  # 单赛事失败不阻断全流程, 由断点续跑机制下次补齐
    driver = None

    for i, url in enumerate(event_urls):
        event_id = get_event_id_from_url(url)
        current_event_name = url.split('/')[-1]
        
        if not event_id:
            print(f"警告: 无法从 {url} 提取 event_id，跳过。")
            continue

        target_directory = os.path.join(base_directory, event_id)
        raw_data_file_path = os.path.join(target_directory, f"raw_event_{event_id}_data.xlsx")
        
        print(f"\n--- (Step 1) 正在检查: {current_event_name} ---")

        if os.path.exists(raw_data_file_path):
            # 已存在数据: 若已含 mapstats 补抓列 (map_kpr) 则跳过 (幂等);
            # 缺列时仅当为 CS2 赛事 (start >= CS2_START_DATE) 才重建以补抓每图字段; CS:GO 赛事保持原样.
            if raw_has_mapstats(raw_data_file_path):
                print(f"检测到已存在数据且已含 mapstats 列, 跳过抓取。")
                continue
            meta_sd = event_meta_start_date(target_directory, event_id)
            if is_cs2_event(meta_sd):
                print(f"检测到已存在数据 (CS2, start {meta_sd}) 但缺 mapstats 列 -> 重建以补抓每图字段")
            else:
                print(f"检测到已存在数据 (CS:GO 或无需补抓), 跳过。")
                continue

        print(f"未找到缓存，开始抓取: {current_event_name}")
        
        all_player_raw_stats = [] 
        team_rank_map = {}
        timeout = 15
        keyword = ">" 
        
        try:
            driver = uc.Chrome(version_main=152, browser_executable_path="/usr/bin/google-chrome-stable")
            driver.get(url)
            try:
                WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CLASS_NAME, "event-world-rank")))
            except: pass
            
            content = driver.page_source

            event_start_date = None  # 用于 MVP 名单范围控制 (早于排名起始则 break)
            # --- [新增] 提取赛事开始时间 ---
            try:
                # 寻找 <td class="eventdate"><span data-unix="1771066800000">...</span></td>
                date_unix_match = re.search(r'<td class="eventdate">.*?<span .*?data-unix="(\d+)".*?>', content, re.DOTALL)
                if date_unix_match:
                    unix_ms = int(date_unix_match.group(1))
                    event_start_date = pd.to_datetime(unix_ms, unit='ms').strftime('%Y-%m-%d')
                    print(f"  -> 成功提取赛事开始日期: {event_start_date}")
                    
                    # 保存元数据
                    meta_data = {"start_date": event_start_date}
                    meta_file_path = os.path.join(target_directory, f"event_{event_id}_meta.json")
                    os.makedirs(target_directory, exist_ok=True)
                    with open(meta_file_path, "w") as f:
                        json.dump(meta_data, f)
                else:
                    print("  -> 警告: 无法从页面提取赛事开始日期 (data-unix)")
            except Exception as e:
                print(f"  -> 提取日期时出错: {e}")
            # -------------------------------

            # --- [MVP 名单范围控制] 早于排名起始日期的赛事不抓取, 并停止后续更旧赛事 ---
            # 名单按 offset 抓取顺序排列 (时间从新到旧), 故遇到第一个 < RANK_START_DATE 的
            # 赛事后, 其后的赛事全部更旧, 直接 break 省去无效爬取 (2015-10 之前无 HLTV 排名,
            # 含金量/排名均无法匹配).
            if event_start_date and event_start_date < RANK_START_DATE:
                print(f"  -> 赛事开始 {event_start_date} 早于排名起始 {RANK_START_DATE}, 跳过并停止后续更旧赛事")
                break
            # -------------------------------------------------------

            # --- [CS2 补抓] 边界判定: 仅 CS2 赛事 (start_date >= CS2_START_DATE) 启用 mapstatsid ---
            cs2_event = is_cs2_event(event_start_date)
            if cs2_event:
                print(f"  -> CS2 赛事 (start {event_start_date} >= {CS2_START_DATE}): 启用每图 mapstatsid 补抓")

            team_name = re.findall('<div class="text">(.*?)<',content)
            team_rank_raw = re.findall('<div class="event-world-rank" title=".*?">#(.*?)<', content)
            team_rank_clean = [r for r in team_rank_raw if r.isdigit()]
            
            for idx in range(min(len(team_name), len(team_rank_clean))):
                team_rank_map[team_name[idx]] = int(team_rank_clean[idx])
            
            try: current_filter = eventfilter[i]
            except: current_filter = f"&event={event_id}"

            filter_param = current_filter.lstrip('&') 
            webnext = f"https://www.hltv.org/results?{filter_param}"
            
            driver = ensure_driver(driver)  # 崩溃自动重建 (长时爬取窗口可能被杀)
            driver.get(webnext)
            try:
                WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CLASS_NAME, "a-reset")))
            except: pass
            
            content = driver.page_source
            Game_link = re.findall('<a href="(/matches/.*?)" class="a-reset">', content)
            Game_link = list(dict.fromkeys(Game_link)) 
            
            if not Game_link: continue
                 
            print(f"共找到 {len(Game_link)} 场比赛。")

            for j, link in enumerate(Game_link):
                match_url = 'https://www.hltv.org' + link
                print(f"\n--- 正在处理比赛 {j + 1}/{len(Game_link)} ---")
                driver = ensure_driver(driver)  # 崩溃自动重建 (每场请求前探测)
                driver.get(match_url)
                try:
                    WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((By.CLASS_NAME, "statsPlayerName")))
                except: continue
                
                content = driver.page_source

                # --- [CS2 补抓] 本场各图 mapstatsid(performance) 链接 (出现序=图序; 页面链接为无 /performance/ 版) ---
                mapstats_urls = []
                if cs2_event:
                    raw_ms = re.findall(r'href="(/stats/matches/mapstatsid/\d+[^"]*)"', content)
                    raw_ms = list(dict.fromkeys(raw_ms))
                    mapstats_urls = ["https://www.hltv.org" + u.replace(
                        "/stats/matches/mapstatsid/", "/stats/matches/performance/mapstatsid/", 1)
                        for u in raw_ms]
                    if mapstats_urls:
                        print(f"  [mapstats] 本场发现 {len(mapstats_urls)} 个地图性能页")

                game_score = re.findall('<div class="results-team-score">(.*?)<', content)
                game_team_name = re.findall('<div class="results-teamname text-ellipsis">(.*?)<', content)
                game_player_name = re.findall('<div class="smartphone-only statsPlayerName text-ellipsis">(.*?)<', content)
                game_total_rating = re.findall('<td class="rating text-center rating(.*?)<', content)
                
                stage_match_raw = re.findall('preformatted-text">(.*?)</', content, re.DOTALL)

                # 阶段判定: HLTV 阶段文本大小写不统一 ("Semi-final" / "semi-final"),
                # 且小组赛标记行也可能含阶段字样 (如 "Group B upper bracket final. Winner
                # advances to the playoff semi-finals"), 故按 "* 标记行" 判定并跳过 Group/Swiss 行.
                stage_marker = stage_match_raw[0] if stage_match_raw else ""
                if "online" in stage_marker.lower():
                    match_stage = "Online"
                else:
                    match_stage = "Groups"
                    for line in stage_marker.split("\n"):
                        line = line.strip()
                        if not line.startswith("*"): continue
                        marker = line.lstrip("* ").strip()
                        if re.match(r"^(group|swiss|round)\b", marker, re.IGNORECASE): continue
                        low = marker.lower()
                        if "grand final" in low: match_stage = "Grand final"; break
                        if "semi-final" in low: match_stage = "Semi-final"; break
                        if "quarter-final" in low: match_stage = "Quarter-final"; break
                        if "3rd place" in low: match_stage = "3rd place"; break

                for idx in range(len(game_total_rating)):
                    game_total_rating[idx] = game_total_rating[idx].split(keyword, 1)[-1].strip()

                if len(game_team_name) < 2 or len(game_score) < 2: continue
                
                try:
                    team1_name = game_team_name[0].strip()
                    team2_name = game_team_name[1].strip()
                    team1_rank = team_rank_map.get(team1_name, 999)
                    team2_rank = team_rank_map.get(team2_name, 999)
                    
                    num_maps = len(game_score) // 2

                    MAP_DATA_START_OFFSET = 30
                    MAP_DATA_INCREMENT = 30
                    TEAM_DATA_INCREMENT = 15
                    PLAYERS_PER_TEAM = 5

                    for map_index in range(num_maps):
                        try:
                            r1 = int(game_score[map_index * 2].strip())
                            r2 = int(game_score[map_index * 2 + 1].strip())
                            map_total_rounds = r1 + r2
                            map_team1_round_diff = r1 - r2
                            map_team2_round_diff = -map_team1_round_diff 
                            if map_total_rounds == 0: continue
                        except: continue 

                        t1_start_idx = MAP_DATA_START_OFFSET + (map_index * MAP_DATA_INCREMENT)
                        t2_start_idx = t1_start_idx + TEAM_DATA_INCREMENT
                        t1_end_idx = t1_start_idx + PLAYERS_PER_TEAM
                        t2_end_idx = t2_start_idx + PLAYERS_PER_TEAM

                        if t2_end_idx > len(game_player_name): break 

                        try:
                            t1_ratings_float = [float(game_total_rating[j]) for j in range(t1_start_idx, t1_end_idx)]
                            t2_ratings_float = [float(game_total_rating[j]) for j in range(t2_start_idx, t2_end_idx)]
                            
                            team1_avg_rating = sum(t1_ratings_float) / 5 if t1_ratings_float else 1.0
                            team2_avg_rating = sum(t2_ratings_float) / 5 if t2_ratings_float else 1.0
                            all_map_player_ratings = t1_ratings_float + t2_ratings_float
                            map_baseline_rating = sum(all_map_player_ratings) / 10.0 if len(all_map_player_ratings) == 10 else 1.0
                        except: continue

                        # ---- [CS2 补抓] 本图 mapstatsid(performance) 抓取 + 解析. 失败/CF 仅跳过该图, 不阻断主流程 ----
                        # 复用主 driver (executable 152 实测可过 performance 页); 逐图导航不读回主页面,
                        # 后续图/场靠新一轮 driver.get 重新加载, 故此处导航无副作用.
                        map_enrich = {}
                        if mapstats_urls and map_index < len(mapstats_urls):
                            perf_driver = ensure_perf_driver(driver)
                            if perf_driver is None:
                                mapstats_urls = []          # 主 driver 已失效: 放弃本场后续图
                            else:
                                perf_html = fetch_perf_html(perf_driver, mapstats_urls[map_index])
                                if perf_html:
                                    try:
                                        prow, pmeta = msp.build_summary(perf_html)
                                        map_enrich = {(r["team"], r["nick"]): msp.enrich_cols(r)
                                                      for r in prow.values()}
                                        print(f"  [mapstats] 图{map_index + 1} 解析 {len(map_enrich)} 名选手, "
                                              f"rounds={pmeta['n_rounds']}", flush=True)
                                    except Exception as ee:
                                        print(f"  [mapstats] 解析失败: {type(ee).__name__}: {ee}")

                        for j in range(PLAYERS_PER_TEAM):
                            player_idx = t1_start_idx + j
                            row = {
                                "player": game_player_name[player_idx].strip(),
                                "team": team1_name,
                                "opponent": team2_name,
                                "opponent_rank": team2_rank,
                                "match_stage": match_stage,
                                "round_differential": map_team1_round_diff,
                                "rating": t1_ratings_float[j],
                                "team_avg_rating": team1_avg_rating,
                                "total_rounds": map_total_rounds,
                                "match_baseline_rating": map_baseline_rating
                            }
                            row.update(map_enrich.get((team1_name, row["player"]), {}))
                            all_player_raw_stats.append(row)

                        for j in range(PLAYERS_PER_TEAM):
                            player_idx = t2_start_idx + j
                            row = {
                                "player": game_player_name[player_idx].strip(),
                                "team": team2_name,
                                "opponent": team1_name,
                                "opponent_rank": team1_rank,
                                "match_stage": match_stage,
                                "round_differential": map_team2_round_diff,
                                "rating": t2_ratings_float[j],
                                "team_avg_rating": team2_avg_rating,
                                "total_rounds": map_total_rounds,
                                "match_baseline_rating": map_baseline_rating
                            }
                            row.update(map_enrich.get((team2_name, row["player"]), {}))
                            all_player_raw_stats.append(row)

                except Exception as e:
                    print(f"处理比赛数据时出错: {e}")

            print(f"\n--- {current_event_name} 抓取完毕 ---")
            
            if all_player_raw_stats:
                try:
                    os.makedirs(target_directory, exist_ok=True)
                    df_raw_save = pd.DataFrame(all_player_raw_stats)
                    df_raw_save.to_excel(raw_data_file_path, index=False)
                    print(f"原始数据保存成功，共 {len(df_raw_save)} 条。")
                except Exception as e:
                    print(f"保存原始数据失败: {e}")
                    failed_events.append(current_event_name)
            else:
                print(f"警告：赛事 {current_event_name} 未抓取到数据。")
                failed_events.append(current_event_name)

        except Exception as e:
            print(f"严重错误: {e}")
            failed_events.append(current_event_name)
        
        finally:
            if driver: driver.quit()
            
    if failed_events:
        print(f"警告: Step1 有 {len(failed_events)} 个赛事失败, 已记录待补齐: {failed_events}")
        print("(raw 缺失的赛事会被 Step1.5/2/3 自动跳过; 重跑 Step1 时断点续跑自动补齐)")
    return all_events_scraped_successfully


# ----------------------------------------------------------------------
# 4. 
# (Step 2) 全局统计计算 (权重逻辑已抽离到外部独立文件)
# ----------------------------------------------------------------------

def run_step2_calculate_global_stats():
    print("\n===========================================================")
    print("  运行 Step 2 (新算法 evp_experiment obj=107.03): 计算全局统计数据")
    print("===========================================================")

    # 尝试读取外部独立脚本计算好的赛事含金量表 (保留: 赛事权重)
    all_event_scores_for_saving = {}
    try:
        if os.path.exists(event_score_file_path):
            df_scores = pd.read_excel(event_score_file_path, index_col=0)
            all_event_scores_for_saving = df_scores['event_score'].to_dict()
            print(f"成功加载 {len(all_event_scores_for_saving)} 条已存在的赛事含金量分数。")
    except Exception as e:
        print(f"加载 'event_scores_lookup.xlsx' 失败: {e}")
        all_event_scores_for_saving = {}

    # 用新算法逐赛事计算选手总分 (total_score), 收集全局分布用于 z_score
    import statistics
    all_scores = []
    all_group_rounds = []
    n_events = 0
    group_stages = evp_exp.EVP_CONFIG["GROUP_STAGES"]

    for url in event_urls:
        event_id = get_event_id_from_url(url)
        current_event_name = url.split('/')[-1]
        if not event_id:
            continue
        raw_data_path = os.path.join(base_directory, event_id, f"raw_event_{event_id}_data.xlsx")
        if not os.path.exists(raw_data_path):
            print(f"错误: 原始数据文件 '{raw_data_path}' 未找到。跳过。")
            continue

        print(f"\n--- (Step 2) 正在处理: {current_event_name} (新算法) ---")
        # 两套分拆 (2026-09-10): 逐赛事按产品段取 cfg — CS:GO=42 核原样, CS2=EVP_CONFIG+CS2_OVERRIDES.
        # 全局 z 统计必须与生产交付口径一致 (CS2 机制-on), 否则 mean/std 会混入 mechanism-off 的总分.
        step_cfg = evp_exp.cfg_for(ev.segment_of(event_id))
        summary, _bo_all, map_all, _details = evp_exp.run_experiment(
            raw_data_path, None, None, cfg=step_cfg, save=False)
        all_scores.extend(summary["total_score"].tolist())
        grp = map_all.loc[map_all["match_stage"].isin(group_stages), "total_rounds"]
        all_group_rounds.extend(grp.tolist())
        n_events += 1
        if current_event_name not in all_event_scores_for_saving:
            print(f"警告: 未在查找表中找到 {current_event_name} 的赛事含金量。请确保运行了权重计算脚本。")
            all_event_scores_for_saving[current_event_name] = 0.0

    if all_scores:
        mean_score = float(statistics.mean(all_scores))
        std_score = float(statistics.pstdev(all_scores)) if len(all_scores) > 1 else 1.0
        mean_group_rounds = float(statistics.mean(all_group_rounds)) if all_group_rounds else 1.0
    else:
        mean_score, std_score, mean_group_rounds = 0.0, 1.0, 1.0

    stats_data = {
        "global_mean_performance_score": mean_score,
        "global_std_dev_performance_score": std_score,
        "global_average_group_rounds_played": mean_group_rounds,
        "total_player_records_processed": len(all_scores),
        "total_events_processed": n_events,
    }
    try:
        with open(output_stats_file, "w") as f:
            json.dump(stats_data, f, indent=4)
    except Exception as e:
        print(f"保存 global_stats.json 失败: {e}")
        return False, None, None

    print(f"\nStep 2 执行完毕。全局 mean={mean_score:.4f} std={std_score:.4f} (新算法 total_score)")
    return True, stats_data, all_event_scores_for_saving





# ----------------------------------------------------------------------
# 4. 
# (Step 3) EVP 计算与汇总 (新算法 evp_experiment, 保留赛事含金量 + 输出结构)
# ----------------------------------------------------------------------


def run_step3_calculate_evp_pivot():
    print("\n===========================================================")
    print("  运行 Step 3 (新算法 evp_experiment obj=107.03): 计算EVP并生成汇总")
    print("===========================================================")

    # 赛事含金量 (保留: 赛事权重, weighted_evp_score = evp_score × event_score)
    manual_event_scores_map = {}
    try:
        if os.path.exists(event_score_file_path):
            df_scores = pd.read_excel(event_score_file_path, index_col=0)
            manual_event_scores_map = df_scores["event_score"].to_dict()
    except Exception:
        manual_event_scores_map = {}

    # 全局分布 (新算法 total_score 的 mean/std, 供 z_score)
    global_stats = {}
    GLOBAL_MEAN_SCORE = 0.0
    GLOBAL_STD_DEV_SCORE = 1.0
    try:
        with open(output_stats_file, "r") as f:
            global_stats = json.load(f)
        GLOBAL_MEAN_SCORE = global_stats.get("global_mean_performance_score", 0.0) or 0.0
        GLOBAL_STD_DEV_SCORE = global_stats.get("global_std_dev_performance_score", 1.0) or 1.0
    except Exception:
        pass

    all_events_summary_list = []
    group_stages = evp_exp.EVP_CONFIG["GROUP_STAGES"]

    for webstart in event_urls:
        event_id = get_event_id_from_url(webstart)
        if not event_id:
            continue
        current_event_name = webstart.split("/")[-1]
        print(f"\n--- (Step 3) 正在处理: {current_event_name} ---")

        target_directory = os.path.join(base_directory, event_id)
        raw_data_file_path = os.path.join(target_directory, f"raw_event_{event_id}_data.xlsx")
        evp_summary_file_path = os.path.join(target_directory, f"event_{event_id}_evp_summary.xlsx")
        if not os.path.exists(raw_data_file_path):
            continue

        current_event_score = manual_event_scores_map.get(current_event_name, 0.0)
        print(f"加载赛事含金量: {current_event_score:.4f}")

        # ---- 新算法计算 (替换旧 calculate_performance_score 汇总逻辑) ----
        # 两套分拆 (2026-09-10): 交付物 cfg 逐赛事取段 (CS:GO=冻结源原样 / CS2=+机制覆写),
        # 与 eval_full 评估口径一致 — 否则 CS2 交付物会静默丢机制 (回退到 42 核纯公式总分).
        _seg = ev.segment_of(event_id)
        step3_cfg = evp_exp.cfg_for(_seg)
        summary, bo_all, map_all, _details = evp_exp.run_experiment(
            raw_data_file_path, None, None, cfg=step3_cfg, save=False)

        # ---- 保留: EVP_Summary 列结构 (值来自新算法) ----
        s = summary.copy()
        s["evp_score"] = s["total_score"]
        s["normalized_score"] = s["total_score"]
        if GLOBAL_STD_DEV_SCORE and GLOBAL_STD_DEV_SCORE > 0:
            s["z_score"] = (s["total_score"] - GLOBAL_MEAN_SCORE) / GLOBAL_STD_DEV_SCORE
        else:
            s["z_score"] = 0.0
        s["weighted_evp_score"] = s["evp_score"] * current_event_score

        s["Raw_Group_Score"] = s["group_bo_total"]
        s["Raw_Playoff_Score"] = s["playoff_bo_total"]
        s["Norm_Group_Score"] = s["group_effective"]
        s["Norm_Group_Score_Scaled"] = s["group_soft_capped"]
        s["Norm_Playoff_Score"] = s["playoff_soft_capped"]

        # 保留: 加权回合数列 (按阶段对单图回合数求和)
        m = map_all.copy()
        m["is_group"] = m["match_stage"].isin(group_stages)
        grp_rounds = m[m["is_group"]].groupby("player")["total_rounds"].sum()
        po_rounds = m[~m["is_group"]].groupby("player")["total_rounds"].sum()
        s = s.merge(grp_rounds.rename("group_weighted_rounds_played"), on="player", how="left")
        s = s.merge(po_rounds.rename("playoff_weighted_rounds_played"), on="player", how="left")
        s["group_weighted_rounds_played"] = s["group_weighted_rounds_played"].fillna(0).astype(int)
        s["playoff_weighted_rounds_played"] = s["playoff_weighted_rounds_played"].fillna(0).astype(int)
        s["total_weighted_rounds_played"] = s["group_weighted_rounds_played"] + s["playoff_weighted_rounds_played"]
        s["total_weighted_score"] = s["Raw_Group_Score"] + s["Raw_Playoff_Score"]

        cols = ["player", "evp_score", "weighted_evp_score", "z_score", "normalized_score",
                "Norm_Group_Score_Scaled", "Norm_Playoff_Score", "Norm_Group_Score",
                "Raw_Group_Score", "Raw_Playoff_Score", "group_weighted_rounds_played",
                "playoff_weighted_rounds_played", "total_weighted_score", "total_weighted_rounds_played"]
        player_summary_reset = s.sort_values("evp_score", ascending=False)[cols].copy()
        player_summary_reset["evp_score"] = player_summary_reset["evp_score"].round(4)
        player_summary_reset["weighted_evp_score"] = player_summary_reset["weighted_evp_score"].round(4)
        player_summary_reset["z_score"] = player_summary_reset["z_score"].round(4)
        player_summary_reset["normalized_score"] = player_summary_reset["normalized_score"].round(4)

        data_for_global = player_summary_reset.copy()
        data_for_global["event_id"] = event_id
        data_for_global["event_name"] = current_event_name
        data_for_global["event_score"] = current_event_score
        all_events_summary_list.append(data_for_global)

        # ---- 保留: Per_Map_Scores sheet (新算法单图给分 map_score) ----
        pm = map_all[["player", "team", "opponent", "opponent_rank", "match_stage",
                      "round_differential", "total_rounds", "rating"]].copy()
        pm["perf_score_raw"] = map_all["map_score"]
        pm["perf_score_weighted"] = map_all["map_score"] * map_all["total_rounds"]
        pm = pm.round({"perf_score_raw": 6, "perf_score_weighted": 6})

        # ---- 保留: 输出 event_{eid}_evp_summary.xlsx (受 WRITE_EVENTS 门控; 行数据始终进透视表) ----
        if WRITE_EVENTS not in ("all", _seg):
            print(f"--- 跳过写出 ({_seg} 段, EVP_WRITE_EVENTS={WRITE_EVENTS}): {evp_summary_file_path} ---")
        else:
            print(f"--- 正在保存 *单个* 赛事EVP总结 (新算法 + 赛事含金量): {evp_summary_file_path} ---")
            try:
                with pd.ExcelWriter(evp_summary_file_path, engine="openpyxl") as writer:
                    player_summary_reset.to_excel(writer, index=False, sheet_name=f"EVP_Summary_{event_id}")
                    pm.to_excel(writer, index=False, sheet_name="Per_Map_Scores")
                print(f"成功保存总结和地图详情到: {evp_summary_file_path}")
            except Exception as e:
                print(f"错误: 保存 *单个* 赛事EVP总结文件失败: {e}")

    # ---- 保留: 全局透视表 (evp_score × 赛事, EVENT_SCORE 行, 列排序) ----
    print("\n===========================================================")
    print("(Step 3) 所有赛事处理完毕。正在汇总所有数据...")
    if not all_events_summary_list:
        print("未收集到任何赛事数据。")
    else:
        global_summary_df = pd.concat(all_events_summary_list, ignore_index=True)
        print("正在创建EVP分数的数据透视表 (Pivoting data)...")
        try:
            values_to_pivot = ["evp_score", "weighted_evp_score"]
            pivot_df = pd.pivot_table(
                global_summary_df, values=values_to_pivot,
                index=["player"], columns=["event_name"], aggfunc="mean")
            try:
                pivot_df[("Overall", "Sum_Weighted_EVP")] = pivot_df["weighted_evp_score"].sum(axis=1)
                pivot_df = pivot_df.sort_values(by=("Overall", "Sum_Weighted_EVP"), ascending=False)
            except KeyError:
                try:
                    fallback_sort_col = pivot_df["weighted_evp_score"].columns[0]
                    pivot_df = pivot_df.sort_values(by=("weighted_evp_score", fallback_sort_col), ascending=False)
                except Exception:
                    pass

            event_scores_map = manual_event_scores_map
            event_score_row = pd.DataFrame(columns=pivot_df.columns, index=["EVENT_SCORE"])
            for event_name in event_scores_map.keys():
                if ("evp_score", event_name) in event_score_row.columns:
                    event_score_row.loc["EVENT_SCORE", ("evp_score", event_name)] = event_scores_map.get(event_name, 0)
            if ("Overall", "Sum_Weighted_EVP") in event_score_row.columns:
                event_score_row[("Overall", "Sum_Weighted_EVP")] = "---"

            pivot_df_final = pd.concat([event_score_row, pivot_df])
            if "weighted_evp_score" in pivot_df_final.columns.get_level_values(0):
                pivot_df_final = pivot_df_final.drop(columns="weighted_evp_score", level=0)

            new_columns = []
            for col_level0, col_level1 in pivot_df_final.columns:
                if col_level0 == "Overall":
                    new_columns.append(col_level1)
                else:
                    new_columns.append(col_level1 if col_level1 else col_level0)
            pivot_df_final.columns = new_columns
            pivot_df_final.index.name = "Player"
            pivot_df_final.columns.name = None

            event_name_order = [url.split("/")[-1] for url in event_urls]
            all_current_cols = pivot_df_final.columns.tolist()
            ordered_event_cols = [name for name in event_name_order if name in all_current_cols]
            overall_cols = [col for col in all_current_cols if col not in ordered_event_cols]
            final_column_order = ordered_event_cols + overall_cols
            pivot_df_final = pivot_df_final[final_column_order]

            pivot_df_final = pivot_df_final.fillna(0)
            pivot_df_final = pivot_df_final.round(4)
            if "Sum_Weighted_EVP" in pivot_df_final.columns:
                pivot_df_final.loc["EVENT_SCORE", "Sum_Weighted_EVP"] = "---"

            print(f"正在写入数据透视表到: {global_summary_file_path}")
            with pd.ExcelWriter(global_summary_file_path, engine="openpyxl") as writer:
                pivot_df_final.to_excel(writer, sheet_name="EVP_Pivot_Summary")

                # ---- 新增: 赛事权重子表 (含金量从高到低) ----
                try:
                    weights_df = pd.read_excel(event_score_file_path)
                    weights_df = weights_df.rename(columns={"event_name": "slug"})
                    # join MVP 名单拿可读赛事名与 event_id
                    mvp_df = pd.read_excel(MVP_LIST_FILE)
                    mvp_df["slug"] = mvp_df["url"].astype(str).str.split("/").str[-1]
                    info = mvp_df[["event_id", "event_name", "slug"]].drop_duplicates("slug")
                    weights_df = weights_df.merge(info, on="slug", how="left")
                    weights_df["event_name"] = weights_df["event_name"].fillna(weights_df["slug"])
                    weights_df = weights_df.sort_values("event_score", ascending=False).reset_index(drop=True)
                    weights_df.insert(0, "Rank", range(1, len(weights_df) + 1))
                    wcols = [c for c in ["Rank", "event_id", "event_name", "event_score"]
                             if c in weights_df.columns]
                    weights_df = weights_df[wcols]
                    weights_df.to_excel(writer, index=False, sheet_name="赛事权重")
                    print(f"已写入赛事权重子表 ({len(weights_df)} 个赛事, 含金量降序)")
                except Exception as e:
                    print(f"警告: 写赛事权重子表失败: {e}")
            print("成功。")
        except Exception as e:
            print(f"创建数据透视表错误: {e}")
            try:
                backup_path = global_summary_file_path.replace(".xlsx", "_long_format_backup.xlsx")
                global_summary_df.to_excel(backup_path, index=False)
                print(f"已保存 'long format' 备份文件到: {backup_path}")
            except Exception:
                pass

    print("\n===========================================================")
    print("  Step 3 执行完毕。")
    print("===========================================================")


def run_step1_5_calculate_event_scores():
    """(Step 1.5, eventrank) 计算赛事含金量权重并刷新 event_scores_lookup.xlsx.

    复用 eventrank.py 的参数化计算 (传入本脚本同一份配置),
    实现 hltv evp.py 一站式: 爬虫 → 含金量 → 全局统计 → EVP.
    """
    print("\n===========================================================")
    print("  Step 1.5 (eventrank): 计算赛事含金量 (赛事队伍总分 / 当期世界总得分)")
    print("===========================================================")
    try:
        result = eventrank.calculate_all_event_weights(
            event_urls_=event_urls, base_directory_=base_directory,
            rank_db_directory_=rank_db_directory, event_score_file_path_=event_score_file_path)
        print(f"  -> 共计算 {len(result)} 个赛事的含金量系数, 已写入 {event_score_file_path}")
        return len(result) > 0
    except Exception as e:
        print(f"错误: 计算赛事含金量失败: {e}")
        return False


if __name__ == "__main__":
    # 注意: 主流程现已一站式:
    # Step 0 更新排名快照 (hltv rank) → Step 1 爬取数据 → Step 1.5 赛事含金量 (eventrank)
    #   → Step 2 全局统计 → Step 3 EVP 汇总
    # (原先手动运行 hltv rank.py / event_weight_calculator.py 的环节均已集成)

    run_step0_update_rank()

    step1_success = run_step1_scrape_data()

    step1_5_success = False
    if step1_success:
        step1_5_success = run_step1_5_calculate_event_scores()
    else:
        print("错误: Step 1 失败。")

    step2_success = False
    if step1_5_success:
        step2_success, _, _ = run_step2_calculate_global_stats()
    else:
        print("错误: Step 1.5 (赛事含金量计算) 失败, 跳过 Step 2/3。")

    if step2_success:
        run_step3_calculate_evp_pivot()
    elif step1_5_success:
        print("错误: Step 2 失败。")

    print("\n所有分析步骤已执行完毕。")