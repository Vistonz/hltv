import pandas as pd
import json
import os
from collections import Counter, defaultdict

# ================= 配置区域 =================

INPUT_FILE = "hltv_predictions_2025.jsonl"
OUTPUT_FILE = "HLTV_Prediction_Filtered_Analysis.xlsx"

# 过滤阈值：提及率低于此值的选手将被忽略 (0.10 代表 10%)
THRESHOLD_RATIO = 0.10 

# ===========================================

def main():
    print(f"正在读取数据: {INPUT_FILE} ...")
    
    if not os.path.exists(INPUT_FILE):
        print(f"错误: 找不到文件 {INPUT_FILE}")
        return

    # --- 容器初始化 ---
    rank_counters = {i: Counter() for i in range(1, 21)}
    player_ranks_collection = defaultdict(list)
    total_valid_users = 0

    # --- 数据读取与聚合 ---
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                line = line.strip()
                if not line: continue
                entry = json.loads(line)
                predictions = entry.get('predictions', [])
                
                if not predictions: continue
                total_valid_users += 1
                
                for pred in predictions:
                    rank = pred.get('rank')
                    player_nick = pred.get('player_nick')
                    
                    if rank and player_nick and 1 <= rank <= 20:
                        rank_counters[rank][player_nick] += 1
                        player_ranks_collection[player_nick].append(rank)
                        
            except json.JSONDecodeError:
                continue

    if total_valid_users == 0:
        print("未找到有效数据，请检查 jsonl 文件。")
        return

    print(f"数据聚合完毕 (样本数: {total_valid_users})，正在计算并过滤...")

    # --- 开始写入 Excel ---
    try:
        with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
            
            # ==========================================
            # Sheet 1: 平均排名总榜 (带过滤)
            # ==========================================
            summary_data = []
            filtered_count = 0 # 统计一下过滤了多少人

            for player, ranks in player_ranks_collection.items():
                count = len(ranks)
                mention_rate = count / total_valid_users
                
                # --- [核心修改] 过滤逻辑 ---
                if mention_rate < THRESHOLD_RATIO:
                    filtered_count += 1
                    continue
                # -------------------------

                avg_rank = sum(ranks) / count
                best_rank = min(ranks)
                worst_rank = max(ranks)
                
                summary_data.append({
                    "选手": player,
                    "平均预测排名": round(avg_rank, 2),
                    "被预测次数": count,
                    "最高预测": best_rank,
                    "最低预测": worst_rank,
                    "全场提及率": f"{mention_rate:.2%}" 
                })
            
            df_summary = pd.DataFrame(summary_data)
            if not df_summary.empty:
                df_summary = df_summary.sort_values(by=["平均预测排名", "被预测次数"], ascending=[True, False])
            
            df_summary.to_excel(writer, sheet_name="总榜_平均排名(Filtered)", index=False)
            print(f"  - 总榜生成完毕: 保留 {len(df_summary)} 人 (已剔除 {filtered_count} 名提及率 < {THRESHOLD_RATIO:.0%} 的选手)")

            # ==========================================
            # Sheet 2-21: 各排名详细得票
            # ==========================================
            for i in range(1, 21):
                sheet_name = f"Rank_{i:02d}"
                counter = rank_counters[i]
                
                if not counter:
                    df = pd.DataFrame(columns=["选手", "得票数", "该排名占比"])
                else:
                    data = counter.most_common()
                    df = pd.DataFrame(data, columns=["选手", "得票数"])
                    total_votes = df["得票数"].sum()
                    df["该排名占比"] = (df["得票数"] / total_votes).apply(lambda x: f"{x:.2%}")
                
                # 注意：分排名的榜单通常不需要过滤，因为那里列出的是“谁得了第几名”，
                # 即使是冷门选手，如果在某个位置得了一票，通常也值得展示。
                # 如果你想连分榜单也过滤，可以在这里加类似的逻辑。
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        print("\n" + "="*30)
        print(f"分析报告已生成: {OUTPUT_FILE}")
        print(f"过滤标准: 提及率 >= {THRESHOLD_RATIO:.0%}")
        print("="*30)

    except Exception as e:
        print(f"Excel 保存失败: {e}")

if __name__ == "__main__":
    main()