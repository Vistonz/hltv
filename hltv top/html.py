import pandas as pd
import os

# ================= 配置区域 =================
# 请确保路径正确，指向你的实际文件
grade_file_path = r'C:\Users\10725\Desktop\hltv\hltv top\grade.xlsx'
award_file_path = r'C:\Users\10725\Desktop\hltv\hltv top\1Personal Award.xlsx'
output_dir = r'C:\Users\10725\Desktop\hltv\hltv top'

# 确保输出目录存在
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 评分阈值
avg_highvalues = {
    "adr": 75, "kpr": 0.70, "dpr": 0.70, "rs": 1.0, 
    "kast": 75, "rating": 1.04, "rank_change": 0.04,
}
avg_lowvalues = {
    "adr": 69, "kpr": 0.62, "dpr": 0.62, "rs": -0.7, 
    "kast": 69, "rating": 0.96, "rank_change": -0.04,
}

# ================= 1. 读取主数据 (Stats) =================
print(">>> 正在读取 Stats 数据...")

try:
    df = pd.read_excel(grade_file_path)
    print(f"成功读取主数据: {grade_file_path}")
except Exception as e:
    print(f"读取 grade.xlsx 失败: {e}")
    exit()

# 定义排名转换规则
def rank_to_text(rank):
    try:
        if rank == 1: return "1st"
        elif rank == 2: return "2nd"
        elif rank == 3: return "3rd"
        elif rank in [4, 5]: return f"{rank}th"
        return str(rank)
    except:
        return str(rank)

# 应用排名转换 (自动寻找Grade列)
# ================= 2. 读取并处理荣誉数据 (Awards) =================
# ================= 2. 读取并处理荣誉数据 (Awards) =================
print(">>> 正在读取 Awards 数据...")

player_awards_map = {} 

try:
    df_awards = pd.DataFrame()
    
    # 策略：先尝试当做 Excel 读取 (即使后缀是 csv，内容可能是 Excel)
    try:
        df_awards = pd.read_excel(award_file_path)
    except Exception:
        # 如果 Excel 读取失败，再尝试当做 CSV 读取
        read_kwargs = {'sep': None, 'engine': 'python', 'on_bad_lines': 'skip'}
        try:
            df_awards = pd.read_csv(award_file_path, encoding='utf-8', **read_kwargs)
        except:
            try:
                df_awards = pd.read_csv(award_file_path, encoding='gbk', **read_kwargs)
            except:
                df_awards = pd.read_csv(award_file_path, encoding='latin1', **read_kwargs)

    # 二次检查：防止 CSV 读取误把 Excel 二进制当文本读入 (特征是列名包含 PK)
    if not df_awards.empty:
        # 检查列名是否包含乱码特征
        cols_str = "".join([str(c) for c in df_awards.columns])
        if "PK" in cols_str and "\\x" in cols_str:
            print("检测到文件实质为 Excel 格式，正在重试读取...")
            try:
                df_awards = pd.read_excel(award_file_path)
            except Exception as e:
                print(f"Excel 读取模式也失败: {e}")

    print(f"成功读取荣誉文件，共 {len(df_awards)} 行。")

    # --- 智能识别列名 ---
    col_map = {}
    # 清理列名空格
    df_awards.columns = [str(c).strip() for c in df_awards.columns]
    
    for col in df_awards.columns:
        c_clean = str(col).strip().lower()
        if 'id' == c_clean or 'player' in c_clean:
            col_map['ID'] = col
        elif 'tourn' in c_clean or 'event' in c_clean:
            col_map['Tournament'] = col
        elif 'award' in c_clean:
            col_map['Award'] = col
            
    # 检查关键列
    if 'Tournament' not in col_map or 'Award' not in col_map or 'ID' not in col_map:
        print(f"错误: 无法识别荣誉文件表头。当前列名: {list(df_awards.columns)}")
    else:
        # 英文赛事名 -> 中文赛事ID 的映射
        event_mapping = {
            "BLAST Bounty 2025 Season 1": "BLAST赏金赛S1",
            "IEM Katowice 2025": "IEM卡托维兹",
            "PGL Cluj-Napoca 2025": "PGL克鲁日纳波卡",
            "EPL S21": "EPL S21",
            "BLAST Open Lisbon 2025": "BLAST里斯本公开赛",
            "PGL Bucharest 2025": "PGL布加勒斯特",
            "IEM Melbourne 2025": "IEM墨尔本",
            "BLAST Rivals 2025 Season 1": "BLAST对抗赛S1",
            "PGL Astana 2025": "PGL阿斯塔纳",
            "IEM Dallas 2025": "IEM达拉斯",
            "BLAST.tv Austin Major 2025": "BLAST奥斯汀Major",
            "FISSURE Playground 1": "裂变天地S1",
            "IEM Cologne 2025": "IEM科隆",
            "BLAST Bounty 2025 Season 2": "BLAST赏金赛S2",
            "Esports World Cup 2025": "电竞世界杯",
            "BLAST Open London 2025": "BLAST伦敦公开赛",
            "FISSURE Playground 2": "裂变天地S2",
            "EPL S22": "EPL S22",
            "CS Asia Championships 2025": "CAC2025",
            "Thunderpick World Championship 2025": "Thunderpick世界锦标赛",
            "PGL Masters Bucharest 2025": "PGL布加勒斯特大师赛",
            "IEM Chengdu 2025": "IEM成都",
            "BLAST Rivals 2025 Season 2": "BLAST对抗赛S2",
            "StarLadder Budapest Major 2025":"SL布达佩斯Major",
        }

        match_count = 0
        for _, row in df_awards.iterrows():
            try:
                # 使用智能识别到的列名获取数据
                p_name = str(row[col_map['ID']]).strip()
                t_eng = str(row[col_map['Tournament']]).strip().replace('"', '')
                award = str(row[col_map['Award']]).strip()
                
                if not award or award.lower() == 'nan':
                    continue
                    
                # 尝试匹配中文赛事名
                t_chn = event_mapping.get(t_eng)
                
                if t_chn:
                    player_awards_map[(p_name, t_chn)] = award
                    match_count += 1
            except Exception:
                continue
                
        print(f"荣誉数据处理完毕，建立 {match_count} 条映射关系。")

except Exception as e:
    print(f"读取荣誉文件严重失败: {e}")

# ================= 3. 资源定义 =================

tournament_logos = {
    "BLAST赏金赛S1": "https://img-cdn.hltv.org/eventtrophy/eJQzbqPQNMO_CMFslGXH36.png?ixlib=java-2.1.0&w=200&s=366290fc440a953422387967f5ca18ce",
    "IEM卡托维兹": "https://img-cdn.hltv.org/eventtrophy/Rw5lw84rBupRg1-Ig1dNOo.png?ixlib=java-2.1.0&w=200&s=f6e4c8fa1d093b8f167fca76759354d7",
    "PGL克鲁日纳波卡": "https://img-cdn.hltv.org/eventtrophy/ddhXBShpxl3rJ5Co1pISIr.png?ixlib=java-2.1.0&w=200&s=5a11f8d88119db52b37829e72d1cb41d",
    "EPL S21": "https://img-cdn.hltv.org/eventtrophy/xj3JGis_2olnWMCNqxaTWj.png?ixlib=java-2.1.0&w=200&s=1fc78a5da4245c1a18a0c75a4bece401",
    "BLAST里斯本公开赛": "https://img-cdn.hltv.org/eventtrophy/UzCUCyAHb-WQyY6YQInp70.png?ixlib=java-2.1.0&w=200&s=15bba227eaab595cb7d3dcca5b4a3907",
    "PGL布加勒斯特": "https://img-cdn.hltv.org/eventtrophy/X9N5PAOW_wrIQSYWcRoW7D.png?ixlib=java-2.1.0&w=200&s=a03971d29e9cc8fd0b942adadd27e7b9",
    "IEM墨尔本": "https://img-cdn.hltv.org/eventtrophy/tALCDw0tHAUjhTxGR4ViCM.png?ixlib=java-2.1.0&w=200&s=e5e76b9e65d8fe747f92bb67fb7ca0d2",
    "BLAST对抗赛S1": "https://img-cdn.hltv.org/eventtrophy/AXrTaJeRpjYPOdeSpnZz1V.png?ixlib=java-2.1.0&w=200&s=9643366af9dd45258315c3317e1228b5",
    "PGL阿斯塔纳": "https://img-cdn.hltv.org/eventtrophy/Ar0GZFlqv5inDS4Pjd5qrI.png?ixlib=java-2.1.0&w=200&s=3dedcacc3cb360797aa861139b26fad0",
    "IEM达拉斯": "https://img-cdn.hltv.org/eventtrophy/C9DKGFLLfdiyrjnRKEwm11.png?ixlib=java-2.1.0&w=200&s=f033b352fb1a7ac998bdedd1467bbcb6",
    "BLAST奥斯汀Major": "https://img-cdn.hltv.org/eventtrophy/5d4LzgfGCZm_hGKRvMHjOI.png?ixlib=java-2.1.0&w=200&s=fcffadfd95eeeeec000f4b771864be08",
    "裂变天地S1": "https://img-cdn.hltv.org/eventtrophy/93Y3cg_mxixKv2mXkiDRcU.png?ixlib=java-2.1.0&w=200&s=beb3dc1f747ae596a10ddafc0188ea35",
    "IEM科隆": "https://img-cdn.hltv.org/eventtrophy/kz5mo2yl7o0iwRjx3z3hlP.png?ixlib=java-2.1.0&amp;w=200&amp;s=7ad3e2b6cffdbef6bd48257195788151",
    "BLAST赏金赛S2": "https://img-cdn.hltv.org/eventtrophy/L14lcNYoIiNotG5WaLa9KM.png?ixlib=java-2.1.0&amp;w=200&amp;s=9a9aac3895cbe6fb4a5a4a7cb6d3564c",
    "电竞世界杯": "https://img-cdn.hltv.org/eventtrophy/FHFzLHeB2f-0Zin2Dy4xNq.png?ixlib=java-2.1.0&amp;w=200&amp;s=47501f82ca09c2a8004d9d34dd922b4f", 
    "BLAST伦敦公开赛": "https://img-cdn.hltv.org/eventtrophy/kPrc3nLNBk5vgC6PM7ltga.png?ixlib=java-2.1.0&w=200&s=55f0e525c8d4f4ef5e5d55f3d156d308",
    "裂变天地S2": "https://img-cdn.hltv.org/eventtrophy/3L4LhGNGfTcHHjZiAw6XiO.png?ixlib=java-2.1.0&amp;w=200&amp;s=e19bb03917f105481071445f0bbf5d8d",
    "EPL S22": "https://img-cdn.hltv.org/eventtrophy/DlAQc2NhVb74CEliaDYaIy.png?ixlib=java-2.1.0&w=200&s=a422ddb6ab61d7d2dd7395bfbe1effce",
    "CAC2025": "https://img-cdn.hltv.org/eventtrophy/sx8ElFaPVTVihS83JAbmnk.png?ixlib=java-2.1.0&w=200&s=7dfaf2232705c2a7f085493216aacbc8",
    "Thunderpick世界锦标赛": "https://img-cdn.hltv.org/eventtrophy/qhNXnEiw_pVg2VmcOIOTzu.png?ixlib=java-2.1.0&amp;w=200&amp;s=4595ddf73d4a422c952faa645d3147f6", 
    "PGL布加勒斯特大师赛": "https://img-cdn.hltv.org/eventtrophy/WAE0hGXkSDuNPBSjd9J7R9.png?ixlib=java-2.1.0&w=200&s=0c7d21f835a2b4ed9d86da21965bd2c6",
    "IEM成都": "https://img-cdn.hltv.org/eventtrophy/l00l3KK2uGZm0Wh31vp_Le.png?ixlib=java-2.1.0&amp;w=200&amp;s=02d8ffbf336ea5f92c9c2c43425d0445",
    "BLAST对抗赛S2": "https://img-cdn.hltv.org/eventtrophy/aHlSV7nOTHK0Nmy9v4NaDc.png?ixlib=java-2.1.0&amp;w=200&amp;s=bbcf12e1c633fd0866a45b0224dcc62e",
    "SL布达佩斯Major":"https://img-cdn.hltv.org/eventtrophy/JFWvpqNBeEd2yUtXiU9cvc.png?ixlib=java-2.1.0&w=200&s=ef679ffebd7171110d470e2225261542",
}

tournament_links = {
    "BLAST赏金赛S1": "https://www.hltv.org/events/7903/blast-bounty-2025-season-1",
    "IEM卡托维兹": "https://www.hltv.org/events/8034/iem-katowice-2025",
    "PGL克鲁日纳波卡": "https://www.hltv.org/events/8043/pgl-cluj-napoca-2025",
    "EPL S21": "https://www.hltv.org/events/8292/esl-pro-league-season-21",
    "BLAST里斯本公开赛": "https://www.hltv.org/events/7904/blast-open-lisbon-2025",
    "PGL布加勒斯特": "https://www.hltv.org/events/8044/pgl-bucharest-2025",
    "IEM墨尔本": "https://www.hltv.org/events/8036/iem-melbourne-2025",
    "BLAST对抗赛S1": "https://www.hltv.org/events/7905/blast-rivals-2025-season-1",
    "PGL阿斯塔纳": "https://www.hltv.org/events/8045/pgl-astana-2025",
    "IEM达拉斯": "https://www.hltv.org/events/8037/iem-dallas-2025",
    "BLAST奥斯汀Major": "https://www.hltv.org/events/7902/blasttv-austin-major-2025",
    "裂变天地S1": "https://www.hltv.org/events/8063/fissure-playground-1",
    "IEM科隆": "https://www.hltv.org/events/8038/iem-cologne-2025",
    "BLAST赏金赛S2": "https://www.hltv.org/events/7906/blast-bounty-2025-season-2",
    "电竞世界杯": "https://www.hltv.org/events/8039/esports-world-cup-2025",
    "BLAST伦敦公开赛": "https://www.hltv.org/events/7907/blast-open-london-2025",
    "裂变天地S2": "https://www.hltv.org/events/8064/fissure-playground-2",
    "EPL S22": "https://www.hltv.org/events/8040/esl-pro-league-season-22",
    "CAC2025": "https://www.hltv.org/events/8027/cs-asia-championships-2025",
    "Thunderpick世界锦标赛": "https://www.hltv.org/events/8067/thunderpick-world-championship-2025",
    "PGL布加勒斯特大师赛": "https://www.hltv.org/events/8046/pgl-masters-bucharest-2025",
    "IEM成都": "https://www.hltv.org/events/8041/iem-chengdu-2025",
    "BLAST对抗赛S2": "https://www.hltv.org/events/7908/blast-rivals-2025-season-2",
}

team_logos = {
    "Natus Vincere": "https://img-cdn.hltv.org/teamlogo/9iMirAi7ArBLNU8p3kqUTZ.svg?ixlib=java-2.1.0&s=4dd8635be16122656093ae9884675d0c",
    "FaZe Clan": "https://img-cdn.hltv.org/teamlogo/5HqZyv4yVXhdmPzA6q1B86.svg?ixlib=java-2.1.0&s=56dbd99cb52c437fdfeee58e9d4c1e4d",
    "Vitality":"https://img-cdn.hltv.org/teamlogo/ogcHrcCdzRvxbYvAz04KAN.png?ixlib=java-2.1.0&w=50&s=e1f6019aa9f274ffe45a5e99c88dbc02",
    "Spirit":"https://img-cdn.hltv.org/teamlogo/syrtYYKR7sBRw3ZHy1YFX7.png?ixlib=java-2.1.0&w=50&s=40e66714687bec05ea422255b1c0099e",
    "The MongolZ":"https://img-cdn.hltv.org/teamlogo/bRk2sh_tSTO6fq1GLhgcal.png?ixlib=java-2.1.0&w=50&s=8b08e53858eb817852ae74b30a30151d",
    "MOUZ":"https://img-cdn.hltv.org/teamlogo/IejtXpquZnE8KqYPB1LNKw.svg?ixlib=java-2.1.0&s=7fd33b8def053fbfd8fdbb58e3bdcd3c",
    "Eternal Fire":"https://img-cdn.hltv.org/teamlogo/Tafdq71X3B_-73b73bAixr.png?ixlib=java-2.1.0&w=100&s=acf07fab5478f7dda7201085fc55e467",
    "Aurora":"https://img-cdn.hltv.org/teamlogo/yJzPNOeXlyiniNxanYJCrv.png?ixlib=java-2.1.0&w=50&s=2c08f70c2f2f8c2024a438ddcf19bbf1",
    "Falcons":"https://img-cdn.hltv.org/teamlogo/4eJSkDQINNM6Tbs4WvLzkN.png?ixlib=java-2.1.0&w=50&s=d8c857ea47046f61eca695beab0d12ef",
    "FaZe":"https://img-cdn.hltv.org/teamlogo/66pHABGIztb3uoDAU18k76.png?ixlib=java-2.1.0&w=50&s=1aeaeb52d80c1f20afe885e4ddd5896c",
    "G2":"https://img-cdn.hltv.org/teamlogo/zFLwAELOD15BjJSDMMNBWQ.png?ixlib=java-2.1.0&w=50&s=affb583e6716d8ee904826992255cc4b",
    "FURIA":"https://img-cdn.hltv.org/teamlogo/mvNQc4csFGtxXk5guAh8m1.svg?ixlib=java-2.1.0&s=11e5056829ad5d6c06c5961bbe76d20c",
    "Liquid":"https://img-cdn.hltv.org/teamlogo/JMeLLbWKCIEJrmfPaqOz4O.svg?ixlib=java-2.1.0&s=c02caf90234d3a3ebac074c84ba1ea62",
}

# ================= HTML 模板 =================

html_head1_template = """
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <title>{player_name}</title>
        <link rel="stylesheet" href="./hltvstyle.css">
    </head>  
    <body class="cols1101" data-livescore-server-url="https://scorebot-lb.hltv.org" style="background-color: rgb(255, 255, 255);" inmaintabuse="1">
        <nav class="navbar-smartphone smartphone-only" id="navBarSmartphone">
          <ul class="nav-content-smartphone">
            <li class="nav-logo"><a href="/" class="small-logo"><img alt="HLTV.org" src="/img/static/TopSmallLogo2x.png" class="small-logo-img" loading="lazy"></a></li>
            <ul class="nav-item" id="navItem__oSpdJ7" data-nav-item=""><a href="/" class="nav-link">News</a></ul>
            <ul class="nav-item" id="navItem9eRkTsRR" data-nav-item=""><a href="/matches" class="nav-link">Matches</a></ul>
            <ul class="nav-item" id="navItemvGwczGP2" data-nav-item=""><a href="/results" class="nav-link">Results</a></ul>
            <ul class="nav-item" id="navItemWjQXksux" data-nav-item=""><a href="/events" class="nav-link">Events</a></ul>
            <li class="navsmartphone-extras" data-nav-smartphone-menu-open-button=""><a href="#" class="dot-menu dot-menu-smartphone"><div data-reactroot="" class="dots-wrapper "><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></a></li>
          </ul>
        </nav>
        
        <div class="bgPadding">
              <div class="bg-sidebar left narrow sticky-offset">
                <div class="secondary-sidebar-container"><div class="v-wrapper" data-trdswuppiz="FirstColumnBottom1" data-qhltyfmqpw="703" style="min-height: 0px;"><div class="ready-vm-placement" data-vid="5ed0d404b519801b8a4d4edc"></div></div></div>
              </div>
              <div class="bg-sidebar left wide sticky-offset">
                <div class="secondary-sidebar-container"><div class="v-wrapper" data-trdswuppiz="BelowBackgroundLeftSideStickyWide" data-depuajcudw="703" style="min-height: 0px;"><div class="ready-vm-placement" data-vid="5ed0d404b519801b8a4d4edc"></div></div></div>
              </div>
              <div class="bg-sidebar right narrow sticky-offset">
                <div class="secondary-sidebar-container"><div class="v-wrapper" data-wxpdxamgmk="FourthColumnBottom1" data-diqorhwazt="704" style="min-height: 0px;"><div class="ready-vm-placement" data-vid="5ea1c28867200b43179499d0"></div></div></div>
              </div>
              <div class="bg-sidebar right wide sticky-offset">
                <div class="secondary-sidebar-container"><div class="v-wrapper" data-wxpdxamgmk="BelowBackgroundRightSideStickyWide" data-zquhebbvxj="704" style="min-height: 0px;"><div class="ready-vm-placement" data-vid="5ea1c28867200b43179499d0"></div></div></div>
              </div>
            
          <div class="widthControl">
            <div class="colCon">
                <div class="contentCol">
                  <div class="smartphone-only mobiletop"><div class="v-wrapper" data-wxpdxamgmk="TopMobile" data-wrgowvwwhc="732" style="min-height: 0px;"><div data-ref="vm-preloader" style="width: 320px; max-width: 320px; min-width: 320px; height: 50px; display: flex; flex-direction: column; justify-content: center; align-items: center; margin: 0px auto;"><div class="vm-placement" data-vid="633a8556c672387bad423389" data-id="633a8556c672387bad423389" data-pos="1113" id="633a8556c672387bad423389-1113" data-reg="true"></div></div></div></div>
                
                <article class="newsitem standard-box">
                    <div class="newsdsl">
                    <div class="newstext-con">
                        <div class="image-con"></div>
                        <div class="newsdsl-tournament-stat-widget">
                        <div class="newsdsl-tournament-stat-widget-player-info"><img alt="{player_country}" src="{player_flag_url}" class="flag" title="{player_country}" loading="lazy">{player_name1}</div>
                        <div class="newsdsl-tournament-stat-widget-stat-info">2025年正赛数据</div>
                        <table class="table-container ">
                          <thead>
                            <tr>
                              <th class="newsdsl-tournament-stat-widget-tournament"><span class="gtSmartphone-only">赛事</span><span class="smartphone-only">赛事</span></th>
                              <th class="newsdsl-tournament-stat-widget-team">战队 (名次)</th>
                              <th class="newsdsl-tournament-stat-widget-rating">Rating 3.0<span class="gtSmartphone-only"> (同比队内)</span></th>
                              <th class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">ADR</th>
                              <th class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">KPR</th>
                              <th class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">DPR</th>
                              <th class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">RS</th>
                              <th class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">KAST</th>
                              <th class="newsdsl-tournament-stat-widget-adr">个人荣誉</th>
                            </tr>
                          </thead>
                          <tbody>
"""

# HTML尾部，不再是列表
html_tail_str = """                          </tbody>
                        </table>
                        <div class="newsdsl-tournament-stat-widget-legend-container">
                            <div class="newsdsl-tournament-stat-legend">
                                <div class="newsdsl-tournament-stat-legend-square positive"></div>
                                高于平均值5%+
                            </div>
                            <div class="newsdsl-tournament-stat-legend">
                                <div class="newsdsl-tournament-stat-legend-square negative"></div>
                                低于平均值5%+
                            </div>
                            <div class="newsdsl-tournament-stat-legend">
                                <div class="newsdsl-tournament-stat-legend-square average"></div>
                                与平均值相差不超过5%
                            </div>
                        </div>
                        </div>
                    </div>
                    </div>
                </article>
                </div>
                <div class="news-forum-spacer"></div>
            </div>
            </div>
            <div class="colCon"></div>
          </div>
        </div>
        </body>
</html>
"""

# HTML行模板
html_template = """
<tr>
    <td class="newsdsl-tournament-stat-widget-tournament text-ellipsis">
    <a href="{tournament_link}">
        <div class="newsdsl-tournament-stat-widget-tournament-logo-container">
            <img alt="{tournament_name}" 
                src="{tournament_logo}" 
                class="newsdsl-tournament-stat-widget-tournament-logo" 
                title="{tournament_name}">
        </div>
        {tournament_name}
    </a>
    </td>
    <td class="newsdsl-tournament-stat-widget-team">
        <div class="newsdsl-tournament-stat-widget-team-logo-container">
            <img alt="{team_name}" 
                src="{team_logo}" 
                class="newsdsl-tournament-stat-widget-team-logo" 
                title="{team_name}">
        </div>
        <span class="newsdsl-tournament-stat-widget-place">({team_rank})</span>
    </td>
    <td class="newsdsl-tournament-stat-widget-rating">
        <span>{rating}</span>
        <span class="newsdsl-tournament-stat-widget-in-team gtSmartphone-only">
            (#{rank_in_team}, {rank_change}</span>)
        </span>
    </td>
    <td class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">{adr}</td>
    <td class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">{kpr}</td>
    <td class="newsdsl-tournament-stat-widget-adr gtSmartphone-only ">{dpr}</td>
    <td class="newsdsl-tournament-stat-widget-adr gtSmartphone-only ">{rs}</td>
    <td class="newsdsl-tournament-stat-widget-adr gtSmartphone-only">{kast}</td>
    <td class="newsdsl-tournament-stat-widget-adr">{award}</td>
</tr>
"""

# ================= 主逻辑：循环生成所有选手HTML =================

# 获取所有不重复的选手名称
try:
    unique_players = df['Player'].unique()
    print(f"检测到 {len(unique_players)} 位选手，开始生成HTML...")
except KeyError:
    print("错误：grade文件中没有找到 'Player' 列。请检查文件格式。")
    exit()

count = 0
for player_name in unique_players:
    # 筛选该选手的数据
    filtered_df = df[df['Player'] == player_name]
    
    if filtered_df.empty:
        continue

    # 获取基本信息 (国籍等)
    player_country = "Unknown"
    player_flag_url = ""
    
    # 安全获取第一行数据
    try:
        first_row = filtered_df.iloc[0]
        player_country = first_row.get('Country', "Unknown")
        raw_url = str(first_row.get('CountryURL', ""))
        
        if raw_url.startswith("http"):
            player_flag_url = raw_url
        elif raw_url:
            player_flag_url = "https://www.hltv.org" + raw_url
    except Exception:
        pass

    # 初始化 HTML 行列表
    html_rows = []
    
    # 填充 HTML 头部
    html_head_filled = html_head1_template.format(
        player_name=player_name,
        player_name1=player_name,
        player_country=player_country,
        player_flag_url=player_flag_url
    )

    # 遍历该选手的所有赛事行
    for index, row in filtered_df.iterrows():
        try:
            tournament_name = row.get('Event_ID', "")  # 赛事名称
            team_name = row.get('Team', "")
            team_rank = row.get('Grade', "")
            rating = row.get('Rating', 0.0)
            rank_in_team = row.get('Team_Rank', "")
            rank_change = row.get('Rating_Diff(%)', 0.0)
            adr = row.get('ADR', 0.0)
            kpr = row.get('KPR', 0.0)
            dpr = row.get('DPR', 0.0)
            rs = row.get('RS', 0.0)
            kast = row.get('KAST', 0.0)

            # 辅助函数：根据数值分配 class
            def assign_class(value, high, low, inverse=False):
                try:
                    val = float(value)
                    if not inverse:
                        if val > high: return "won"
                        elif val < low: return "lost"
                    else:
                        if val > high: return "lost"
                        elif val < low: return "won"
                except (ValueError, TypeError):
                    pass
                return ""

            adr_class = assign_class(adr, avg_highvalues['adr'], avg_lowvalues['adr'])
            kpr_class = assign_class(kpr, avg_highvalues['kpr'], avg_lowvalues['kpr'])
            dpr_class = assign_class(dpr, avg_highvalues['dpr'], avg_lowvalues['dpr'], inverse=True)
            rs_class = assign_class(rs, avg_highvalues['rs'], avg_lowvalues['rs'])
            kast_class = assign_class(kast, avg_highvalues['kast'], avg_lowvalues['kast'])
            rating_class = assign_class(rating, avg_highvalues['rating'], avg_lowvalues['rating'])
            rank_change_class = assign_class(rank_change, avg_highvalues['rank_change'], avg_lowvalues['rank_change'])

            # 格式化数据
            try:
                rank_change_str = f"{(float(rank_change))*100:.0f}%"
                kast_str = f"{float(kast):.1f}%"
                rating_str = f"{float(rating):.2f}"
                kpr_str = f"{float(kpr):.2f}"
                dpr_str = f"{float(dpr):.2f}"
                if float(rs) > 0:
                    rs_str = f"+{float(rs):.2f}"
                else:
                    rs_str = f"{float(rs):.2f}"
                adr_str = f"{float(adr):.1f}"
            except (ValueError, TypeError):
                rank_change_str = str(rank_change)
                kast_str = str(kast)
                rating_str = str(rating)
                kpr_str = str(kpr)
                dpr_str = str(dpr)
                rs_str = str(rs)
                adr_str = str(adr)

            # 获取LOGO和链接
            tournament_logo = tournament_logos.get(tournament_name, "")
            tournament_link = tournament_links.get(tournament_name, "")
            team_logo = team_logos.get(team_name, "")

            # --- 获取荣誉数据 ---
            # 使用预处理好的字典：(选手名, 赛事名) -> 荣誉
            award_text = player_awards_map.get((str(player_name).strip(), str(tournament_name).strip()), "")
            
            # 填充行模板
            html_row = html_template.format(
                tournament_name=tournament_name,
                tournament_link=tournament_link,
                tournament_logo=tournament_logo,
                team_name=team_name,
                team_logo=team_logo,
                team_rank=team_rank,
                rating=f'<span class="{rating_class}">{rating_str}</span>',
                rank_in_team=rank_in_team,
                rank_change=f'<span class="{rank_change_class}">{rank_change_str}</span>',
                adr=f'<span class="{adr_class}">{adr_str}</span>',
                kpr=f'<span class="{kpr_class}">{kpr_str}</span>',
                dpr=f'<span class="{dpr_class}">{dpr_str}</span>',
                rs=f'<span class="{rs_class}">{rs_str}%</span>',
                kast=f'<span class="{kast_class}">{kast_str}</span>',
                award=award_text # 填入动态获取的荣誉
            )
            html_rows.append(html_row)
        except Exception as e_row:
            print(f"处理行数据时出错: {e_row}")
            continue

    # 组合最终HTML
    final_html = html_head_filled + "\n".join(html_rows) + html_tail_str

    # 写入文件
    safe_player_name = str(player_name).replace('/', '_').replace('\\', '_') # 防止文件名非法字符
    output_html_path = os.path.join(output_dir +'\\html', f'{safe_player_name}_tournament_sheet.html')
    try:
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(final_html)
        count += 1
    except Exception as e:
        print(f"写入文件失败 {player_name}: {e}")

print(f"所有网页已生成完毕，共生成 {count} 个文件，保存在 {output_dir}")