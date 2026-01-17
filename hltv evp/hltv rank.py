import re
import os
import time
import datetime
import undetected_chromedriver as uc
from openpyxl import Workbook

# --- 1. 准备工作 ---
base_save_dir = "database/rank"
if not os.path.exists(base_save_dir):
    os.makedirs(base_save_dir)

# --- 2. URL 生成函数 (增加了特例处理) ---
def get_all_mondays_urls(year):
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

# --- 3. 爬虫主逻辑 ---
driver = uc.Chrome()

try:
    year_to_crawl = 2025
    # 获取的日期列表里，9月的那条已经是 9月2日 了
    target_dates, hltv_urls = get_all_mondays_urls(year_to_crawl)

    for date_obj, url in zip(target_dates, hltv_urls):
        print(f"--------------------------------")
        print(f"正在爬取: {url}")
        
        try:
            driver.get(url)
            time.sleep(0.5) # 建议根据网速调整，HLTV有时候加载慢
            
            content = driver.page_source 
            
            # 正则提取
            teams = re.findall(r'"><span class="name">(.*?)<', content)
            # 优化后的正则，直接提取括号内的数字
            points_raw = re.findall(r'<span class="points">\((.*?)<', content) 
            
            # 简单校验
            if not teams:
                print(f"{url} 未找到数据，可能未发布或加载失败")
                continue

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

        except Exception as e:
            print(f"错误: {e}")

finally:
    driver.quit()
    print("所有任务完成。")