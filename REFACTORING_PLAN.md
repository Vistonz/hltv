# HLTV 项目代码重构与模块化设计方案 (Refactoring Design Plan)

## 1. 概述与重构目标

本项目的核心功能覆盖 HLTV 赛事的各个数据维度，包含**单项赛事数据抓取**、**战队攻防战术统计**、**EVP 评级与含金量计算**、**年度/赛季选手全量指标评比**、**社区预测分析**以及**第三方数据分析**。

当前项目存在大量顶层过程式执行代码，导入模块即启动浏览器或执行耗时爬取，且模块间函数复用困难。本次重构的目标为：

1. **功能与计算逻辑 100% 不变**：保留所有正则表达式、HLTV 页面解析选择器、软上限算法、加权数学模型、Excel 输出结构与列顺序。
2. **零副作用模块导入（Zero Side-Effect Imports）**：消除脚本在被其他 Python 文件 import 时自动启动浏览器或写文件的副作用。
3. **函数化与可复用化**：将所有顶层过程代码封装为带类型提示和默认参数的高内聚函数，同时保留 if __name__ == '__main__': 支持独立命令行运行。
4. **EVP 模块深度解耦**：针对后续需要调整数据处理后流程的需求，将 hltv evp 彻底拆分为“数据采集层 (Step 1)”、“数据清洗与加权统计层 (Step 2)”与“EVP 分数计算与透视汇总层 (Step 3)”。

---

## 2. 模块与文件全量重构方案

### 2.1 赛事单项与战队攻防模块 (hltv event/ & hltv team/)

#### 📄 hltv event/hltvsingleevent.py (589 行)
* **功能**：爬取指定单项赛事（如 event=8914）所有选手的 87 项高阶数据（传统面板、Eco 调整面板、首杀、手枪局、对阵 Top 5/10/20、生死战/回家局状态机判定、残局 1v1~1v5 等）。
* **函数设计**：
  * scrape_event_leaderboards(driver, webfront, eventfilter, min_map_count_filter, keyword=">") -> dict：抓取赛事主榜、CT/T、首杀、手枪局等列表数据。
  * scrape_player_profile_stats(driver, webfront, statsuffix) -> dict：抓取选手个人主页面板、Eco 调整数据、角色数据及对阵 Top5/10/20。
  * scrape_player_kill_distribution(driver, webfront, statsuffix, rounds) -> list：抓取 /individual 页面 0~5 杀回合占比。
  * calculate_elimination_and_map_stats(driver, webfront, statsuffix, stagedate, rounds, kills, adr, kprw, adrw) -> tuple：执行回家局状态机算法，统计淘汰局局数/Rating、胜局 Rating、各区间 Rating 比例。
  * scrape_player_clutch_stats(driver, webfront, statsuffix, rounds) -> tuple：抓取 1v1 到 1v5 残局胜利次数及加权点数。
  * scrape_single_event(event_id="8914", stagedate=None, output_path=None, min_rating=0, min_map_count=0, chrome_version=149) -> str：单项赛事全流程主入口。

#### 📄 hltv team/hltvteam.py (205 行)
* **功能**：抓取单项赛事的战队 FTU（首杀、补枪、道具伤害、闪光助攻、5v4/4v5 转化率）及手枪局数据（Overall/CT/T）。
* **函数设计**：
  * etch_team_ftu_page(driver, url, keyword=">") -> dict：抓取指定 FTU 页面的战队攻防指标。
  * etch_team_pistol_page(driver, url, keyword=">") -> dict：抓取指定手枪局页面的胜率及后续回合转化率。
  * scrape_team_stats(event_id="8914", output_path=None, min_map_count=0, chrome_version=149) -> str：战队战术与攻防统计爬虫主入口。

---

### 2.2 EVP 评级与世界排名系统 (hltv evp/)

#### 📄 hltv evp/hltv rank.py (105 行)
* **功能**：遍历指定年份所有周一的世界排名榜单（包含 2025-09-01 -> 2025-09-02 特例），提取战队名与积分。
* **函数设计**：
  * get_all_mondays_urls(year: int) -> tuple[list, list]：生成指定年份所有周一的排名页面 URL。
  * scrape_single_rank_page(driver, url: str, date_obj, base_save_dir: str) -> bool：抓取单周世界排名数据并保存为 Excel。
  * crawl_yearly_rankings(year=2026, base_save_dir="database/rank", chrome_version=148) -> None：年度周排名全量爬取主入口。

#### 📄 hltv evp/eventrank.py (172 行)
* **功能**：根据各赛事参赛队伍在开赛当周的 HLTV 积分，计算赛事在全球总分中的权重占比。
* **函数设计**：
  * get_event_id_from_url(url: str) -> str：从 URL 中提取赛事 ID。
  * load_team_points_for_date(date_str: str, rank_db_directory: str) -> tuple[dict, float]：加载指定日期的战队积分字典及世界总分。
  * calculate_single_event_weight(event_url: str, base_directory: str, rank_db_directory: str, split_event_keywords=None) -> float：计算单项赛事的含金量权重。
  * calculate_all_event_weights(event_urls=None, base_directory=None, rank_db_directory=None, output_file_path=None) -> dict：批量计算所有赛事权重并导出 Excel 查找表。

#### 📄 hltv evp/hltv evp.py (827 行)
* **功能**：EVP 评级核心计算管线，支持分步独立执行与一键串联。
* **函数设计**：
  * **数学计算层**：
    * get_rank_weight(opponent_rank: int, base_c=0.5, k=6.0) -> float
    * pply_symmetrical_soft_cap(score: float, cap=30.0, base=5.0) -> float
    * calculate_performance_score(player_rating, stage_weight, rank_weight, team_avg_rating, match_baseline_rating, round_differential, upper_power=1.2) -> float
  * **Step 1: 原始数据爬取**：
    * scrape_match_map_data(driver, match_url: str, team_rank_map: dict) -> list[dict]
    * un_step1_scrape_data(event_urls=None, event_filters=None, base_directory=None, chrome_version=147) -> bool
  * **Step 2: 数据清洗与标准化打分**：
    * process_event_raw_data(raw_data_path: str, stage_weight_map: dict, group_cap=30.0) -> pd.DataFrame
    * un_step2_calculate_global_stats(event_urls=None, base_directory=None, event_score_file=None, output_stats_file=None) -> tuple[bool, dict, dict]
  * **Step 3: EVP 分数计算与数据透视表**（后续重点修改点）：
    * calculate_event_evp_scores(df_raw: pd.DataFrame, current_event_score: float, global_mean: float, global_std: float, stage_weight_map: dict) -> tuple[pd.DataFrame, pd.DataFrame]
    * un_step3_calculate_evp_pivot(event_urls=None, base_directory=None, event_score_file=None, global_summary_file=None) -> None
  * **主入口**：
    * un_full_evp_pipeline(event_urls=None, base_directory=None) -> None

---

### 2.3 年度评选与赛季报表模块 (hltv year/ & hltv top/)

#### 📄 hltv year/hltvnew.py (557 行)
* **功能**：年度全量高阶数据爬虫（90+ 列指标，含 8 种复合赛事类型、微观战术、击杀平均武器价值计算）。
* **函数设计**：
  * parse_stat_value(val: any) -> any：纯函数化解析百分比、浮点数与字符，消除全局变量副作用。
  * scrape_sub_event_stats(driver, url: str, keyword=">") -> tuple[list, list, list]：抓取特定赛事类型的选手名字、地图数与 Rating。
  * scrape_player_weapon_economy(driver, webfront: str, statsuffix: str) -> float：抓取选手武器击杀分布并计算加权武器价值。
  * scrape_player_year_metrics(driver, webfront: str, player_basic_info: dict, multi_event_data: dict) -> list：抓取单个选手的 90+ 项年度指标。
  * un_yearly_scrape(output_file="rating2026.xlsx", min_map_count=65, min_rating=1.04, chrome_version=149) -> str：年度全量数据爬取主入口。

#### 📄 hltv top/top.py (272 行)
* **功能**：赛季分站赛表现数据爬取，增量维护 grade.xlsx。
* **函数设计**：
  * etch_event_team_ratings(driver, teamfront: str, event_filter: str) -> dict：抓取赛事战队平均 Rating。
  * etch_event_team_grades(driver, sub_event_ids: list) -> dict：抓取战队最终名次成绩 (Grade)。
  * scrape_season_events(event_filters=None, event_names=None, output_dir=None, grade_filename="grade.xlsx", chrome_version=148) -> str：赛季数据抓取主入口。

#### 📄 hltv top/classify.py (228 行)
* **功能**：选手高阶数据指标分类（影响力、高阶、其他）、正反向排名计算及中文化输出。
* **函数设计**：
  * clean_and_normalize_rankings_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]：执行 DPR 反转、百分比转换及排名计算。
  * generate_classified_text_report(df: pd.DataFrame, rank_df: pd.DataFrame) -> str：生成结构化分类文本。
  * process_sorted_player_rankings_final(input_file_path: str, output_folder: str) -> str：对外公开的处理主函数。

#### 📄 hltv top/html.py (420 行)
* **功能**：基于模板与阈值，批量生成 HLTV 风格的可视化 HTML 战绩单。
* **函数设计**：
  * load_awards_mapping(award_file_path: str, event_mapping: dict) -> dict：加载选手荣誉映射。
  * ender_single_player_html(player_name: str, player_df: pd.DataFrame, player_awards_map: dict) -> str：渲染单人 HTML 页面。
  * generate_all_player_tournament_sheets(grade_file_path=None, award_file_path=None, output_dir=None) -> int：全量生成报表主入口。

---

### 2.4 HLTV 预测与社区数据挖掘 (hltv predict/)

#### 📄 hltv predict/predict.py (265 行)
* **功能**：HLTV Top 20 社区预测爬虫（Phase 1 抓取用户清单，Phase 2 抓取预测明细）。
* **函数设计**：
  * get_driver(headless=False) -> uc.Chrome
  * un_phase_1(driver, top20_id="2025", user_list_file="hltv_user_list.jsonl", min_sleep=0.2, max_sleep=0.5) -> None
  * parse_detail_html(html_source: str, user_obj: dict) -> dict
  * un_phase_2(driver, user_list_file="hltv_user_list.jsonl", final_output_file="hltv_predictions_2025.jsonl", min_sleep=0.2, max_sleep=0.5) -> None
  * un_predict_crawler(top20_id="2025", run_p1=True, run_p2=True) -> None

#### 📄 hltv predict/summary.py (126 行)
* **功能**：社区预测数据统计，生成过滤总榜及 1~20 名各分位投票分布。
* **函数设计**：
  * nalyze_predictions(input_file="hltv_predictions_2025.jsonl", output_file="HLTV_Prediction_Filtered_Analysis.xlsx", threshold_ratio=0.10) -> None

---

### 2.5 选手库、极值挖掘与第三方平台 (i/ & skybox/)

#### 📄 i/i.py (41 行)
* **功能**：从本地 HTML 提取选手 ID 和名字。
* **函数设计**：
  * extract_player_data(file_path=..., output_path=...) -> list[dict]

#### 📄 i/ixilie.py (181 行)
* **功能**：筛选选手失常比赛（死亡 - 击杀 >= 10）。
* **函数设计**：
  * extract_matches_from_page(content: str, player_id: str, player_name: str, offset: int, diff_threshold=10) -> tuple[list, bool, int]
  * get_matches_for_player(driver, player_id: str, player_name: str, diff_threshold=10) -> list[dict]
  * ind_worst_matches_all_players(players_file=None, json_output=None, excel_output=None, diff_threshold=10, player_limit=None) -> list[dict]

#### 📄 skybox/skybox.py (197 行)
* **功能**：Skybox.gg 平台爬虫与 OCR 图像识别。
* **函数设计**：
  * extract_adr_from_region(image, box, tesseract_cmd=None) -> int
  * scrape_skybox_leaderboard(driver, totalwebfront, events_total, max_pages=4) -> tuple[list, list]
  * scrape_player_skybox_details(driver, player_id, name, events_id, playerwebfront) -> list
  * un_skybox_crawler(output_file=None, events_id=None, selected_players=None) -> None

---

## 3. 重构实施与验证策略

1. **分阶段执行**：
   - Phase 1: i/ 及 skybox/
   - Phase 2: hltv predict/
   - Phase 3: hltv event/ 及 hltv team/
   - Phase 4: hltv top/
   - Phase 5: hltv evp/（重点解耦 Step 1, Step 2, Step 3）
   - Phase 6: hltv year/
2. **正确性验证**：
   - 对每个重构文件进行 Python AST 语法校验（python -m py_compile）。
   - 验证所有模块在 import 时无浏览器弹出与无网络请求（即无副作用）。
   - 验证模块在主入口调用时参数能正确传递且完全兼容原有逻辑。
