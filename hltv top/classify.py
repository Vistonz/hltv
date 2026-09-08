import pandas as pd
import numpy as np
import os

def process_sorted_player_rankings_final(input_file_path, output_folder):
    print("--- 开始处理 ---")
    
    # 1. 读取数据
    if not os.path.exists(input_file_path):
        print(f"❌ 错误：找不到输入文件！\n请检查路径是否正确: {input_file_path}")
        return

    try:
        df = pd.read_excel(input_file_path)
        df.columns = df.columns.str.strip().str.lower()
        print(f"✅ 成功读取文件，共 {len(df)} 行数据")
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return

    # ==========================================
    # 定义列名
    # ==========================================
    impact_cols_keys = [
        'rs',  '回合首杀数', 
         '3+kill', 'rounds with a multikill', 'rounds with a kill',
        'clutch win', 'clutch point per round', 'kill per round win', 'adr win' ,
        'adr','kpr'
    ]
    
    advanced_cols_keys = [
        'big event rating', 
        'elite event rating', 
        'supereliteevent rating', 'super elite event rating',
        'big event playoff rating', 
        'elite event playoff rating', 
        'superelite event playoff rating', 'super elite event playoff rating',
        'arena rating'
    ]
    
    # 占比转换列
    cols_needing_division = ['0.85+', '1.00+', '1.15+', '1.30+']
    
    # 格式化百分比列 (移除 kast 以免被乘100)
    cols_already_ratio = [
        'dpr', 'dpr_eco', 
        '3+kill', 'rounds with a multikill', 'rounds with a kill',
        'hs%', 
        'support_round_percent', 'winrate_1v1', 
        'assist kill percentage', 'save per round lose',
        'traded_death_percentage', 'traded_death_percentage.1', # 这里包含了补枪和被补
        '首杀尝试', '首杀成功', 'win after first kill',
        'snipkill_percent', 'snipkillround_percent'
    ]
    
    percent_cols = cols_needing_division + cols_already_ratio

    # ==========================================
    # 强制转换数据类型
    # ==========================================
    all_target_cols = impact_cols_keys + advanced_cols_keys + percent_cols + ['kast', 'kast_eco']
    
    print("🔧 正在强制转换数据类型...")
    for col in all_target_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # ==========================================
    # 逻辑处理: DPR反转, 占比计算, 移除列
    # ==========================================
    if 'dpr' in df.columns:
        df['dpr'] = 1 - df['dpr']
    if 'dpr_eco' in df.columns:
        df['dpr_eco'] = 1 - df['dpr_eco']

    map_count_col = '图池数'
    if map_count_col not in df.columns:
        for c in df.columns:
            if '图池' in c or 'maps' == c:
                map_count_col = c
                break
    
    if map_count_col in df.columns:
        df[map_count_col] = pd.to_numeric(df[map_count_col], errors='coerce')
        for col in cols_needing_division:
            if col in df.columns:
                df[col] = df[col] / df[map_count_col]
    
    cols_to_drop = []
    if 'arena round' in df.columns:
        cols_to_drop.append('arena round')

    for col in df.columns:
        if ('map' in col or '图池' in col) and ('rating' not in col):
            cols_to_drop.append(col)
            
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    # ==========================================
    # 4. 定义映射
    # ==========================================
    translation_map = {
        'rating': 'Rating', 'rounds': '总回合数', 'adr': 'ADR', 'kpr': 'KPR',
        'dpr': 'Surviving', 
        'kast': 'KAST%', 'kd diff': 'KD差', 'hs%': '爆头率',
        'ctrating': 'CT Rating', 'trating': 'T Rating', '手枪局rating': '手枪局 Rating',
        'firepower': '火力 ', 'trading': '补枪 ', 'sniping': '狙击 ',
        'utility': '道具', 'flash_assist': '闪光助攻', 'utility_damage': '道具伤害',
        'support_round_percent': '贡献回合占比', 'winrate_1v1': '1v1 胜率',
        'rating vs top5': '对阵Top5 Rating', 'rating vs top10': '对阵Top10 Rating',
        'rating vs top20': '对阵Top20 Rating', 'assist kill percentage': '助攻击杀占比',
        'damage per kill': '每击杀造成伤害', 'save per round lose': '失败回合存活率',
        'traded_death_percentage': '被补死亡占比', 'traded_death_percentage.1': '补枪击杀占比',
        'rs': 'RS', 
        '首杀rating': '首杀Rating', '首杀尝试': '首杀尝试率', '首杀成功': '首杀成功率',
        '回合首杀数': '局均首杀数', 'opening': '破局 ', 'entrying': '突破 ',
        '3+kill': '3杀+回合占比', 'rounds with a multikill': '多杀回合占比',
        'rounds with a kill': '击杀回合占比', 'clutch win': '残局胜利总数',
        'clutch point per round': '回合残局点数', 'clutching': '残局',
        'win after first kill': '首杀后胜率',
        'big event rating': '大型赛事 Rating', 
        'elite event rating': '精英赛事 Rating',
        'supereliteevent rating': '超级精英赛事 Rating', 
        'super elite event rating': '超级精英赛事 Rating',
        'big event playoff rating': '大型赛事淘汰赛 Rating',
        'elite event playoff rating': '精英赛事淘汰赛 Rating',
        'superelite event playoff rating': '超级精英赛事淘汰赛 Rating',
        'super elite event playoff rating': '超级精英赛事淘汰赛 Rating',
        'arena rating': '主场馆赛事 Rating', 'elimination rating': '回家局 Rating',
        'kill per round win': '获胜回合KPR', 'adr win': '获胜回合ADR',
        'kpr lose': '失败回合KPR', 'adr lose': '失败回合ADR',
        'singlemapwinrating': '获胜地图Rating', 'traded_death': '回合被补死亡数',
        'save_teammate': '回合拯救队友次数', 'saved_by_teammate': '回合被队友拯救次数',
        'attack_in_round': '回合主动出击次数', 'livetime_perround': '回合存活时间',
        'snipkill_perround': '回合狙杀数', 'snipkill_percent': '狙杀占比',
        'snipkillround_percent': '狙杀回合占比', 'utlility_kill_round': '每百回合道具击杀',
        'throw_flash_perround': '回合闪光投掷数', 'time_opponent_flashed': '敌人平均吃闪时间',
        '0.85+': 'Rating 0.85+ 占比', '1.00+': 'Rating 1.00+ 占比',
        '1.15+': 'Rating 1.15+ 占比', '1.30+': 'Rating 1.30+ 占比',
        'dpr_eco': '经济调整存活率', 'kast_eco': '经济调整KAST%',
        'multikill_eco': '经济调整多杀Rating', 'adr_eco': '经济调整ADR',
        'kpr_eco': '经济调整KPR', 'avg_weaponvalve_perkill': '平均击杀武器价值'
    }

    # ==========================================
    # 5. 计算排名 (核心修正区域)
    # ==========================================
    all_numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    real_impact_cols = [c for c in impact_cols_keys if c in df.columns]
    real_advanced_cols = [c for c in advanced_cols_keys if c in df.columns]
    
    used_cols = set(real_impact_cols + real_advanced_cols)
    real_other_cols = [c for c in all_numeric_cols if c not in used_cols]

    rank_df = pd.DataFrame(index=df.index)
    
    for col in all_numeric_cols:
        # [逻辑修正]: 
        # 1. 默认越高越好 (is_lower_better = False)
        # 2. 如果包含 'death' 或 'damage per kill'，通常是越低越好 (is_lower_better = True)
        # 3. [特例]: 如果包含 'traded' (被补/补枪)，这代表团队配合，无论是否含death，都是越高越好。
        
        is_lower_better = False 
        
        if 'death' in col or 'damage per kill' in col:
            is_lower_better = True
            
        if 'traded' in col:  # 包含 traded 的列（traded_death, traded_death_percentage等）强制改为越高越好
            is_lower_better = False
            
        rank_df[col] = df[col].rank(ascending=is_lower_better, method='min', na_option='bottom')

    # 6. 生成输出
    output_lines = []
    for idx, row in df.iterrows():
        player_name = row.get('选手id', row.get('选手ID', f'Player_{idx}'))
        output_lines.append(f"### 选手: {player_name}")
        
        def print_sorted_section(title, cols):
            lines = [f"**{title}**"]
            if not cols: return []
            data_list = []
            for col in cols:
                val = row[col]
                rank = rank_df.loc[idx, col]
                zh_name = translation_map.get(col, col)
                
                if pd.isna(val): val_str = "N/A"
                elif col == 'rs': val_str = f"{val:+.2f}%" 
                elif 'kast' in col: val_str = f"{val:.1f}%"
                elif col in percent_cols: val_str = f"{val:.1%}"
                elif isinstance(val, float): val_str = f"{val:.2f}" if abs(val) > 0.01 else f"{val:.4f}"
                else: val_str = str(val)
                
                rank_val = rank if pd.notna(rank) else 999999 
                rank_str = f"(#{int(rank)})" if pd.notna(rank) else "(N/A)"
                data_list.append((rank_val, f"· {zh_name}: {val_str} {rank_str}"))
            
            data_list.sort(key=lambda x: x[0])
            for _, line_str in data_list: lines.append(line_str)
            return lines

        output_lines.extend(print_sorted_section("1. 影响力数据 (Impact Data)", real_impact_cols))
        output_lines.extend(print_sorted_section("2. 重要高阶数据 (Important Advanced Data)", real_advanced_cols))
        output_lines.extend(print_sorted_section("3. 其他值得注意的数据 (Other Notable Data)", real_other_cols))
        output_lines.append("\n" + "-"*30 + "\n")

    # 7. 保存结果
    result_text = "\n".join(output_lines)
    final_output_path = os.path.join(output_folder, 'player_rankings_final_fixed.txt')
    
    try:
        with open(final_output_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
        print(f"✅ 处理完成！\n已修复：被补/补枪数据逻辑改为“越高越好”。\n已修复：Arena Round 已移除，KAST 百分比显示修正。")
        print(f"📁 结果文件已保存至: {final_output_path}")
    except Exception as e:
        print(f"❌ 保存文件失败: {e}")

# ==========================================
# 执行区域
# ==========================================
# 输入输出路径 (Linux, 该仓库仅在 Arch 上运行; 原 Windows 拼接路径已改为绝对路径)
input_excel_path = '/home/hongbin/Desktop/hltv/hltv year/rating2026.xlsx'
output_folder = '/home/hongbin/Desktop/hltv/hltv top'

if __name__ == "__main__":
    process_sorted_player_rankings_final(input_excel_path, output_folder)