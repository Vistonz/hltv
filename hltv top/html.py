import pandas as pd
import os

# ================= 配置区域 =================
# 1. 文件路径配置
# grade_file_path: 选手各项数据的主表格
# award_file_path: 荣誉奖项数据 (MVP, EVP, VP)
# output_dir: 生成的 HTML 文件存放的根目录
grade_file_path = r'/home/hongbin/Desktop/hltv/hltv top/2026 S1/grade.xlsx'
award_file_path = r'/home/hongbin/Desktop/hltv/hltv top/2026 S1/2026 EVP.xlsx'
output_dir = r'/home/hongbin/Desktop/hltv/hltv top/2026 S1'

# 2. 赛事名称映射 (英文名 -> 中文显示名)
# 脚本会优先尝试在此映射中寻找中文名，找不到则使用原名
event_mapping = {
    "BLAST Bounty 2026 Season 1 Finals": "BLAST赏金赛S1",
    "IEM Krakow 2026": "IEM卡托维兹",
    "PGL Cluj-Napoca 2026": "PGL克卢日纳波卡",
    "EPL S23 Finals": "EPL S23",
    "BLAST Open Rotterdam 2026": "BLAST鹿特丹公开赛",
    "PGL Bucharest 2026": "PGL布加勒斯特",
    "IEM Rio 2026": "IEM里约",
    "BLAST Rivals 2026 Season 1": "BLAST对抗赛S1",
    "PGL Astana 2026": "PGL阿斯塔纳",
    "IEM Atlanta 2026": "IEM亚特兰大",
    "CS Asia Championships 2026": "CAC",
    "IEM Cologne Major 2026": "IEM科隆Major",
}

# 3. 赛事图标与链接配置
tournament_logos = {
    "BLAST赏金赛S1": "https://img-cdn.hltv.org/eventlogo/CJvqOkI-PrW8BhN2jleFfc.png?ixlib=java-2.1.0&w=200&s=b8364c33cc9433b38422f16f8cfadd8e",
    "IEM克拉科夫": "https://img-cdn.hltv.org/eventlogo/nYADQoBBHeOXRjBW1kFOra.png?ixlib=java-2.1.0&w=200&s=9951330163ee8e7abf56775d5ee517e3",
    "PGL克卢日纳波卡": "https://img-cdn.hltv.org/eventlogo/6zk9tRgjzb_pBLqBKiniwE.png?ixlib=java-2.1.0&w=100&s=85308148d750f5ead3889bc653f29f06",
    "EPL S23": "https://img-cdn.hltv.org/eventlogo/PhVPy7kXO_J_nfTng7a87h.png?ixlib=java-2.1.0&w=100&s=6760b0a699faca61ae1b35b33acbf7e7",
    "BLAST鹿特丹公开赛": "https://img-cdn.hltv.org/eventlogo/8k86fLI5ZsXieCf_Bo3p4w.png?ixlib=java-2.1.0&w=100&s=9c5b86297677ee1e5f4ea5676c060f2b",
    "PGL布加勒斯特": "https://img-cdn.hltv.org/eventlogo/N50M3-80lth-pNJeYJOUSQ.png?ixlib=java-2.1.0&w=200&s=cb383c73468493373c781ecad3256c89",
    "IEM里约": "https://img-cdn.hltv.org/eventlogo/nYADQoBBHeOXRjBW1kFOra.png?ixlib=java-2.1.0&w=200&s=9951330163ee8e7abf56775d5ee517e3",
    "BLAST对抗赛S1": "https://img-cdn.hltv.org/eventlogo/pOBDGt1pvBDx2B2Fe6htMp.png?ixlib=java-2.1.0&w=200&s=897d7d72194ddbb26dbbeb8e1e8a3151",
    "PGL阿斯塔纳": "https://img-cdn.hltv.org/eventlogo/IOejg3Hnz60k38JsoCvMXq.png?ixlib=java-2.1.0&w=200&s=568252360f7f6a7ea88d161e1a5d1e31",
    "IEM亚特兰大": "https://img-cdn.hltv.org/eventlogo/nYADQoBBHeOXRjBW1kFOra.png?ixlib=java-2.1.0&w=200&s=9951330163ee8e7abf56775d5ee517e3",
    "CAC": "https://img-cdn.hltv.org/eventlogo/8edBsgkSjlPx71QkYJJPwE.png?ixlib=java-2.1.0&w=200&s=94165d7390618b43c64bafb1dd4526be",
    "IEM科隆Major": "https://img-cdn.hltv.org/eventlogo/2mt5dKGFBdIcxv37gayq1X.png?ixlib=java-2.1.0&w=200&s=316bec1eb89e1172ce5cb7eb8733c71f",
}

tournament_links = {
    "BLAST赏金赛S1": "https://www.hltv.org/events/8246/blast-bounty-2026-season-1-finals",
    "IEM克拉科夫": "https://www.hltv.org/events/8240/iem-krakw-2026",
    "PGL克卢日纳波卡": "https://www.hltv.org/events/8047/pgl-cluj-napoca-2026",
    "EPL S23": "https://www.hltv.org/events/8413/esl-pro-league-season-23-finals",
    "BLAST鹿特丹公开赛": "https://www.hltv.org/events/8248/blast-open-rotterdam-2026",
    "PGL布加勒斯特": "https://www.hltv.org/events/8048/pgl-bucharest-2026",
    "IEM里约": "https://www.hltv.org/events/8242/iem-rio-2026",
    "BLAST对抗赛S1": "https://www.hltv.org/events/8250/blast-rivals-2026-season-1",
    "PGL阿斯塔纳": "https://www.hltv.org/events/8049/pgl-astana-2026",
    "IEM亚特兰大": "https://www.hltv.org/events/8243/iem-atlanta-2026",
    "CAC": "https://www.hltv.org/events/8263/cs-asia-championships-2026",
    "IEM科隆Major": "https://www.hltv.org/events/8301/iem-cologne-major-2026",
}

# 4. 战队图标配置 (根据战队名称获取 SVG/PNG 链接)
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

# 5. 评分阈值配置 (用于在网页中标记 优秀/较差 数据)
avg_highvalues = {
    "adr": 75, "kpr": 0.70, "dpr": 0.70, "rs": 1.0,
    "kast": 75, "rating": 1.04, "rank_change": 0.04,
}
avg_lowvalues = {
    "adr": 69, "kpr": 0.62, "dpr": 0.62, "rs": -0.7,
    "kast": 69, "rating": 0.96, "rank_change": -0.04,
}

# 定义排名转换规则 (例如 1 -> 1st)
def rank_to_text(rank):
    try:
        if rank == 1: return "1st"
        elif rank == 2: return "2nd"
        elif rank == 3: return "3rd"
        elif rank in [4, 5]: return f"{rank}th"
        return str(rank)
    except:
        return str(rank)


# ================= HTML 模板定义 =================
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
                        <div class="newsdsl-tournament-stat-widget-stat-info">2026年正赛数据</div>
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


def generate_all_player_tournament_sheets(
    grade_file_path=grade_file_path,
    award_file_path=award_file_path,
    output_dir=output_dir,
    event_mapping=event_mapping,
    tournament_logos=tournament_logos,
    tournament_links=tournament_links,
    team_logos=team_logos,
    avg_highvalues=avg_highvalues,
    avg_lowvalues=avg_lowvalues,
):
    """根据 grade.xlsx + EVP.xlsx 生成每位选手的 HTML 数据报告页.

    参数均可传入覆盖 (默认值 = 脚本内硬编码配置, 行为不变):
      grade_file_path  选手各项数据的主表格
      award_file_path  荣誉奖项数据 (MVP, EVP, VP)
      output_dir       生成的 HTML 文件存放的根目录
      event_mapping    赛事英文名 -> 中文显示名 映射
      tournament_logos / tournament_links  赛事图标与链接
      team_logos       战队图标配置
      avg_highvalues / avg_lowvalues  评分高/低阈值
    """
    # ================= 初始化输出目录 =================
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    html_output_dir = os.path.join(output_dir, 'html')
    if not os.path.exists(html_output_dir):
        os.makedirs(html_output_dir)

    # ================= 1. 读取主数据 (Stats) =================
    print(">>> 正在读取 Stats 数据...")

    try:
        df = pd.read_excel(grade_file_path)
        print(f"成功读取主数据: {grade_file_path}")
    except Exception as e:
        print(f"读取 grade.xlsx 失败: {e}")
        return

    # ================= 2. 读取并处理荣誉数据 (Awards) =================
    print(">>> 正在读取 Awards 数据...")

    player_awards_map = {}
    try:
        # 从 2026 EVP.xlsx 的 "ALL the VPs" 表中读取荣誉数据
        df_awards = pd.read_excel(award_file_path, sheet_name='ALL the VPs')
        print(f"成功读取荣誉文件，共 {len(df_awards)} 行。")

        # --- 识别关键列名 (支持多种命名方式) ---
        col_map = {}
        df_awards.columns = [str(c).strip() for c in df_awards.columns]
        for col in df_awards.columns:
            c_clean = str(col).strip().lower()
            if 'id' in c_clean or 'player' in c_clean or '选手名' in c_clean:
                col_map['ID'] = col
            elif 'tourn' in c_clean or 'event' in c_clean or '赛事' in c_clean:
                col_map['Tournament'] = col
            elif 'award' in c_clean or '荣誉' in c_clean:
                col_map['Award'] = col

        # 检查是否找齐了必要的列
        if 'Tournament' not in col_map or 'Award' not in col_map or 'ID' not in col_map:
            print(f"错误: 无法识别荣誉文件表头。当前列名: {list(df_awards.columns)}")
        else:
            match_count = 0
            for _, row in df_awards.iterrows():
                try:
                    p_name = str(row[col_map['ID']]).strip()
                    # 赛事名称 (可能是英文或已经翻译成中文)
                    t_raw = str(row[col_map['Tournament']]).strip().replace('"', '')
                    award = str(row[col_map['Award']]).strip()

                    if not award or award.lower() == 'nan':
                        continue

                    # 尝试通过 mapping 转换为中文名，如果找不到则保留原样
                    t_chn = event_mapping.get(t_raw, t_raw)

                    # 建立映射关系: (选手, 赛事) -> 荣誉
                    player_awards_map[(p_name, t_chn)] = award
                    match_count += 1
                except Exception:
                    continue
            print(f"荣誉数据处理完毕，建立 {match_count} 条映射关系。")

    except Exception as e:
        print(f"读取荣誉文件严重失败: {e}")

    # ================= 3. 主逻辑：生成选手 HTML =================

    try:
        unique_players = df['Player'].unique()
        print(f"检测到 {len(unique_players)} 位选手，开始生成HTML...")
    except KeyError:
        print("错误：grade文件中没有找到 'Player' 列。请检查文件格式。")
        return

    count = 0
    for player_name in unique_players:
        filtered_df = df[df['Player'] == player_name]
        if filtered_df.empty:
            continue

        # 获取基本信息
        player_country = "Unknown"
        player_flag_url = ""
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

        html_rows = []
        html_head_filled = html_head1_template.format(
            player_name=player_name,
            player_name1=player_name,
            player_country=player_country,
            player_flag_url=player_flag_url
        )

        for index, row in filtered_df.iterrows():
            try:
                tournament_name = str(row.get('Event_ID', "")).strip()
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

                def assign_class(value, high, low, inverse=False):
                    try:
                        val = float(value)
                        if not inverse:
                            if val > high: return "won"
                            elif val < low: return "lost"
                        else:
                            if val > high: return "lost"
                            elif val < low: return "won"
                    except:
                        pass
                    return ""

                adr_class = assign_class(adr, avg_highvalues['adr'], avg_lowvalues['adr'])
                kpr_class = assign_class(kpr, avg_highvalues['kpr'], avg_lowvalues['kpr'])
                dpr_class = assign_class(dpr, avg_highvalues['dpr'], avg_lowvalues['dpr'], inverse=True)
                rs_class = assign_class(rs, avg_highvalues['rs'], avg_lowvalues['rs'])
                kast_class = assign_class(kast, avg_highvalues['kast'], avg_lowvalues['kast'])
                rating_class = assign_class(rating, avg_highvalues['rating'], avg_lowvalues['rating'])
                rank_change_class = assign_class(rank_change, avg_highvalues['rank_change'], avg_lowvalues['rank_change'])

                try:
                    rank_change_str = f"{(float(rank_change))*100:.0f}%"
                    kast_str = f"{float(kast):.1f}%"
                    rating_str = f"{float(rating):.2f}"
                    kpr_str = f"{float(kpr):.2f}"
                    dpr_str = f"{float(dpr):.2f}"
                    rs_str = (f"+{float(rs):.2f}" if float(rs) > 0 else f"{float(rs):.2f}")
                    adr_str = f"{float(adr):.1f}"
                except:
                    rank_change_str, kast_str, rating_str, kpr_str, dpr_str, rs_str, adr_str = map(str, [rank_change, kast, rating, kpr, dpr, rs, adr])

                t_logo = tournament_logos.get(tournament_name, "")
                t_link = tournament_links.get(tournament_name, "")
                m_team_logo = team_logos.get(team_name, "")

                award_text = player_awards_map.get((str(player_name).strip(), str(tournament_name).strip()), "")

                html_row = html_template.format(
                    tournament_name=tournament_name,
                    tournament_link=t_link,
                    tournament_logo=t_logo,
                    team_name=team_name,
                    team_logo=m_team_logo,
                    team_rank=team_rank,
                    rating=f'<span class="{rating_class}">{rating_str}</span>',
                    rank_in_team=rank_in_team,
                    rank_change=f'<span class="{rank_change_class}">{rank_change_str}</span>',
                    adr=f'<span class="{adr_class}">{adr_str}</span>',
                    kpr=f'<span class="{kpr_class}">{kpr_str}</span>',
                    dpr=f'<span class="{dpr_class}">{dpr_str}</span>',
                    rs=f'<span class="{rs_class}">{rs_str}%</span>',
                    kast=f'<span class="{kast_class}">{kast_str}</span>',
                    award=award_text
                )
                html_rows.append(html_row)
            except Exception as e_row:
                print(f"处理行数据时出错: {e_row}")
                continue

        final_html = html_head_filled + "\n".join(html_rows) + html_tail_str
        safe_player_name = str(player_name).replace('/', '_').replace('\\', '_')
        output_html_path = os.path.join(html_output_dir, f'{safe_player_name}_tournament_sheet.html')
        try:
            with open(output_html_path, 'w', encoding='utf-8') as f:
                f.write(final_html)
            count += 1
        except Exception as e:
            print(f"写入文件失败 {player_name}: {e}")

    print(f"所有网页已生成完毕，共生成 {count} 个文件，保存在 {html_output_dir}")


if __name__ == "__main__":
    generate_all_player_tournament_sheets()
