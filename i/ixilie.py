"""
HLTV 比赛统计爬虫 (ixilie.py)

功能：
1. 读取 players.json 中的选手 ID 和名称。
2. 使用 undetected_chromedriver 开启浏览器。
3. 爬取每个选手的比赛记录（按 K/D 升序排列）。
4. 过滤出 死亡(D) - 击杀(K) >= 10 的比赛。  
5. 提取比赛链接并添加 hltv.org 前缀。
6. 如果第一页的所有比赛都满足条件，则处理分页（offset=100）。
7. 结果保存为 ixilie_results.json 和 ixilie_results.xlsx。

运行方法：
1. 确保安装依赖：
   pip install undetected-chromedriver selenium pandas openpyxl
2. 在 i/ 目录下运行：
   python ixilie.py

注意：
- 处理 1.9 万名选手需要很长时间，建议先修改 main() 中的循环进行小规模测试（例如 for player in players[:10]:）。
"""

import re
import json
import os
import time
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def extract_matches_from_page(content, player_id, player_name, offset, diff_threshold=10):
    """
    Extract matches from the page source.
    Returns: (filtered_matches, all_on_page_satisfy, total_matches_count)
    """
    # Finding rows is safer.
    rows = re.findall(r'<tr(.*?)</tr>', content, re.DOTALL)
    
    filtered_matches = []
    total_on_page = 0
    all_on_page_satisfy = True
    
    for row in rows:
        # Check if it's a valid match row by looking for K-D
        kd_match = re.search(r'<td class="statsCenterText no-sort" data-sort-method="none">(\d+) - (\d+)</td>', row)
        if not kd_match:
            continue
            
        total_on_page += 1
        k = int(kd_match.group(1))
        d = int(kd_match.group(2))
        diff = d - k
        
        # Extract link
        link_match = re.search(r'<td class="no-sort" data-sort-method="none"><a href="(.*?)">', row)
        match_link = ""
        if link_match:
            # Prefix with hltv.org as requested
            match_link = "hltv.org" + link_match.group(1)
            
        if diff >= diff_threshold:
            filtered_matches.append({
                "Player": player_name,
                "Player ID": player_id,
                "Kills": k,
                "Deaths": d,
                "Difference": diff,
                "Link": match_link,
                "Offset": offset
            })
        else:
            all_on_page_satisfy = False
            
    return filtered_matches, all_on_page_satisfy, total_on_page

def get_matches_for_player(driver, player_id, player_name, diff_threshold=10):
    base_url = f"https://www.hltv.org/stats/players/matches/{player_id}/{player_name}&sortColumn=KillDeath&sortDirection=Ascending"
    offset = 0
    all_filtered_matches = []
    
    while True:
        url = base_url + (f"&offset={offset}" if offset > 0 else "")
        print(f"  Fetching offset {offset}: {url}")
        driver.get(url)
        
        try:
            # Wait for the table to appear
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "stats-table"))
            )
            # Give it a tiny bit extra for the content to render fully if needed
            time.sleep(1)
        except Exception:
            print(f"  Table not found or timed out for {player_name} at offset {offset}")
            break
            
        content = driver.page_source
        page_matches, all_satisfy, count = extract_matches_from_page(content, player_id, player_name, offset, diff_threshold)
        
        if count == 0:
            print("  No matches found on this page.")
            break
            
        all_filtered_matches.extend(page_matches)
        
        print(f"  Found {len(page_matches)}/{count} matches matching criteria (Diff >= 10).")
        
        # Pagination condition: All matches on current page satisfy the condition
        if all_satisfy and count > 0:
            print("  All matches on page satisfy condition. Proceeding to next offset...")
            offset += 100
        else:
            break
            
        time.sleep(1)
        
    return all_filtered_matches

def find_worst_matches_all_players(
    players_file=r"c:\Users\10725\Desktop\hltv\i\players.json",
    json_output=r"c:\Users\10725\Desktop\hltv\i\ixilie_results.json",
    excel_output=r"c:\Users\10725\Desktop\hltv\i\ixilie_results.xlsx",
    diff_threshold=10,
    player_limit=None,
):
    
    if not os.path.exists(players_file):
        print("Error: players.json not found.")
        return
        
    with open(players_file, "r", encoding="utf-8") as f:
        players = json.load(f)
    
    print(f"Loaded {len(players)} players.")
    
    # Initialize uc.Chrome
    options = uc.ChromeOptions()
    # options.add_argument('--headless') # Uncomment for headless mode
    driver = uc.Chrome(options=options)
    
    all_results = []
    
    try:
        # Process all players from players.json
        # To limit the number of players (e.g., for testing), you can use:
        # for player in players[:10]:
        for player in players[:player_limit]:
            pid = player.get("id")
            pname = player.get("name")
            print(f"Processing: {pname} ({pid})")
            
            player_results = get_matches_for_player(driver, pid, pname, diff_threshold)
            if player_results:
                all_results.extend(player_results)
                
                # Intermediate save
                df = pd.DataFrame(all_results)
                df.to_excel(excel_output, index=False)
                with open(json_output, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, indent=4, ensure_ascii=False)
                    
            print(f"Total entries so far: {len(all_results)}")
            
    except KeyboardInterrupt:
        print("Stopped by user. Saving current Progress...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()
        
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_excel(excel_output, index=False)
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=4, ensure_ascii=False)
        print(f"Done! Results saved to {excel_output} and {json_output}")
    else:
        print("No matches found matching the criteria.")

if __name__ == "__main__":
    find_worst_matches_all_players()
