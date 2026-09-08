import re
import os
import json
import math
import pandas as pd
from openpyxl.utils.dataframe import dataframe_to_rows
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# ----------------------------------------------------------------------
# 1. 
# 全局配置区
# ----------------------------------------------------------------------

# !! 必须与 Step 1 (爬虫) 脚本中的列表保持一致 !!
event_urls = [
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

eventfilter = [
    "&event=8246",
    "&event=8240","&event=8047","&event=8413","&event=8248","&event=8048","&event=8242","&event=8250","&event=8049","&event=8243","&event=8263","&event=8301"
]

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
# 3. 
# (Step 1) 真实数据抓取 (保持不变)
# ----------------------------------------------------------------------

def run_step1_scrape_data():
    print("===========================================================")
    print("  运行 Step 1 (真实爬虫): 抓取原始数据 (按地图)")
    print("===========================================================")
        
    all_events_scraped_successfully = True
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
            print(f"检测到已存在的数据: {raw_data_file_path}，跳过抓取。")
            continue

        print(f"未找到缓存，开始抓取: {current_event_name}")
        
        all_player_raw_stats = [] 
        team_rank_map = {}
        timeout = 15
        keyword = ">" 
        
        try:
            driver = uc.Chrome(version_main=147)
            driver.get(url)
            try:
                WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CLASS_NAME, "event-world-rank")))
            except: pass
            
            content = driver.page_source

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

            team_name = re.findall('<div class="text">(.*?)<',content)
            team_rank_raw = re.findall('<div class="event-world-rank" title=".*?">#(.*?)<', content)
            team_rank_clean = [r for r in team_rank_raw if r.isdigit()]
            
            for idx in range(min(len(team_name), len(team_rank_clean))):
                team_rank_map[team_name[idx]] = int(team_rank_clean[idx])
            
            try: current_filter = eventfilter[i]
            except: current_filter = f"&event={event_id}"

            filter_param = current_filter.lstrip('&') 
            webnext = f"https://www.hltv.org/results?{filter_param}"
            
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
                driver.get(match_url)
                try:
                    WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((By.CLASS_NAME, "statsPlayerName")))
                except: continue
                
                content = driver.page_source

                game_score = re.findall('<div class="results-team-score">(.*?)<', content)
                game_team_name = re.findall('<div class="results-teamname text-ellipsis">(.*?)<', content)
                game_player_name = re.findall('<div class="smartphone-only statsPlayerName text-ellipsis">(.*?)<', content)
                game_total_rating = re.findall('<td class="rating text-center rating(.*?)<', content)
                
                stage_match_raw = re.findall('preformatted-text">(.*?)</', content, re.DOTALL)
                
                if not stage_match_raw: match_stage = "Groups"
                elif "Online" in stage_match_raw[0] or "online" in stage_match_raw[0]: match_stage = "Online" 
                elif "Quarter-final" in stage_match_raw[0]: match_stage = "Quarter-final"
                elif "Semi-final" in stage_match_raw[0]: match_stage = "Semi-final"
                elif "Grand final" in stage_match_raw[0]: match_stage = "Grand final"
                elif "3rd place" in stage_match_raw[0]: match_stage = "3rd place"
                else: match_stage = "Groups"

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

                        for j in range(PLAYERS_PER_TEAM):
                            player_idx = t1_start_idx + j
                            all_player_raw_stats.append({
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
                            })

                        for j in range(PLAYERS_PER_TEAM):
                            player_idx = t2_start_idx + j
                            all_player_raw_stats.append({
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
                            })

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
                    all_events_scraped_successfully = False
            else:
                print(f"警告：赛事 {current_event_name} 未抓取到数据。")
                all_events_scraped_successfully = False

        except Exception as e:
            print(f"严重错误: {e}")
            all_events_scraped_successfully = False
        
        finally:
            if driver: driver.quit()
            
    return all_events_scraped_successfully


# ----------------------------------------------------------------------
# 4. 
# (Step 2) 全局统计计算 (权重逻辑已抽离到外部独立文件)
# ----------------------------------------------------------------------

def run_step2_calculate_global_stats():
    print("\n===========================================================")
    print("  运行 Step 2 (来自 1.py): 计算全局统计数据")
    print("===========================================================")

    all_player_summary_dataframes = [] 
    all_event_scores_for_saving = {} 

    # 尝试读取外部独立脚本计算好的赛事含金量表
    try:
        if os.path.exists(event_score_file_path):
            df_scores = pd.read_excel(event_score_file_path, index_col=0)
            all_event_scores_for_saving = df_scores['event_score'].to_dict()
            print(f"成功加载 {len(all_event_scores_for_saving)} 条已存在的赛事含金量分数。")
    except Exception as e:
        print(f"加载 'event_scores_lookup.xlsx' 失败: {e}")
        all_event_scores_for_saving = {}

    print("\n--- (Step 2 - Pass 1) 正在循环所有赛事以收集 *并处理* 分数 ---")
    
    for url in event_urls:
        event_id = get_event_id_from_url(url)
        current_event_name = url.split('/')[-1]
        
        if not event_id: continue
        
        print(f"\n--- (Step 2 - Pass 1) 正在处理: {current_event_name} ---")

        raw_data_path = os.path.join(base_directory, event_id, f"raw_event_{event_id}_data.xlsx")
        
        if not os.path.exists(raw_data_path):
            print(f"错误: 原始数据文件 '{raw_data_path}' 未找到。跳过。")
            continue

        try:
            df = pd.read_excel(raw_data_path)
            
            if 'round_differential' not in df.columns:
                df['round_differential'] = 0
            
            df['stage_weight_value'] = df['match_stage'].apply(lambda x: stage_weight_map.get(x, 1.0))
            df['rank_weight'] = df['opponent_rank'].apply(get_rank_weight)
            df['match_weight'] = df['stage_weight_value'] * df['rank_weight']
            
            df['perf_score_raw'] = df.apply(
                lambda row: calculate_performance_score(
                    row['rating'],
                    row['stage_weight_value'],
                    row['rank_weight'],
                    row['team_avg_rating'],
                    row['match_baseline_rating'],
                    row['round_differential'] 
                ),
                axis=1
            )
            
            df['perf_score_weighted'] = df['perf_score_raw'] * df['total_rounds']
            df['weighted_rounds'] = df['total_rounds']
            
            df_playoffs = df[df['match_stage'].isin(PLAYOFF_STAGES)].copy()
            df_groups = df[~df['match_stage'].isin(PLAYOFF_STAGES)].copy()

            if not df_groups.empty:
                summary_groups = df_groups.groupby('player').agg(
                    group_score_uncapped=('perf_score_weighted', 'sum'),
                    group_weighted_rounds_played=('weighted_rounds', 'sum') 
                )
            else:
                summary_groups = pd.DataFrame(columns=['player', 'group_score_uncapped', 'group_weighted_rounds_played']).set_index('player')

            if not df_playoffs.empty:
                summary_playoffs = df_playoffs.groupby('player').agg(
                    playoff_score=('perf_score_weighted', 'sum'),
                    playoff_weighted_rounds_played=('weighted_rounds', 'sum')
                )
            else:
                summary_playoffs = pd.DataFrame(columns=['player', 'playoff_score', 'playoff_weighted_rounds_played']).set_index('player')

            player_summary = pd.concat([summary_groups, summary_playoffs], axis=1).fillna(0)
            
            event_average_group_rounds = player_summary['group_weighted_rounds_played'].mean()
            if event_average_group_rounds == 0 or pd.isna(event_average_group_rounds):
                event_average_group_rounds = 1.0 

            player_summary['player_length_coefficient'] = player_summary['group_weighted_rounds_played'] / event_average_group_rounds
            player_summary['applied_power'] = POWER_BOOST
            player_summary.loc[player_summary['player_length_coefficient'] > 1.0, 'applied_power'] = POWER_PENALTY
            
            player_summary['player_length_coefficient'] = player_summary['player_length_coefficient'].replace(0, 1.0) 
            player_summary['normalization_factor'] = (
                player_summary['player_length_coefficient'] ** player_summary['applied_power']
            )
            
            player_summary['normalized_group_score'] = player_summary['group_score_uncapped'] / player_summary['normalization_factor']
            player_summary['normalized_playoff_score'] = player_summary['playoff_score']

            player_summary['normalized_group_score_capped'] = player_summary['normalized_group_score'].apply(
                lambda x: apply_symmetrical_soft_cap(x, GROUP_STAGE_SCORE_CAP)
            )

            player_summary['normalized_score'] = player_summary['normalized_group_score_capped'] + player_summary['normalized_playoff_score']
            all_player_summary_dataframes.append(player_summary)
            
            # --- [赛事含金量获取] ---
            # 权重计算逻辑已单独提取至独立脚本
            if current_event_name in all_event_scores_for_saving:
                print(f"已加载外部计算的赛事含金量: {all_event_scores_for_saving[current_event_name]:.4f}")
            else:
                print(f"警告: 未在查找表中找到 {current_event_name} 的赛事含金量。请确保运行了权重计算脚本。")
                all_event_scores_for_saving[current_event_name] = 0.0
            
        except Exception as e:
            print(f"错误: 处理 {raw_data_path} 失败: {e}")
            continue

    global_stats_calculated = {}

    print("\n--- (Step 2 - Pass 2 & 3) 正在计算 *全局* 统计 ---")
    if not all_player_summary_dataframes:
        return False, None, None 
    else:
        global_df = pd.concat(all_player_summary_dataframes) 
        
        global_average_group_rounds = global_df['group_weighted_rounds_played'].mean()
        if global_average_group_rounds == 0: global_average_group_rounds = 1.0

        global_mean_score = 0 
        global_std_dev_score = global_df['normalized_score'].std()

        stats_data = {
            "global_mean_performance_score": global_mean_score,
            "global_std_dev_performance_score": global_std_dev_score,
            "global_average_group_rounds_played": global_average_group_rounds, 
            "total_player_records_processed": int(global_df['normalized_score'].count()),
            "total_events_processed": len(all_player_summary_dataframes)
        }
        global_stats_calculated = stats_data 
        
        try:
            with open(output_stats_file, 'w') as f:
                json.dump(stats_data, f, indent=4)
        except Exception as e:
            print(f"保存 global_stats.json 失败: {e}")
            return False, None, None 

    print("\nStep 2 执行完毕。")
    return True, global_stats_calculated, all_event_scores_for_saving


# ----------------------------------------------------------------------
# 5. 
# (Step 3) EVP 计算与汇总 (保持不变)
# ----------------------------------------------------------------------

def run_step3_calculate_evp_pivot():
    print("\n===========================================================")
    print("  运行 Step 3 (来自 hltv evp.py): 计算EVP并生成汇总")
    print("===========================================================")

    manual_event_scores_map = {}
    
    try:
        if os.path.exists(event_score_file_path):
            df_scores = pd.read_excel(event_score_file_path, index_col=0) 
            manual_event_scores_map = df_scores['event_score'].to_dict()
    except Exception:
        manual_event_scores_map = {} 

    global_stats = {}
    GLOBAL_MEAN_SCORE = 0.0  
    GLOBAL_STD_DEV_SCORE = 1.0 

    try:
        with open(output_stats_file, 'r') as f:
            global_stats = json.load(f)
        GLOBAL_MEAN_SCORE = 0.0
        GLOBAL_STD_DEV_SCORE = global_stats.get("global_std_dev_performance_score", 1.0)
    except:
        return 

    all_events_summary_list = [] 

    for webstart in event_urls:

        event_id = get_event_id_from_url(webstart)
        if not event_id: continue 
        
        current_event_name = webstart.split('/')[-1]
        print(f"\n--- (Step 3) 正在处理: {current_event_name} ---")

        target_directory = os.path.join(base_directory, event_id)
        raw_data_file_path = os.path.join(target_directory, f"raw_event_{event_id}_data.xlsx")
        evp_summary_file_path = os.path.join(target_directory, f"event_{event_id}_evp_summary.xlsx")

        if not os.path.exists(raw_data_file_path): continue

        df = pd.read_excel(raw_data_file_path)
        all_player_raw_stats = df.to_dict('records')

        current_event_score = manual_event_scores_map.get(current_event_name, 0.0)
        print(f"加载赛事含金量: {current_event_score:.4f}")

        if 'round_differential' not in df.columns:
            df['round_differential'] = 0

        df['stage_weight_value'] = df['match_stage'].apply(lambda x: stage_weight_map.get(x, 1.0))
        df['rank_weight'] = df['opponent_rank'].apply(get_rank_weight)
        
        df['perf_score_raw'] = df.apply(
            lambda row: calculate_performance_score(
                row['rating'],
                row['stage_weight_value'], 
                row['rank_weight'],       
                row['team_avg_rating'],
                row['match_baseline_rating'],
                row['round_differential'] 
            ),
            axis=1
        )
        
        df['perf_score_weighted'] = df['perf_score_raw'] * df['total_rounds']
        df['weighted_rounds'] = df['total_rounds']
        
        df_playoffs = df[df['match_stage'].isin(PLAYOFF_STAGES)].copy()
        df_groups = df[~df['match_stage'].isin(PLAYOFF_STAGES)].copy()

        if not df_groups.empty:
            summary_groups = df_groups.groupby('player').agg(
                group_score_uncapped=('perf_score_weighted', 'sum'),
                group_weighted_rounds_played=('weighted_rounds', 'sum') 
            )
        else:
            summary_groups = pd.DataFrame(columns=['player', 'group_score_uncapped', 'group_weighted_rounds_played']).set_index('player')

        if not df_playoffs.empty:
            summary_playoffs = df_playoffs.groupby('player').agg(
                playoff_score=('perf_score_weighted', 'sum'),
                playoff_weighted_rounds_played=('weighted_rounds', 'sum')
            )
        else:
            summary_playoffs = pd.DataFrame(columns=['player', 'playoff_score', 'playoff_weighted_rounds_played']).set_index('player')

        player_summary = pd.concat([summary_groups, summary_playoffs], axis=1).fillna(0)
        
        player_summary['total_weighted_score'] = player_summary['group_score_uncapped'] + player_summary['playoff_score']
        player_summary['total_weighted_rounds_played'] = player_summary['group_weighted_rounds_played'] + player_summary['playoff_weighted_rounds_played']

        event_average_group_rounds = player_summary['group_weighted_rounds_played'].mean()
        if event_average_group_rounds == 0: event_average_group_rounds = 1.0 

        player_summary['player_length_coefficient'] = player_summary['group_weighted_rounds_played'] / event_average_group_rounds
            
        player_summary['applied_power'] = POWER_BOOST
        player_summary.loc[player_summary['player_length_coefficient'] > 1.0, 'applied_power'] = POWER_PENALTY
        
        player_summary['player_length_coefficient'] = player_summary['player_length_coefficient'].replace(0, 1.0) 
        player_summary['normalization_factor'] = (
            player_summary['player_length_coefficient'] ** player_summary['applied_power']
        )

        player_summary['normalized_group_score'] = player_summary['group_score_uncapped'] / player_summary['normalization_factor']
        player_summary['normalized_playoff_score'] = player_summary['playoff_score']

        player_summary['normalized_group_score_capped'] = player_summary['normalized_group_score'].apply(
            lambda x: apply_symmetrical_soft_cap(x, GROUP_STAGE_SCORE_CAP)
        )

        player_summary['normalized_score'] = player_summary['normalized_group_score_capped'] + player_summary['normalized_playoff_score']
        
        if 'player_length_coefficient' in player_summary.columns:
            columns_to_drop = ['player_length_coefficient', 'applied_power', 'normalization_factor']
            player_summary = player_summary.drop(columns=[c for c in columns_to_drop if c in player_summary.columns])
        
        player_summary = player_summary.rename(columns={
            'group_score_uncapped': 'Raw_Group_Score',
            'playoff_score': 'Raw_Playoff_Score',
            'normalized_group_score_capped': 'Norm_Group_Score_Scaled',
            'normalized_group_score': 'Norm_Group_Score', 
            'normalized_playoff_score': 'Norm_Playoff_Score' 
        })
        
        if GLOBAL_STD_DEV_SCORE == 0 or pd.isna(GLOBAL_STD_DEV_SCORE):
            player_summary['evp_score'] = 0
            player_summary['z_score'] = 0
        else:
            player_summary['z_score'] = player_summary['normalized_score'].apply(
                lambda score: (score - GLOBAL_MEAN_SCORE) / GLOBAL_STD_DEV_SCORE
            )
            player_summary['evp_score'] = player_summary['z_score'].apply(
                 lambda z_score: BASIC_EVP_POINT + math.copysign(1, z_score) * MULTIPLE_EVP_POINT * math.log1p(abs(z_score))
            )
        
        player_summary['evp_score'] = player_summary['evp_score'].apply(lambda x:x)

        player_summary = player_summary.sort_values(by='evp_score', ascending=False)
        player_summary['total_weighted_score'] = player_summary['total_weighted_score'].round(4) 
        player_summary['normalized_score'] = player_summary['normalized_score'].round(4)
        player_summary['evp_score'] = player_summary['evp_score'].round(4)

        player_summary_reset = player_summary.reset_index() 
        player_summary_reset['weighted_evp_score'] = player_summary_reset['evp_score'] * current_event_score
        
        data_for_global = player_summary_reset.copy()
        data_for_global['event_id'] = event_id
        data_for_global['event_name'] = current_event_name
        data_for_global['event_score'] = current_event_score
        all_events_summary_list.append(data_for_global)

        print(f"--- 正在保存 *单个* 赛事EVP总结 (含每场详情): {evp_summary_file_path} ---")
        try:
            columns_to_save = [
                'player', 'evp_score', 'weighted_evp_score', 'z_score',
                'normalized_score', 
                'Norm_Group_Score_Scaled', 'Norm_Playoff_Score', 
                'Norm_Group_Score', 
                'Raw_Group_Score', 'Raw_Playoff_Score',
                'group_weighted_rounds_played', 'playoff_weighted_rounds_played', 
                'total_weighted_score', 'total_weighted_rounds_played'
            ]
            existing_columns_to_save = [col for col in columns_to_save if col in player_summary_reset.columns]
            
            # [恢复] 地图详情 Sheet 保存逻辑
            columns_for_match_sheet = [
                'player', 'team', 'opponent', 'opponent_rank', 'match_stage', 
                'round_differential', 
                'total_rounds', 'rating', 
                'perf_score_raw', 'perf_score_weighted'
            ]
            existing_match_cols = [col for col in columns_for_match_sheet if col in df.columns]
            
            df_match_details_to_save = df[existing_match_cols].copy()
            
            with pd.ExcelWriter(evp_summary_file_path, engine='openpyxl') as writer:
                player_summary_reset.to_excel(
                    writer, 
                    index=False, 
                    sheet_name=f"EVP_Summary_{event_id}",
                    columns=existing_columns_to_save
                )
                df_match_details_to_save.to_excel(
                    writer,
                    index=False,
                    sheet_name="Per_Map_Scores" 
                )

            print(f"成功保存总结和地图详情到: {evp_summary_file_path}")

        except Exception as e:
            print(f"错误: 保存 *单个* 赛事EVP总结文件失败: {e}")


    # --- 5.3. (Step 3) 汇总所有赛事并保存为数据透视表 ---
    print("\n===========================================================")
    print("(Step 3) 所有赛事处理完毕。正在汇总所有数据...")

    if not all_events_summary_list:
        print("未收集到任何赛事数据。")
    else:
        global_summary_df = pd.concat(all_events_summary_list, ignore_index=True)
        print("正在创建EVP分数的数据透视表 (Pivoting data)...")
        
        try:
            values_to_pivot = ['evp_score', 'weighted_evp_score']
            
            pivot_df = pd.pivot_table(
                global_summary_df,
                values=values_to_pivot,
                index=['player'],
                columns=['event_name'],
                aggfunc='mean'
            )

            try:
                pivot_df[('Overall', 'Sum_Weighted_EVP')] = pivot_df['weighted_evp_score'].sum(axis=1)
                pivot_df = pivot_df.sort_values(by=('Overall', 'Sum_Weighted_EVP'), ascending=False)
            except KeyError as e:
                try:
                    fallback_sort_col = pivot_df['weighted_evp_score'].columns[0]
                    pivot_df = pivot_df.sort_values(by=('weighted_evp_score', fallback_sort_col), ascending=False)
                except Exception: pass 

            event_scores_map = manual_event_scores_map 
            event_score_row = pd.DataFrame(columns=pivot_df.columns, index=['EVENT_SCORE'])
            
            for event_name in event_scores_map.keys():
                if ('evp_score', event_name) in event_score_row.columns:
                    event_score_row.loc['EVENT_SCORE', ('evp_score', event_name)] = event_scores_map.get(event_name, 0)
            
            if ('Overall', 'Sum_Weighted_EVP') in event_score_row.columns:
                event_score_row[('Overall', 'Sum_Weighted_EVP')] = '---'

            pivot_df_final = pd.concat([event_score_row, pivot_df])

            if 'weighted_evp_score' in pivot_df_final.columns.get_level_values(0):
                pivot_df_final = pivot_df_final.drop(columns='weighted_evp_score', level=0)

            # [恢复] 复杂的列排序逻辑
            new_columns = []
            for col_level0, col_level1 in pivot_df_final.columns:
                if col_level0 == 'Overall':
                    new_columns.append(col_level1) 
                else:
                    new_columns.append(col_level1 if col_level1 else col_level0) 
            pivot_df_final.columns = new_columns
            pivot_df_final.index.name = 'Player' 
            pivot_df_final.columns.name = None 

            event_name_order = [url.split('/')[-1] for url in event_urls]
            all_current_cols = pivot_df_final.columns.tolist()
            ordered_event_cols = [name for name in event_name_order if name in all_current_cols]
            overall_cols = [col for col in all_current_cols if col not in ordered_event_cols]
            final_column_order = ordered_event_cols + overall_cols
            pivot_df_final = pivot_df_final[final_column_order]

            pivot_df_final = pivot_df_final.fillna(0) 
            pivot_df_final = pivot_df_final.round(4)
            if 'Sum_Weighted_EVP' in pivot_df_final.columns:
                pivot_df_final.loc['EVENT_SCORE', 'Sum_Weighted_EVP'] = '---'

            print(f"正在写入数据透视表到: {global_summary_file_path}")
            pivot_df_final.to_excel(global_summary_file_path, sheet_name="EVP_Pivot_Summary")
            print("成功。")

        except Exception as e:
            print(f"创建数据透视表错误: {e}")
            try:
                backup_path = global_summary_file_path.replace('.xlsx', '_long_format_backup.xlsx')
                global_summary_df.to_excel(backup_path, index=False)
                print(f"已保存 'long format' 备份文件到: {backup_path}")
            except: pass

    print("\n===========================================================")
    print("  Step 3 执行完毕。")
    print("===========================================================")


# ----------------------------------------------------------------------
# 6. 
# 脚本主入口
# ----------------------------------------------------------------------

if __name__ == "__main__":
    # 注意：现在的主流程是：
    # 先运行主脚本，让它执行跑通一次 Step 1 爬取数据；
    # 然后运行外部独立的 event_weight_calculator.py 生成权重表；
    # 接着再运行主脚本跑通 Step 2 和 Step 3。
    
    step1_success = run_step1_scrape_data()
    
    step2_success = False
    if step1_success:
        step2_success, _, _ = run_step2_calculate_global_stats()
    else:
        print("错误: Step 1 失败。")

    if step2_success:
        run_step3_calculate_evp_pivot()
    elif step1_success: 
        print("错误: Step 2 失败。")
        
    print("\n所有分析步骤已执行完毕。")