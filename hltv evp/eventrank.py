import os
import re
import json
import pandas as pd

# ----------------------------------------------------------------------
# 1. 全局配置区
# ----------------------------------------------------------------------
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

base_directory = "C:\\Users\\10725\\Desktop\\hltv\\database\\event"
rank_db_directory = "C:\\Users\\10725\\Desktop\\hltv\\database\\rank"
event_score_file_path = os.path.join(base_directory, "event_scores_lookup.xlsx")

PLAYOFF_STAGES = ["Grand final", "Semi-final", "Quarter-final", "3rd place"]
SPLIT_EVENT_KEYWORDS = ["bounty", "Final"]

# ----------------------------------------------------------------------
# 2. 辅助函数
# ----------------------------------------------------------------------
def get_event_id_from_url(url):
    match = re.search(r"[-+]?\d+\.?\d*|\.\d+", url)
    if match:
        return match.group(0)
    return None

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
        return {}, 0.0

    df.columns = [c.strip() for c in df.columns]
    if 'Team Name' not in df.columns or 'Points' not in df.columns:
        return {}, 0.0
    
    df['Points'] = pd.to_numeric(df['Points'], errors='coerce')
    df = df.dropna(subset=['Points'])
    
    # [核心修改] 计算当日所有战队得分总和
    total_global_points = df['Points'].sum()
    
    points_map = {}
    for _, row in df.iterrows():
        team = str(row['Team Name']).strip()
        pts = float(row['Points'])
        points_map[team] = pts
        points_map[team.lower()] = pts
        
    return points_map, total_global_points

# ----------------------------------------------------------------------
# 3. 核心计算逻辑
# ----------------------------------------------------------------------
def calculate_all_event_weights():
    print("===========================================================")
    print(" 开始计算赛事权重 (赛事队伍总分 / 当期世界总得分)")
    print("===========================================================")
    
    all_event_scores = {}
    
    for url in event_urls:
        event_id = get_event_id_from_url(url)
        current_event_name = url.split('/')[-1]
        if not event_id: continue
            
        print(f"\n--- 正在计算: {current_event_name} ---")
        
        target_directory = os.path.join(base_directory, event_id)
        raw_data_path = os.path.join(target_directory, f"raw_event_{event_id}_data.xlsx")
        meta_file_path = os.path.join(target_directory, f"event_{event_id}_meta.json")
        
        if not os.path.exists(raw_data_path):
            print(f"跳过: 找不到该赛事的原始比赛数据 ({raw_data_path})")
            continue
            
        # 1. 尝试获取日期
        event_date = None
        if os.path.exists(meta_file_path):
            try:
                with open(meta_file_path, 'r') as f:
                    event_date = json.load(f).get("start_date")
            except: pass
            
        # 2. 匹配最近的排名文件
        team_points_map = {}
        total_global_points = 0.0
        
        if event_date:
            try:
                target_dt = pd.to_datetime(event_date)
                rank_files = []
                for fname in os.listdir(rank_db_directory):
                    if fname.endswith(".xlsx") or fname.endswith(".csv"):
                        try:
                            date_part = fname.replace(".xlsx", "").replace(".csv", "")
                            file_dt = pd.to_datetime(date_part)
                            rank_files.append((file_dt, fname))
                        except: continue
                
                rank_files.sort(key=lambda x: x[0])
                valid_files = [x for x in rank_files if x[0] <= target_dt]
                if valid_files:
                    best_match = valid_files[-1]
                    closest_file_date_str = best_match[0].strftime('%Y-%m-%d')
                    team_points_map, total_global_points = load_team_points_for_date(closest_file_date_str)
            except Exception as e:
                print(f" 匹配排名文件失败: {e}")
                
        if total_global_points <= 0:
            print(" 警告: 未能获取到有效的世界总积分，跳过该赛事计算。")
            continue
            
        # 3. 提取赛事的参赛队伍
        df = pd.read_excel(raw_data_path)
        is_split_event = any(kw in current_event_name for kw in SPLIT_EVENT_KEYWORDS)
        
        unique_teams = pd.concat([df['team'], df['opponent']]).unique()
            
        # 4. 计算参赛队伍总分及权重
        event_total_points = 0.0
        for team in unique_teams:
            pts = team_points_map.get(team)
            if pts is None: pts = team_points_map.get(team.lower(), 0.0)
            if pts > 0: event_total_points += pts
                
        # [修改核心] 使用新公式：赛事参赛队伍总分 / 榜单所有队伍总分
        current_event_score = event_total_points / total_global_points
        all_event_scores[current_event_name] = current_event_score
        
        print(f" -> 当期世界战队总分: {total_global_points}")
        print(f" -> 参赛队伍得分总和: {event_total_points}")
        print(f" -> 最终含金量系数: {current_event_score:.6f}")

    # 5. 排序并保存
    if all_event_scores:
        df_to_save = pd.DataFrame.from_dict(all_event_scores, orient='index', columns=['event_score'])
        df_to_save.index.name = 'event_name'
        
        event_name_order = [url.split('/')[-1] for url in event_urls]
        all_known = df_to_save.index.tolist()
        final_order = [name for name in event_name_order if name in all_known] + [name for name in all_known if name not in event_name_order]
        df_to_save = df_to_save.reindex(final_order)

        df_to_save.to_excel(event_score_file_path)
        print(f"\n成功保存所有赛事含金量至: {event_score_file_path}")

if __name__ == "__main__":
    calculate_all_event_weights()