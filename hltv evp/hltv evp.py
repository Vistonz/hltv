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
    "https://www.hltv.org/events/7903/blast-bounty-2025-season-1",
    "https://www.hltv.org/events/8034/iem-katowice-2025",
    "https://www.hltv.org/events/8043/pgl-cluj-napoca-2025",
    "https://www.hltv.org/events/8292/esl-pro-league-season-21",
    "https://www.hltv.org/events/7904/blast-open-lisbon-2025",
    "https://www.hltv.org/events/8044/pgl-bucharest-2025",
    "https://www.hltv.org/events/8036/iem-melbourne-2025",
    "https://www.hltv.org/events/7905/blast-rivals-2025-season-1",
    "https://www.hltv.org/events/8045/pgl-astana-2025",
    "https://www.hltv.org/events/8037/iem-dallas-2025",
    "https://www.hltv.org/events/7902/blasttv-austin-major-2025",
    "https://www.hltv.org/events/8063/fissure-playground-1",
    "https://www.hltv.org/events/8038/iem-cologne-2025",
    "https://www.hltv.org/events/7906/blast-bounty-2025-season-2",
    "https://www.hltv.org/events/8039/esports-world-cup-2025",
    "https://www.hltv.org/events/7907/blast-open-london-2025",
    "https://www.hltv.org/events/8064/fissure-playground-2",
    "https://www.hltv.org/events/8040/esl-pro-league-season-22",
    "https://www.hltv.org/events/8027/cs-asia-championships-2025",
    "https://www.hltv.org/events/8067/thunderpick-world-championship-2025",
    "https://www.hltv.org/events/8046/pgl-masters-bucharest-2025",
    "https://www.hltv.org/events/8041/iem-chengdu-2025",
    "https://www.hltv.org/events/7908/blast-rivals-2025-season-2",
    "https://www.hltv.org/events/8042/starladder-budapest-major-2025"
]

eventfilter = [
    "&event=7909&event=7903",  "&event=8034", "&event=8043",
    "&event=8292", "&event=7904", "&event=8044", "&event=8036",
    "&event=7905", "&event=8045", "&event=8037",
    "&event=7902","&event=8063","&event=8038","&event=7910&event=7906",
    "&event=8039","&event=7912&event=7907","&event=8064","&event=8040",
    "&event=8027","&event=8067","&event=8046","&event=8041","&event=7908","&event=8042"
]

# (回合) 长度归一化参数 (幂)
POWER_PENALTY = 1
POWER_BOOST = 0.5
BASIC_EVP_POINT = 0
MULTIPLE_EVP_POINT = 5.5
UPPER_POWER = 1.2

# ----------------- [路径配置] -----------------
# 基础路径
base_directory = "C:\\Users\\10725\\Desktop\\hltv\\database\\event"
# 排名数据库路径
rank_db_directory = "C:\\Users\\10725\\Desktop\\hltv\\database\\rank"
# 赛事日期映射文件路径
date_mapping_file = "C:\\Users\\10725\\Desktop\\hltv\\hltv evp\\副本2025年各赛事使用的HLTV排名日期.xlsx"

# (文件路径)
output_stats_file = os.path.join(base_directory, "global_stats.json")
event_score_file_path = os.path.join(base_directory, "event_scores_lookup.xlsx")
global_summary_file_path = os.path.join("C:\\Users\\10725\\Desktop\\hltv\\hltv evp", "global_evp_pivot_summary.xlsx")

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

# [新增] 赛事ID与 Excel 表格名称的映射 (用于从 Sheet3 查找日期)
EVENT_ID_TO_SHEET3_NAME = {
    "7903": "BLAST赏金赛 S1-线上",
    "8034": "IEM卡托维兹", 
    "8043": "PGL克卢日—纳波卡",
    "8292": "EPL  S21", 
    "7904": "BLAST里斯本",
    "8044": "PGL布加勒斯特",
    "8036": "IEM 墨尔本",
    "7905": "BLAST竞争赛 S1",
    "8045": "PGL阿斯塔纳",
    "8037": "IEM 达拉斯",
    "7902": "奥斯汀Major",
    "8063": "FPG 1",
    "8038": "IEM 科隆",
    "7906": "BLAST赏金赛 S2", 
    "8039": "EWC",
    "7907": "BLAST伦敦",
    "8064": "FPG 2",
    "8040": "EPL  S22",
    "8027": "CAC",
    "8067": "Thunderpick World",
    "8046": "PGL布加勒斯特 S2",
    "8041": "IEM 成都",
    "7908": "BLAST竞争赛 S2",
    "8042": "布达佩斯Major"
}

# [新增] 标准T1赛事总积分基准 (用于归一化赛事含金量)
# 假设前8名队伍总分约为 5000分左右 (基于归一化后的1000分制)。
STANDARD_TIER1_POINT_SUM = 5000.0


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

def load_event_date_map():
    print(f"正在加载赛事日期映射: {date_mapping_file}")
    try:
        df_map = pd.read_excel(date_mapping_file, sheet_name=2, header=None)
        
        event_date_map = {}
        for index, row in df_map.iterrows():
            try:
                name = str(row.iloc[1]).strip()
                date_val = row.iloc[2]
                date_str = ""
                try:
                    ts = pd.to_datetime(date_val)
                    if not pd.isna(ts):
                        date_str = ts.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val).strip().split(' ')[0]
                except:
                    date_str = str(date_val).strip().split(' ')[0]

                if name and date_str and date_str.lower() != 'nan' and 'hltv' not in date_str.lower():
                    event_date_map[name] = date_str
            except Exception:
                continue
                
        print(f"已加载 {len(event_date_map)} 条赛事日期映射。")
        return event_date_map
    except Exception as e:
        print(f"加载日期映射文件失败: {e}")
        return {}

# [修改] 加载特定日期的队伍积分 (包含积分归一化逻辑 & 数据类型修复)
def load_team_points_for_date(date_str):
    target_path_xlsx = os.path.join(rank_db_directory, f"{date_str}.xlsx")
    target_path_csv = os.path.join(rank_db_directory, f"{date_str}.csv")
    
    df = pd.DataFrame()
    if os.path.exists(target_path_xlsx):
        print(f"正在加载排名文件: {target_path_xlsx}")
        try: df = pd.read_excel(target_path_xlsx)
        except: pass
    elif os.path.exists(target_path_csv):
        print(f"正在加载排名文件: {target_path_csv}")
        try: df = pd.read_csv(target_path_csv)
        except: pass
    else:
        print(f"警告: 未找到日期 {date_str} 的排名文件。")
        return {}

    df.columns = [c.strip() for c in df.columns]
    
    if 'Team Name' not in df.columns or 'Points' not in df.columns:
        return {}
    
    # --- 修复核心：强制转换 Points 为数字 ---
    df['Points'] = pd.to_numeric(df['Points'], errors='coerce')
    df = df.dropna(subset=['Points']) # 删除无法转为数字的行
    
    # [新增] 积分归一化逻辑
    try:
        max_points = df['Points'].max()
        if max_points > 0:
            scale_factor = 1000.0 / max_points
            print(f"  -> 此日期最高分为 {max_points}，归一化系数为 {scale_factor:.4f} (第一名将被视为1000分)")
            # 增加所有队伍分数
            df['Points'] = df['Points'] * scale_factor
    except Exception as e:
        print(f"  -> 积分归一化计算失败: {e}")

    points_map = {}
    for _, row in df.iterrows():
        team = str(row['Team Name']).strip()
        try:
            pts = float(row['Points'])
            points_map[team] = pts
            points_map[team.lower()] = pts
        except:
            continue
    return points_map

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
            driver = uc.Chrome()
            driver.get(url)
            try:
                WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CLASS_NAME, "event-world-rank")))
            except: pass
            
            content = driver.page_source
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
# (Step 2) 全局统计计算 (修改了积分计算逻辑 - 仅针对权重计算部分进行过滤)
# ----------------------------------------------------------------------

def run_step2_calculate_global_stats():
    print("\n===========================================================")
    print("  运行 Step 2 (来自 1.py): 计算全局统计数据")
    print("===========================================================")
    
    # [新增] 加载日期映射
    event_date_map = load_event_date_map()

    all_player_summary_dataframes = [] 
    all_event_scores_for_saving = {} 

    # [恢复] 尝试读取已有的赛事含金量表，以便保留旧数据
    try:
        if os.path.exists(event_score_file_path):
            df_scores = pd.read_excel(event_score_file_path, index_col=0)
            all_event_scores_for_saving = df_scores['event_score'].to_dict()
            print(f"成功加载 {len(all_event_scores_for_saving)} 条已存在的赛事含金量分数。")
    except Exception as e:
        print(f"加载 'event_scores_lookup.xlsx' 失败 (将重新计算所有): {e}")
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
            
            # --- [修改核心] 计算赛事含金量 (Event Score) ---
            # [恢复] 如果已存在，跳过计算
            if current_event_name in all_event_scores_for_saving:
                print(f"赛事含金量已存在: {all_event_scores_for_saving[current_event_name]:.4f}，跳过计算。")
            else:
                print("正在计算赛事含金量 (基于归一化后的积分)...")
                
                # 1. 找到对应的日期
                mapped_chinese_name = EVENT_ID_TO_SHEET3_NAME.get(event_id)
                event_date = None
                
                if mapped_chinese_name and mapped_chinese_name in event_date_map:
                    event_date = event_date_map[mapped_chinese_name]
                    print(f"匹配到赛事日期: {mapped_chinese_name} -> {event_date}")
                else:
                    print(f"警告: 无法在映射表中找到赛事 ID {event_id} ({mapped_chinese_name}) 的日期。")
                
                # 2. 加载积分 (已包含归一化逻辑)
                team_points_map = {}
                if event_date:
                    team_points_map = load_team_points_for_date(event_date)
                    
                if not team_points_map:
                    print("未加载到积分数据，将使用默认极低分数。")
                    
                # 3. 统计该赛事所有参赛队伍的积分总和
                
                # ==============================================================================
                # [新增/修改逻辑] 针对特定赛事，仅计算线下决赛（Playoffs）队伍权重
                # ==============================================================================
                
                # 定义哪些赛事属于"分裂赛事"或需要严格过滤的赛事
                SPLIT_EVENT_KEYWORDS = ["bounty"] # 你可以根据需要添加更多关键词
                
                # 判断当前赛事是否需要特殊处理
                is_split_event = any(kw in current_event_name for kw in SPLIT_EVENT_KEYWORDS)
                
                if is_split_event:
                    print(f"  -> [权重计算] 检测到分裂赛事 ({current_event_name})，仅提取淘汰赛阶段(Playoffs)队伍...")
                    
                    # 仅保留属于 Playoffs 阶段的行
                    # PLAYOFF_STAGES = ["Grand final", "Semi-final", "Quarter-final", "3rd place"]
                    df_filtered_for_weight = df[df['match_stage'].isin(PLAYOFF_STAGES)]
                    
                    if df_filtered_for_weight.empty:
                        print("     警告: 该分裂赛事未找到 Playoff 数据（可能是海选阶段数据），权重计算可能不准确。")
                        unique_teams = []
                    else:
                        unique_teams = pd.concat([df_filtered_for_weight['team'], df_filtered_for_weight['opponent']]).unique()
                        print(f"     已提取 {len(unique_teams)} 支决赛圈队伍进行权重计算。")
                else:
                    # 对于普通赛事，保留原有逻辑：计算所有出现过的队伍
                    unique_teams = pd.concat([df['team'], df['opponent']]).unique()
                
                # ==============================================================================
                
                event_total_points = 0.0
                
                for team in unique_teams:
                    # 尝试匹配积分 (精确或小写)
                    pts = team_points_map.get(team)
                    if pts is None:
                        pts = team_points_map.get(team.lower(), 0.0)
                    
                    if pts > 0:
                        event_total_points += pts
                
                print(f"赛事参赛队伍总积分 (归一化后): {event_total_points}")
                
                current_event_score = event_total_points / STANDARD_TIER1_POINT_SUM
                print(f"赛事含金量系数: {current_event_score:.4f}")
                
                all_event_scores_for_saving[current_event_name] = current_event_score
            
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

    print(f"\n--- (Step 2) 正在保存赛事含金量 ---")
    if all_event_scores_for_saving:
        try:
            df_to_save = pd.DataFrame.from_dict(
                all_event_scores_for_saving, 
                orient='index', 
                columns=['event_score']
            )
            df_to_save.index.name = 'event_name'
            
            # [新增] 对赛事含金量表进行简单的排序以匹配 urls 顺序
            event_name_order = [url.split('/')[-1] for url in event_urls]
            all_known_events = df_to_save.index.tolist()
            ordered_events = [name for name in event_name_order if name in all_known_events]
            other_events = [name for name in all_known_events if name not in event_name_order]
            final_order = ordered_events + other_events
            df_to_save = df_to_save.reindex(final_order)

            df_to_save.to_excel(event_score_file_path)
            print(f"成功保存赛事含金量记录: {event_score_file_path}")
        except Exception as e:
            print(f"保存赛事含金量表格失败: {e}")
            
    print("\nStep 2 执行完毕。")
    return True, global_stats_calculated, all_event_scores_for_saving


# ----------------------------------------------------------------------
# 5. 
# (Step 3) EVP 计算与汇总 (恢复了完整 Excel 格式化)
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