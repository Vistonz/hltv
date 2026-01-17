import re
import os
import time
from openpyxl import Workbook, load_workbook
import undetected_chromedriver as uc

# === 初始数据配置 ===
webfront = "https://www.hltv.org/stats/players?startDate=all&minMapCount=0"
teamfront = "https://www.hltv.org/stats/teams?startDate=all&minMapCount=0"

# eventfilter 保持不变，这是核心数据源
eventfilter = [
    "&event=7903&event=7909",  "&event=8034", "&event=8043",
    "&event=8292", "&event=7904", "&event=8044", "&event=8036",
    "&event=7905", "&event=8045", "&event=8037",
    "&event=7902","&event=8063","&event=8038","&event=7906&event=7910",
    "&event=8039","&event=7907&event=7912","&event=8064","&event=8040",
    "&event=8027","&event=8067","&event=8046","&event=8041","&event=7908","&event=8042"
]
eventnamefilter = [
    "BLAST赏金赛S1",  "IEM卡托维兹", "PGL克鲁日纳波卡",
     "EPL S21", "BLAST里斯本公开赛", "PGL布加勒斯特", "IEM墨尔本",
    "BLAST对抗赛S1", "PGL阿斯塔纳", "IEM达拉斯",
    "BLAST奥斯汀Major","裂变天地S1","IEM科隆","BLAST赏金赛S2",
    "电竞世界杯","BLAST伦敦公开赛","裂变天地S2","EPL S22",
    "CAC2025","Thunderpick世界锦标赛","PGL布加勒斯特大师赛","IEM成都","BLAST对抗赛S2","SL布达佩斯Major"
]

file_path = os.path.join("C:\\Users\\10725\\Desktop\\hltv\\hltv top", "grade.xlsx")
keyword = ">"
sleep_first = 25.6657
sleep_others = 0.6657

# === 初始化 ===
driver = uc.Chrome()

existing_events = set() 

if os.path.exists(file_path):
    print(f"发现现有文件：{file_path}，正在读取已存在的赛事...")
    try:
        wb = load_workbook(file_path)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[1]: 
                existing_events.add(row[1])
        print(f"已跳过的赛事列表: {list(existing_events)}")
    except Exception as e:
        print(f"读取文件出错，将重新创建: {e}")
        wb = Workbook()
        ws = wb.active
        ws.title = "Player Stats"
        ws.append([
            "Player", "Event_ID", "Country","CountryURL","Team", "Grade", "Rating", "Team_Rank",
            "Rating_Diff(%)", "KPR", "ADR", "DPR", "RS", "KAST", "eaKPR", "eaADR", "eaDPR", "eaMK", "eaKAST",
        ])
else:
    print("未发现现有文件，创建新文件...")
    wb = Workbook()
    ws = wb.active
    ws.title = "Player Stats"
    ws.append([
        "Player", "Event_ID", "Country","CountryURL","Team", "Grade", "Rating", "Team_Rank",
        "Rating_Diff(%)", "KPR", "ADR", "DPR", "RS", "KAST", "eaKPR", "eaADR", "eaDPR", "eaMK", "eaKAST",
    ])

player_stats = {}
zz = 0
j = 0

for i in eventfilter:
    current_event_name = eventnamefilter[j] 
    
    # === 检查跳过逻辑 ===
    if current_event_name in existing_events:
        print(f"赛事 '{current_event_name}' 已存在于表格中，跳过...")
        j += 1 
        continue
    # ====================

    print(f"开始抓取赛事: {current_event_name}...")
    event_id = current_event_name 
    j += 1
    
    # 1. 抓取 Player Stats (保持不变)
    driver.get(webfront + i)
    time.sleep(sleep_first if zz == 0 else sleep_others)
    zz = 1
    content = driver.page_source

    Name1 = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>', content)
    Mapcount1 = re.findall('<td class="statsDetail">(.*?)</td>', content)
    Team = re.findall('class="teamCol" data-sort="(.*?)"><', content)
    Rating = re.findall('class="ratingCol(.*?)</td>', content)
    Id = re.findall('<a href="/stats/players(.*?)" data-tooltip-id="uniqueTooltipId', content)
    Rounds = re.findall('<td class="statsDetail gtSmartphone-only">(.*?)</td>', content)
    Flag = re.findall('class="flag" title="(.*?)">', content)
    FlagURL = re.findall('" src="(.*?)" class="flag"',content)

    # 2. 抓取 Team Rating (保持不变)
    team_rating_per_event = {}
    driver.get(teamfront + i)
    time.sleep(sleep_others)
    content = driver.page_source
    Team1 = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>', content)
    Rating1 = re.findall('class="ratingCol(.*?)</td>', content)
    team_rating = {}
    for idx in range(len(Team1)):
        team_name = Team1[idx].split(keyword, 1)[-1].strip()
        team_rating_value = Rating1[idx].split(keyword, 1)[-1].strip()
        try:
            team_rating[team_name] = float(team_rating_value)
        except:
            team_rating[team_name] = None
    team_rating_per_event[event_id] = team_rating

    # 清洗玩家数据 (保持不变)
    Name = []
    Mapcount = []
    tempzz = 0
    while tempzz * 2 < len(Mapcount1):
        Mapcount.append(Mapcount1[tempzz * 2])
        if len(Mapcount1) == len(Name1):
            Name.append(Name1[tempzz * 2].split(keyword, 1)[-1].strip())
        else:
            Name.append(Name1[tempzz].split(keyword, 1)[-1].strip())
        Team[tempzz] = Team[tempzz]
        Rating[tempzz] = Rating[tempzz].split(keyword, 1)[-1].strip()
        tempzz += 1

    # ==========================================
    # 3. 队伍排名 Grade (逻辑修改部分)
    # ==========================================
    #
    
    team_grade_dict = {}
    
    # 从 "&event=7909&event=7903" 中提取所有数字ID ['7909', '7903']
    extracted_event_ids = re.findall(r'event=(\d+)', i)
    
    print(f"正在抓取排名，检测到子赛事ID: {extracted_event_ids}")
    
    # 循环抓取所有关联ID的排名
    # 后面的ID（通常是决赛）数据会覆盖前面的ID（小组赛），确保冠军排名正确
    for eid in extracted_event_ids:
        # 构建 URL，使用 "/1" 作为通配 slug
        rank_url = f"https://www.hltv.org/events/{eid}/1"
        
        driver.get(rank_url)
        time.sleep(sleep_others) # 稍微等待加载
        content = driver.page_source
        
        # 使用原有的正则逻辑抓取当前页面的排名
        Team2 = re.findall('"><a href="/team/(.*?)</a></div>', content)
        Grade = re.findall('</a></div>\n                      <div>(.*?)</div>', content)
        
        for idx in range(len(Grade)):
            # 简单的越界保护
            if idx < len(Team2):
                team_name = Team2[idx].split(keyword, 1)[-1].strip()
                grade_value = Grade[idx].split(keyword, 1)[-1].strip()
                # 存入字典，如果队伍已存在（即之前在小组赛被抓取过），这里会更新为最新的（决赛）排名
                team_grade_dict[team_name] = grade_value

    # ==========================================
    # (逻辑修改结束)
    # ==========================================

    # 4. 构建选手数据 (保持不变)
    team_to_players = {}
    for idx, name in enumerate(Name):
        player_id = Id[idx].split("/")[1] if idx < len(Id) else "unknown"
        team = Team[idx] if idx < len(Team) else "unknown"
        rating = Rating[idx] if idx < len(Rating) else "0"
        maps = Mapcount[idx] if idx < len(Mapcount) else "unknown"
        rounds = Rounds[idx] if idx < len(Rounds) else "unknown"
        flag = Flag[idx] if idx < len(Flag) else "unknown"
        flagURL = FlagURL[idx] if idx < len(FlagURL) else "unknown"

        try:
            rating_float = float(rating)
        except:
            rating_float = 0.0

        # 抓取选手详细页面数据
        statsuffix = Id[idx].replace('amp;', '')
        driver.get("https://www.hltv.org/stats/players" + statsuffix)
        time.sleep(sleep_others)
        content = driver.page_source
        
        Playerstatform=re.findall('<div class="player-summary-stat-box-data traditionalData">(.*?)</div>',content)
        try:
            dpr = Playerstatform[0]
            kast1=re.findall('<div class="player-summary-stat-box-data traditionalData">(.*?)<span',content)
            kast = kast1[0]
            rs1 = re.findall('<div class="player-summary-stat-box-data">(.*?)<span class="',content)
            rs = rs1[0]
            adr = Playerstatform[3]
            kpr = Playerstatform[4]
            Playerstatform_eco=re.findall('<div class="player-summary-stat-box-data ecoAdjustedData hidden">(.*?)</div>',content)
            eadpr = Playerstatform_eco[0]
            eakast1=re.findall('<div class="player-summary-stat-box-data ecoAdjustedData hidden">(.*?)<span',content)
            eakast = eakast1[0]
            eamk = Playerstatform_eco[2]
            eaadr = Playerstatform_eco[3]
            eakpr = Playerstatform_eco[4]
        except IndexError:
            dpr = kast = rs = adr = kpr = eadpr = eakast = eamk = eaadr = eakpr = "0"

        if team not in team_to_players:
            team_to_players[team] = []
        team_to_players[team].append((name, rating_float))

        if name not in player_stats:
            player_stats[name] = {}
        
        # 在这里应用刚刚抓取的 grade 字典
        player_stats[name][event_id] = {
            "player_id": player_id,
            "flag": flag,
            "flagURL": flagURL,
            "team": team,
            "rating": rating,
            "rating_float": rating_float,
            "maps": maps,
            "rounds": rounds,
            "team_rating": team_rating_per_event[event_id].get(team, None),
            "rank_in_team": None,
            "rating_diff_pct": None,
            "grade": team_grade_dict.get(team, "N/A"), # 这里使用动态抓取的排名
            "dpr": dpr,
            "kast": kast,
            "rs": rs,
            "adr": adr,
            "kpr": kpr,
            "eadpr":eadpr,
            "eakast":eakast,
            "eamk":eamk,
            "eaadr":eaadr,
            "eakpr":eakpr,
        }

    # 计算队内排名和rating差 (保持不变)
    for team_name, players in team_to_players.items():
        sorted_players = sorted(players, key=lambda x: x[1], reverse=True)
        for rank, (name, _) in enumerate(sorted_players, 1):
            if event_id in player_stats[name]:
                player_stats[name][event_id]["rank_in_team"] = rank
                team_rating_val = player_stats[name][event_id]["team_rating"]
                if team_rating_val:
                    diff_pct = (player_stats[name][event_id]["rating_float"] - team_rating_val) / team_rating_val
                    player_stats[name][event_id]["rating_diff_pct"] = round(diff_pct, 2)

    # === 写入当前赛事的数据到Excel (保持不变) ===
    for player_name in Name:
        if player_name in player_stats and event_id in player_stats[player_name]:
            stats = player_stats[player_name][event_id]
            ws.append([
                player_name,
                event_id,
                stats.get("flag", ""),
                stats.get("flagURL", ""),
                stats.get("team", ""),
                stats.get("grade", ""),
                float(stats.get("rating", 0)),
                stats.get("rank_in_team", ""),
                stats.get("rating_diff_pct", ""),
                float(stats.get("kpr", 0)),
                float(stats.get("adr", 0)),
                float(stats.get("dpr", 0)),
                stats.get("rs", ""),
                stats.get("kast", ""),
                float(stats.get("eakpr", 0)),
                float(stats.get("eaadr", 0)),
                float(stats.get("eadpr", 0)),
                float(stats.get("eamk", 0)),
                stats.get("eakast", ""),
            ])

    # === 保存文件 ===
    wb.save(file_path)
    print(f"赛事 {event_id} 数据抓取并保存完成。")

driver.quit()
print("所有赛事数据抓取完成，Excel 文件已保存至：", file_path)