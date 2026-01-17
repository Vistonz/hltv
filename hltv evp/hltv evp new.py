import re
import os
import json
import math
import pandas as pd
import numpy as np
import time
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# ==============================================================================
# 1. 全局配置区 (Global Configuration)
# ==============================================================================

# --- 路径配置 (请修改为你电脑上的实际路径) ---
BASE_DIRECTORY = r"C:\Users\10725\Desktop\hltv\database\event"
RANK_DB_DIRECTORY = r"C:\Users\10725\Desktop\hltv\database\rank"
DATE_MAPPING_FILE = r"C:\Users\10725\Desktop\hltv\hltv evp\副本2025年各赛事使用的HLTV排名日期.xlsx"
OUTPUT_SUMMARY_FILE = os.path.join(r"C:\Users\10725\Desktop\hltv\hltv evp", "global_evp_penalty_summary.xlsx")
EVENT_SCORE_FILE = os.path.join(BASE_DIRECTORY, "event_scores_lookup.xlsx")

# --- 核心算分参数 (奖惩机制) ---
WINNER_BONUS_MULTIPLIER = 1.25   # [奖励] 表现好且赢了：得分 x 1.25
LOSER_PENALTY_MULTIPLIER = 1.25  # [惩罚] 表现差且输了：扣分 x 1.25 (让负分更负)
PASSENGER_PROTECTION = 0.75      # [保护] 表现差但赢了(躺赢)：扣分 x 0.75 (减轻惩罚)

UPPER_POWER = 1.0                # 表现分非线性指数 (1.0=线性)
BASE_WEIGHT_C = 0.5              # 对手排名权重基准
RANK_K = 6                       # 对手排名权重斜率
STANDARD_TIER1_POINT_SUM = 5000.0 # T1赛事满分基准分

# --- 阶段权重 ---
STAGE_WEIGHTS = {
    "Grand final": 1.75,
    "Semi-final": 1.25,
    "Quarter-final": 1.0,
    "3rd place": 0.5,
    "Groups": 1.0,
    "Online": 0.8
}

# --- 小组赛软上限 ---
GROUP_SCORE_CAP = 30.0
SOFT_CAP_LOG_BASE = 5

# --- 赛事列表 ---
EVENT_URLS = [
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

# --- 爬虫过滤器 ---
EVENT_FILTERS = [
    "&event=7909&event=7903", "&event=8034", "&event=8043", "&event=8292",
    "&event=7904", "&event=8044", "&event=8036", "&event=7905",
    "&event=8045", "&event=8037", "&event=7902", "&event=8063",
    "&event=8038", "&event=7910&event=7906", "&event=8039",
    "&event=7912&event=7907", "&event=8064", "&event=8040",
    "&event=8027", "&event=8067", "&event=8046", "&event=8041",
    "&event=7908", "&event=8042"
]

# --- ID映射 ---
EVENT_ID_TO_SHEET3_NAME = {
    "7903": "BLAST赏金赛 S1-线上", "8034": "IEM卡托维兹", "8043": "PGL克卢日—纳波卡",
    "8292": "EPL  S21", "7904": "BLAST里斯本", "8044": "PGL布加勒斯特",
    "8036": "IEM 墨尔本", "7905": "BLAST竞争赛 S1", "8045": "PGL阿斯塔纳",
    "8037": "IEM 达拉斯", "7902": "奥斯汀Major", "8063": "FPG 1",
    "8038": "IEM 科隆", "7906": "BLAST赏金赛 S2", "8039": "EWC",
    "7907": "BLAST伦敦", "8064": "FPG 2", "8040": "EPL  S22",
    "8027": "CAC", "8067": "Thunderpick World", "8046": "PGL布加勒斯特 S2",
    "8041": "IEM 成都", "7908": "BLAST竞争赛 S2", "8042": "布达佩斯Major"
}

# ==============================================================================
# 2. 辅助工具函数
# ==============================================================================

def get_event_id_from_url(url):
    match = re.search(r"[-+]?\d+\.?\d*|\.\d+", url)
    return match.group(0) if match else None

def get_rank_weight(opponent_rank):
    rank = opponent_rank if opponent_rank and opponent_rank > 0 else 30
    return BASE_WEIGHT_C + (RANK_K / (rank + 5))

def classify_stage(stage_name):
    if not isinstance(stage_name, str): return "Groups"
    if "Grand final" in stage_name: return "Final"
    elif any(x in stage_name for x in ["Semi-final", "Quarter-final", "3rd place"]): return "Bracket"
    else: return "Groups"

def apply_group_soft_cap(score):
    if score <= GROUP_SCORE_CAP: return score
    excess = score - GROUP_SCORE_CAP
    scaled_excess = GROUP_SCORE_CAP * math.log(1 + (excess / GROUP_SCORE_CAP), SOFT_CAP_LOG_BASE)
    return GROUP_SCORE_CAP + scaled_excess

def load_event_date_map():
    print(f"正在加载赛事日期映射: {DATE_MAPPING_FILE}")
    try:
        df_map = pd.read_excel(DATE_MAPPING_FILE, sheet_name=2, header=None)
        event_date_map = {}
        for index, row in df_map.iterrows():
            try:
                name = str(row.iloc[1]).strip()
                date_val = row.iloc[2]
                date_str = str(date_val).strip().split(' ')[0]
                if name: event_date_map[name] = date_str
            except: continue
        return event_date_map
    except Exception as e:
        print(f"加载日期映射失败: {e}")
        return {}

def load_team_points_for_date(date_str):
    target_path_xlsx = os.path.join(RANK_DB_DIRECTORY, f"{date_str}.xlsx")
    target_path_csv = os.path.join(RANK_DB_DIRECTORY, f"{date_str}.csv")
    
    df = pd.DataFrame()
    if os.path.exists(target_path_xlsx):
        try: df = pd.read_excel(target_path_xlsx)
        except: pass
    elif os.path.exists(target_path_csv):
        try: df = pd.read_csv(target_path_csv)
        except: pass
    
    if 'Team Name' not in df.columns or 'Points' not in df.columns: return {}
    
    df['Points'] = pd.to_numeric(df['Points'], errors='coerce')
    df = df.dropna(subset=['Points'])
    
    max_points = df['Points'].max()
    if max_points > 0:
        df['Points'] = df['Points'] * (1000.0 / max_points)
        
    points_map = {}
    for _, row in df.iterrows():
        team = str(row['Team Name']).strip()
        points_map[team] = float(row['Points'])
        points_map[team.lower()] = float(row['Points'])
    return points_map

# ==============================================================================
# 3. 核心计算引擎 (Updated with Penalty Logic)
# ==============================================================================

def calculate_map_score_v3(
    player_rating, 
    stage_weight, 
    rank_weight, 
    team_avg_rating, 
    match_baseline_rating, 
    round_differential 
):
    """
    [V3 算分核心: 奖惩系统]
    
    分为四种情况：
    1. Rating好 & 赢了: 胜者奖励 (Score * 1.25)
    2. Rating好 & 输了: 尽力局 (Score * 1.0)
    3. Rating差 & 赢了: 躺赢保护 (NegativeScore * 0.75) -> 扣分变少
    4. Rating差 & 输了: 战犯惩罚 (NegativeScore * 1.25) -> 扣分变多
    """
    
    # A. 表现差值 (Performance Delta)
    performance_delta = player_rating - (match_baseline_rating * 2 - team_avg_rating)
    team_context_delta = player_rating - team_avg_rating

    # B. 非线性转换
    def transform(val):
        sign = 1 if val >= 0 else -1
        return sign * 0.5 * math.pow(math.log1p(abs(val)), UPPER_POWER)

    perf_score = transform(performance_delta)
    team_score = transform(team_context_delta) * 1.5 
    raw_score = perf_score + team_score # 这是基础分，可正可负

    # C. 逻辑分流 (Positive vs Negative)
    
    final_score = 0.0

    if raw_score >= 0:
        # --- 表现出色 (Positive) ---
        stage_adjusted = raw_score * stage_weight
        final_base = stage_adjusted + raw_score * (rank_weight + 0.5)
        
        if round_differential > 0:
            # 赢了：Carry 奖励
            final_score = final_base * WINNER_BONUS_MULTIPLIER
        else:
            # 输了：SVP (无奖励，也不惩罚)
            final_score = final_base * 1.0

    else:
        # --- 表现糟糕 (Negative) ---
        # 此时 raw_score 是负数
        
        # 阶段权重修正：负分时通常减少惩罚 (比如决赛输了别扣太多)，
        # 但如果是战犯逻辑，我们下面会找补回来。这里先保持基础逻辑。
        stage_adjusted = raw_score * max(1.0, stage_weight)
        
        # 排名修正：打强队输了(rank_weight大) 扣分应该少；打弱队输了 扣分多
        # 公式: raw * (1.5 - rank_weight) -> rank越大，系数越小，扣分越少
        final_base = stage_adjusted + raw_score * (1.5 - rank_weight)
        
        if round_differential > 0:
            # 赢了：躺赢 (Passenger) -> 减轻惩罚
            final_score = final_base * PASSENGER_PROTECTION
        else:
            # 输了：战犯 (Anchor/Loser) -> 加重惩罚
            # 因为 final_base 是负数，乘以大于1的系数会让它更负
            final_score = final_base * LOSER_PENALTY_MULTIPLIER

    return final_score

# ==============================================================================
# 4. 赛事权重计算
# ==============================================================================

def calculate_event_weight(event_id, event_name, df_data, date_map):
    chinese_name = EVENT_ID_TO_SHEET3_NAME.get(event_id)
    if not chinese_name: return 0.5
    
    date_str = date_map.get(chinese_name)
    if not date_str: return 0.5
    
    team_points_map = load_team_points_for_date(date_str)
    if not team_points_map: return 0.5
    
    SPLIT_KEYWORDS = ["bounty"]
    is_split = any(kw in event_name.lower() for kw in SPLIT_KEYWORDS)
    
    if is_split:
        valid_stages = ["Semi-final", "Quarter-final", "Grand final", "3rd place"]
        df_filtered = df_data[df_data['match_stage'].isin(valid_stages)]
        unique_teams = pd.concat([df_filtered['team'], df_filtered['opponent']]).unique() if not df_filtered.empty else []
    else:
        unique_teams = pd.concat([df_data['team'], df_data['opponent']]).unique()
        
    total_points = 0.0
    for team in unique_teams:
        pts = team_points_map.get(team, team_points_map.get(team.lower(), 0.0))
        total_points += pts
        
    event_score = total_points / STANDARD_TIER1_POINT_SUM
    return max(0.1, event_score)

# ==============================================================================
# 5. 爬虫模块 (Step 1)
# ==============================================================================

def run_step1_scrape_data():
    print("===========================================================")
    print("  Step 1: 启动爬虫 (Scraping Data)")
    print("===========================================================")
    
    driver = None
    for i, url in enumerate(EVENT_URLS):
        event_id = get_event_id_from_url(url)
        if not event_id: continue
        
        current_event_name = url.split('/')[-1]
        target_directory = os.path.join(BASE_DIRECTORY, event_id)
        raw_data_file_path = os.path.join(target_directory, f"raw_event_{event_id}_data.xlsx")
        
        if os.path.exists(raw_data_file_path):
            print(f"检测到已存在数据: {current_event_name}，跳过。")
            continue

        print(f"\n--- 开始抓取: {current_event_name} ---")
        all_player_raw_stats = []
        team_rank_map = {}
        
        try:
            if driver is None: driver = uc.Chrome()
            driver.get(url)
            try: WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "event-world-rank")))
            except: pass
            
            content = driver.page_source
            team_name_raw = re.findall('<div class="text">(.*?)<', content)
            team_rank_raw = re.findall('<div class="event-world-rank" title=".*?">#(.*?)<', content)
            team_rank_clean = [r for r in team_rank_raw if r.isdigit()]
            for idx in range(min(len(team_name_raw), len(team_rank_clean))):
                team_rank_map[team_name_raw[idx]] = int(team_rank_clean[idx])
            
            try: current_filter = EVENT_FILTERS[i]
            except: current_filter = f"&event={event_id}"
            
            filter_param = current_filter.lstrip('&')
            driver.get(f"https://www.hltv.org/results?{filter_param}")
            try: WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "a-reset")))
            except: pass
            
            content = driver.page_source
            Game_link = re.findall('<a href="(/matches/.*?)" class="a-reset">', content)
            Game_link = list(dict.fromkeys(Game_link)) 
            print(f"找到 {len(Game_link)} 场比赛。")
            
            for j, link in enumerate(Game_link):
                match_url = 'https://www.hltv.org' + link
                print(f"  处理比赛 {j + 1}/{len(Game_link)} ...")
                driver.get(match_url)
                try: WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "statsPlayerName")))
                except: continue
                
                content = driver.page_source
                stage_match_raw = re.findall('preformatted-text">(.*?)</', content, re.DOTALL)
                match_stage = "Groups"
                if stage_match_raw:
                    s_txt = stage_match_raw[0].lower()
                    if "grand final" in s_txt: match_stage = "Grand final"
                    elif "semi-final" in s_txt: match_stage = "Semi-final"
                    elif "quarter-final" in s_txt: match_stage = "Quarter-final"
                    elif "3rd place" in s_txt: match_stage = "3rd place"
                    elif "online" in s_txt: match_stage = "Online"
                
                game_score = re.findall('<div class="results-team-score">(.*?)<', content)
                game_team_name = re.findall('<div class="results-teamname text-ellipsis">(.*?)<', content)
                game_player_name = re.findall('<div class="smartphone-only statsPlayerName text-ellipsis">(.*?)<', content)
                game_total_rating = re.findall('<td class="rating text-center rating(.*?)<', content)
                
                clean_ratings = [gr.split(">", 1)[-1].strip() for gr in game_total_rating]
                if len(game_team_name) < 2 or len(game_score) < 2: continue
                
                team1_name = game_team_name[0].strip()
                team2_name = game_team_name[1].strip()
                t1_rank = team_rank_map.get(team1_name, 30)
                t2_rank = team_rank_map.get(team2_name, 30)
                
                num_maps = len(game_score) // 2
                current_offset = 30
                if len(clean_ratings) > num_maps * 10 + 30: current_offset = 30 # Simple check
                
                for map_index in range(num_maps):
                    try:
                        r1 = int(game_score[map_index * 2].strip())
                        r2 = int(game_score[map_index * 2 + 1].strip())
                        total_r = r1 + r2
                        diff = r1 - r2
                        if total_r == 0: continue
                        
                        t1_idx_start = 30 + (map_index * 30)
                        t2_idx_start = t1_idx_start + 15
                        if t2_idx_start + 5 > len(clean_ratings): break
                        
                        t1_ratings = [float(clean_ratings[k]) for k in range(t1_idx_start, t1_idx_start+5)]
                        t2_ratings = [float(clean_ratings[k]) for k in range(t2_idx_start, t2_idx_start+5)]
                        t1_avg = sum(t1_ratings)/5
                        t2_avg = sum(t2_ratings)/5
                        baseline = (sum(t1_ratings) + sum(t2_ratings)) / 10.0
                        
                        for k in range(5):
                            all_player_raw_stats.append({
                                "player": game_player_name[t1_idx_start+k].strip(),
                                "team": team1_name, "opponent": team2_name,
                                "opponent_rank": t2_rank, "match_stage": match_stage,
                                "round_differential": diff, "rating": t1_ratings[k],
                                "team_avg_rating": t1_avg, "total_rounds": total_r,
                                "match_baseline_rating": baseline
                            })
                            
                        for k in range(5):
                            all_player_raw_stats.append({
                                "player": game_player_name[t2_idx_start+k].strip(),
                                "team": team2_name, "opponent": team1_name,
                                "opponent_rank": t1_rank, "match_stage": match_stage,
                                "round_differential": -diff, "rating": t2_ratings[k],
                                "team_avg_rating": t2_avg, "total_rounds": total_r,
                                "match_baseline_rating": baseline
                            })
                    except: continue

            if all_player_raw_stats:
                os.makedirs(target_directory, exist_ok=True)
                pd.DataFrame(all_player_raw_stats).to_excel(raw_data_file_path, index=False)
                print(f"数据保存成功: {raw_data_file_path}")

        except Exception as e: print(f"抓取错误 {current_event_name}: {e}")
    if driver: driver.quit()

# ==============================================================================
# 6. 计算模块 (Step 2 & 3)
# ==============================================================================

def run_step2_and_3_calculate():
    print("\n===========================================================")
    print("  Step 2 & 3: 计算 EVP (奖惩机制版)")
    print("===========================================================")
    print(f"规则: 胜者奖励 x{WINNER_BONUS_MULTIPLIER}, 败者惩罚 x{LOSER_PENALTY_MULTIPLIER}, 躺赢保护 x{PASSENGER_PROTECTION}")

    event_date_map = load_event_date_map()
    all_summary_data = []
    event_scores_record = {}
    SCALE_FACTOR = 20.0 

    for url in EVENT_URLS:
        event_id = get_event_id_from_url(url)
        if not event_id: continue
        
        event_name = url.split('/')[-1]
        raw_path = os.path.join(BASE_DIRECTORY, event_id, f"raw_event_{event_id}_data.xlsx")
        
        if not os.path.exists(raw_path): continue
            
        print(f"正在处理: {event_name} ...")
        df = pd.read_excel(raw_path)
        if 'round_differential' not in df.columns: df['round_differential'] = 0

        # Step 2: 赛事权重
        event_weight = calculate_event_weight(event_id, event_name, df, event_date_map)
        event_scores_record[event_name] = event_weight
        
        # Step 3: 选手得分 (V3 逻辑)
        player_buckets = {}

        for _, row in df.iterrows():
            player = row['player']
            stage_str = row['match_stage']
            stage_type = classify_stage(stage_str)
            
            s_weight = STAGE_WEIGHTS.get(stage_str, 1.0)
            r_weight = get_rank_weight(row['opponent_rank'])
            
            # 核心算分
            map_score_unit = calculate_map_score_v3(
                player_rating=row['rating'],
                stage_weight=s_weight,
                rank_weight=r_weight,
                team_avg_rating=row['team_avg_rating'],
                match_baseline_rating=row['match_baseline_rating'],
                round_differential=row['round_differential']
            )
            
            weighted_map_score = map_score_unit * row['total_rounds']
            
            if player not in player_buckets:
                player_buckets[player] = {"Groups": 0.0, "Bracket": 0.0, "Final": 0.0}
            player_buckets[player][stage_type] += weighted_map_score

        # 汇总
        event_results = []
        for player, buckets in player_buckets.items():
            raw_groups = buckets["Groups"] / SCALE_FACTOR
            raw_bracket = buckets["Bracket"] / SCALE_FACTOR
            raw_final = buckets["Final"] / SCALE_FACTOR
            
            capped_groups = apply_group_soft_cap(raw_groups)
            total_raw = capped_groups + raw_bracket + raw_final
            total_weighted = total_raw * event_weight
            
            event_results.append({
                "player": player,
                "event_name": event_name,
                "event_weight": event_weight,
                "Weighted_EVP": total_weighted,
                "Score_Groups": capped_groups,
                "Score_Bracket": raw_bracket,
                "Score_Final": raw_final
            })
            
        if event_results:
            all_summary_data.extend(event_results)
            pd.DataFrame(event_results).to_excel(
                os.path.join(BASE_DIRECTORY, event_id, f"evp_penalty_{event_id}.xlsx"), 
                index=False
            )

    # 全局保存
    if all_summary_data:
        full_df = pd.DataFrame(all_summary_data)
        pd.DataFrame.from_dict(event_scores_record, orient='index', columns=['event_score']).to_excel(EVENT_SCORE_FILE)
        
        pivot = pd.pivot_table(full_df, index="player", columns="event_name", values="Weighted_EVP").fillna(0)
        pivot["Grand_Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("Grand_Total", ascending=False)
        
        pivot.to_excel(OUTPUT_SUMMARY_FILE)
        print(f"\n全部完成！汇总文件: {OUTPUT_SUMMARY_FILE}")

# ==============================================================================
# 7. 主程序
# ==============================================================================

if __name__ == "__main__":
    run_step1_scrape_data()
    run_step2_and_3_calculate()