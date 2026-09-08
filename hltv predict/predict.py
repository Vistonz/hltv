import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import random
import json
import html
import os
from bs4 import BeautifulSoup

# ================= 配置区域 =================

# API URL (去除 offset 参数)
LISTING_API_BASE = "https://www.hltv.org/top20/json?top20Id=2025" 
HLTV_DOMAIN = "https://www.hltv.org"

# 文件路径
USER_LIST_FILE = "hltv_user_list.jsonl"       # 存放所有用户的列表 (Phase 1 输出)
FINAL_OUTPUT_FILE = "hltv_predictions_2025.jsonl" # 存放最终预测详情 (Phase 2 输出)

# 运行开关 (True = 开启, False = 关闭)
# 建议先跑 Phase 1，跑完后再跑 Phase 2，或者根据需要同时开启
RUN_PHASE_1 = True  # 补全用户列表
RUN_PHASE_2 = True  # 抓取用户详情

# 极速睡眠配置 (秒)
MIN_SLEEP = 0.2
MAX_SLEEP = 0.5

# ===========================================

def get_driver(chrome_version=None):
    """初始化浏览器 - 极速模式"""
    options = uc.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--start-maximized")

    # 禁用图片，极大提升加载速度
    options.add_argument('--blink-settings=imagesEnabled=false')

    # Eager 模式：DOM 加载完（文字出来）就视为加载成功，不等待后续资源
    options.page_load_strategy = 'eager'

    # chrome_version: Chrome 主版本号 (None = 自动检测; 本机 Chrome 151 需传 151)
    driver = uc.Chrome(options=options, version_main=chrome_version)
    return driver

def random_sleep():
    """极速随机等待"""
    time.sleep(random.uniform(MIN_SLEEP, MAX_SLEEP))

def append_line(filepath, data):
    """追加写入一行 JSON"""
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

def load_dataset_to_set(filepath, key_field):
    """加载指定字段到 Set 中用于去重"""
    existing_set = set()
    if not os.path.exists(filepath):
        return existing_set
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                val = data.get(key_field)
                if val:
                    existing_set.add(val)
            except: pass
    return existing_set

# ================= 阶段一：全量名录补全 =================

def run_phase_1(driver, listing_api_base=LISTING_API_BASE, user_list_file=USER_LIST_FILE, start_offset=25520):
    print("\n>>> [Phase 1] 启动：全量名录补全")
    print(">>> 目标：扫描 API，确保每一个在榜用户都存储在 User List 中")

    # 1. 加载本地已保存的 User ID (用于判断是否需要写入)
    # 注意：我们使用 userId 作为唯一标识，比用户名更靠谱
    stored_ids = load_dataset_to_set(user_list_file, 'userId')
    print(f"    当前名录已有: {len(stored_ids)} 人")

    # start_offset: 起始 offset (原值 25520; 从 0 开始可全量补录)
    current_offset = start_offset

    while True:
        connector = "&" if "?" in listing_api_base else "?"
        api_url = f"{listing_api_base}{connector}offset={current_offset}"
        
        try:
            driver.get(api_url)
            random_sleep() # 0.2-0.5s
            
            # 提取 JSON (兼容 body 或 pre 标签)
            page_text = driver.find_element(By.TAG_NAME, "body").text
            if "<pre>" in driver.page_source:
                page_text = driver.find_element(By.TAG_NAME, "pre").text
            
            try:
                api_data = json.loads(page_text)
            except json.JSONDecodeError:
                # 极速模式下偶尔会因为加载未完成解析失败，稍微多等一下重试
                time.sleep(1) 
                continue

            standing_list = api_data.get("standing", [])
            
            if not standing_list:
                print("    [End] API 列表扫描完毕。")
                break
            
            # === 核心逻辑：查漏补缺 ===
            added_count = 0
            
            for user in standing_list:
                uid = user.get("userId")
                
                # 只要 ID 已存在，就跳过 (去重)
                if uid in stored_ids:
                    continue
                
                # 如果不存在，补录进去
                simple_user = {
                    "userId": uid,
                    "username": user.get("username"),
                    "link": user.get("top20UserLocation"),
                    "rank": user.get("placement"), # 顺便记录当前排名
                    "found_at": time.time()
                }
                
                append_line(user_list_file, simple_user)
                stored_ids.add(uid) # 更新内存，防止本轮重复
                added_count += 1
            
            # 状态打印
            if added_count > 0:
                print(f"    Offset {current_offset}:  补录 +{added_count} 人 (总库: {len(stored_ids)})")
            else:
                # 这一页全是已存在的，只打印简略信息
                print(f"    Offset {current_offset}:  全已存在")

            # 翻页
            current_offset += len(standing_list)
            
        except Exception as e:
            print(f" Phase 1 异常: {e}")
            time.sleep(2) # 出错稍微缓一下

# ================= 阶段二：增量详情抓取 =================

def parse_detail_html(html_source, user_obj):
    soup = BeautifulSoup(html_source, 'lxml')
    # 查找包含 JSON 的 div
    data_div = soup.find('div', attrs={'data-top20-predictions-json': True})
    
    if not data_div: return None

    try:
        # 反转义并解析
        clean_json = html.unescape(data_div['data-top20-predictions-json'])
        data = json.loads(clean_json)
        
        predictions = []
        # 提取结果
        for idx, item in enumerate(data.get('results', [])):
            p_data = item.get('predictedPlayer', {})
            if p_data:
                predictions.append({
                    "rank": idx + 1,
                    "player_nick": p_data.get('nick'),
                    "player_id": p_data.get('id', {}).get('playerId')
                })
            
        return {
            "predictor_user": user_obj.get('username'),
            "predictor_id": user_obj.get('userId'),
            "predictions": predictions,
            "timestamp": time.time()
        }
    except: return None

def run_phase_2(driver, user_list_file=USER_LIST_FILE, final_output_file=FINAL_OUTPUT_FILE, hltv_domain=HLTV_DOMAIN):
    print("\n>>> [Phase 2] 启动：详情抓取")

    if not os.path.exists(user_list_file):
        print("    错误：未找到用户列表文件，请先运行 Phase 1。")
        return

    # 1. 读取任务列表
    pending_tasks = []
    with open(user_list_file, 'r', encoding='utf-8') as f:
        for line in f:
            try: pending_tasks.append(json.loads(line))
            except: pass

    # 2. 读取已完成列表 (去重)
    # 使用 predictor_user 或 predictor_id 去重均可，这里用用户名
    completed_users = load_dataset_to_set(final_output_file, 'predictor_user')

    # 3. 过滤出真正需要抓取的
    real_tasks = [u for u in pending_tasks if u['username'] not in completed_users]

    print(f"    列表总数: {len(pending_tasks)}")
    print(f"    已完成数: {len(completed_users)}")
    print(f"    待抓取数: {len(real_tasks)}")

    if not real_tasks:
        print("    所有任务已完成！")
        return

    # 4. 极速循环
    for i, user in enumerate(real_tasks):
        link = user.get('link')
        if not link: continue

        full_url = hltv_domain + link

        try:
            driver.get(full_url)
            random_sleep() # 0.2-0.5s

            result = parse_detail_html(driver.page_source, user)

            progress = f"[{i+1}/{len(real_tasks)}]"

            if result:
                count = len(result['predictions'])
                print(f"    {progress} {user['username']} ({count} preds)")
                append_line(final_output_file, result)
            else:
                # 即使失败也打印
                print(f"    {progress} [Fail] {user['username']} (无数据/解析败)")
            
            # 即使在极速模式，每抓 50 个也建议稍微停顿 2 秒让 CPU 喘口气
            if (i + 1) % 50 == 0:
                print("    --- Buffer Flush (2s) ---")
                time.sleep(2)
                
        except Exception as e:
            print(f"    [Err] {e}")
            # 遇到严重错误不要死循环
            time.sleep(2)

# ================= 主程序 =================

def main(
    chrome_version=None,
    run_phase_1=RUN_PHASE_1,
    run_phase_2=RUN_PHASE_2,
    user_list_file=USER_LIST_FILE,
    final_output_file=FINAL_OUTPUT_FILE,
    listing_api_base=LISTING_API_BASE,
    start_offset=25520,
):
    """Top20 预测爬虫主入口: Phase 1 补全用户列表, Phase 2 抓取用户详情.

    参数均可传入覆盖 (默认值 = 脚本内硬编码配置, 行为不变):
      chrome_version      Chrome 主版本号 (None = 自动检测; 本机 Chrome 151 需传 151)
      run_phase_1 / run_phase_2  阶段开关
      user_list_file / final_output_file  中间与最终输出文件路径
      listing_api_base    Top20 榜单 API URL
      start_offset        Phase 1 起始 offset (原值 25520; 从 0 开始可全量补录)
    """
    driver = get_driver(chrome_version=chrome_version)
    try:
        # 首次访问，通过 Cloudflare 检查
        # 这一步不能太快，必须给足时间让 CF 验证通过
        driver.get(HLTV_DOMAIN)
        print("正在进行首次握手 (Cloudflare)... 等待 4 秒")
        time.sleep(4)

        if run_phase_1:
            run_phase_1(driver, listing_api_base=listing_api_base, user_list_file=user_list_file, start_offset=start_offset)

        if run_phase_2:
            run_phase_2(driver, user_list_file=user_list_file, final_output_file=final_output_file)

    except KeyboardInterrupt:
        print("\n用户手动停止脚本。")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()