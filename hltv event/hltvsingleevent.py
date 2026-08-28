import re
import os
from openpyxl import Workbook
import undetected_chromedriver as uc
import time
"""
以下为初始数据区，需要定时更改
"""
webfront="https://www.hltv.org/stats/players"#默认头，无需更改
#赛事筛选，在hltv筛选器中筛选后复制？之后的文字
eventfilter="?event=8914"
keyword = ">" #用于清除rating和name之前的一些多余字符
stagedate = []
stagedate.append([16,5,19,5,2,9999])
stagedate.append([99,99,99,99,99,9999]) #用于表尾判断预留

minMapCountfilter="&minMapCount=0" # 图池数筛选器，更改数字使用
minrating = 0 #大于此数的选手rating纳入统计

file_path = os.path.join(f"/home/hongbin/Desktop/hltv/hltv event", "rating_group.xlsx") #表格文件保存路径，根据需要更改
#用于填写表格的第一行
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#用于填写表格的第一行

description = ["选手ID","图池数","rating","rounds","CTrating","Trating","首杀尝试","首杀成功","首杀rating","手枪局rating","DPR","KAST","RS","ADR","KPR","DPR_eco","KAST_eco","MULTIKILL_eco","ADR_eco","KPR_eco"]
description.append("KD diff")
description.append("map vs top5")
description.append("rating vs top5")
description.append("map vs top10")
description.append("rating vs top10")
description.append("map vs top20")
description.append("rating vs top20")
description.append("回合首杀数")
description.append("Rounds with a kill")
description.append("ROunds with a multikill")
description.append("3+kill")
description.append("0.85+")
description.append("1.00+")
description.append("1.15+")
description.append("1.30+")
description.append("1.45+")
description.append("clutch win")
description.append("clutch point per round")
description.append("kill per round win")
description.append("elimination round")
description.append("elimination rating")
description.append("adr win")
description.append("win after first kill")
description.append("save per round lose")
description.append("assist kill percentage")
description.append("damage per kill")
description.append("last alive percentage")
description.append("kpr lose")
description.append("adr lose")
description.append("traded_kill")
description.append("traded_death_percentage")
description.append("flash_assist")
description.append("utility_damage")
description.append("firepower")
description.append("entrying")
description.append("trading")
description.append("opening")
description.append("clutching")
description.append("sniping")
description.append("utility")
description.append("HS%")
description.append("singlemapwinrating")
description.append("traded_death")
description.append("save_teammate")
description.append("saved_by_teammate")
description.append("support_round_percent")
description.append("attack_in_round")
description.append("winrate_1v1")
description.append("livetime_perround")
description.append("snipkill_perround")
description.append("snipkill_percent")
description.append("snipkillround_percent")
description.append("utlility_kill_round")
description.append("throw_flash_perround")
description.append("time_opponent_flashed")
description.append("trade_kill_percentage")


"""
初始数据区 over

"""


def scrape_single_event(
    webfront=webfront,
    eventfilter=eventfilter,
    keyword=keyword,
    stagedate=stagedate,
    minMapCountfilter=minMapCountfilter,
    minrating=minrating,
    file_path=file_path,
    chrome_version=149,
):
    """单赛事评分爬虫主入口: 抓选手各页面数据, 按 stagedate 状态机归类赛事, 写 rating_group.xlsx.

    参数均可传入覆盖 (默认值 = 脚本内硬编码配置, 行为不变):
      webfront          统计页 URL 前缀
      eventfilter       赛事筛选字符串, 如 "?event=8914"
      keyword           清洗 name/rating 时去掉的前缀
      stagedate         赛事日期区间状态机 (每项 [起始日,起始月,结束日,结束月,淘汰数,复活数])
      minMapCountfilter 图池数筛选器
      minrating         低于此 rating 的选手停止纳入
      file_path         xlsx 输出路径
      chrome_version    Chrome 主版本号 (原值 149; 本机 Chrome 151 需传 151)
    """
    match = re.search(r"[-+]?\d+\.?\d*|\.\d+", eventfilter)
    event_id = match.group(0)

    wb = Workbook()
    ws = wb.active
    driver = uc.Chrome(version_main=chrome_version) # 打开网页

    ws.append(description) #上传表格的第一行

    # 普通rating，图池
    driver.get(webfront+eventfilter+minMapCountfilter)
    time.sleep(25.6657) #可加可不加，加了提前点不需要rookie爬的会快一些
    content = driver.page_source
    Name1 = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
    Name = []
    Mapcount1 = re.findall('<td class="statsDetail">(.*?)</td>',content)
    Mapcount = []
    Rating = re.findall('class="ratingCol(.*?)</td>',content)
    Id = re.findall('<a href="/stats/players(.*?)" data-tooltip-id="uniqueTooltipId',content)
    Rounds = re.findall('<td class="statsDetail gtSmartphone-only">(.*?)</td>',content)
    Flag = re.findall('class="flag" title="(.*?)">',content)
    #名字和rating的数据清理
    tempzz = 0
    while tempzz*2 < len(Name1):
        Mapcount.append(Mapcount1[tempzz*2])
        Name.append(Name1[tempzz*2].split(keyword, 1)[-1].strip())
        Rating[tempzz]=Rating[tempzz].split(keyword, 1)[-1].strip()
        tempzz = tempzz + 1

    #CT
    time.sleep(0.6657)
    driver.get(webfront+eventfilter+"&side=COUNTER_TERRORIST"+minMapCountfilter)
    content = driver.page_source
    CTname1 = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
    CTrating = re.findall('class="ratingCol(.*?)</td>',content)
    CTflag = re.findall('class="flag" title="(.*?)">',content)
    #T
    time.sleep(0.6657)
    driver.get(webfront+eventfilter+"&side=TERRORIST"+minMapCountfilter)
    content = driver.page_source
    Tname1 = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
    Trating = re.findall('class="ratingCol(.*?)</td>',content)
    Tflag = re.findall('class="flag" title="(.*?)">',content)
    tempzz = 0
    CTname = []
    Tname = []
    #openingkill
    time.sleep(0.6657)
    driver.get(webfront+"/openingkills"+eventfilter+minMapCountfilter)
    content = driver.page_source
    ok = re.findall('class="statsDetail">(.*?)</td>',content)
    Openingkillrating = re.findall('class="ratingCol(.*?)</td>',content)
    Openingkillname1 = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
    Openingkillflag = re.findall('class="flag" title="(.*?)">',content)
    Openingkillname = []
    count=0
    Openingkillattempts=[]
    Openingkillsuccess=[]
    # 筛选数据
    for i in ok:
        if count%4 == 2:
            Openingkillattempts.append(i)
        if count%4 == 3:
            Openingkillsuccess.append(i)
        count+=1

    #手枪局
    time.sleep(0.6657)
    driver.get(webfront+"/pistols"+eventfilter+minMapCountfilter)
    content = driver.page_source
    Pistolname1 = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
    Pistolrating = re.findall('class="ratingCol(.*?)</td>',content)
    Pistolflag = re.findall('class="flag" title="(.*?)">',content)
    Pistolname = []

    while tempzz*2 < len(CTname1):
        CTname.append(CTname1[tempzz*2].split(keyword, 1)[-1].strip())
        Tname.append(Tname1[tempzz*2].split(keyword, 1)[-1].strip())
        Openingkillname.append(Openingkillname1[tempzz].split(keyword, 1)[-1].strip())
        Pistolname.append(Pistolname1[tempzz*2].split(keyword, 1)[-1].strip())
        CTrating[tempzz]=CTrating[tempzz].split(keyword, 1)[-1].strip()
        Trating[tempzz]=Trating[tempzz].split(keyword, 1)[-1].strip()
        Openingkillrating[tempzz]=Openingkillrating[tempzz].split(keyword, 1)[-1].strip()
        Pistolrating[tempzz]=Pistolrating[tempzz].split(keyword, 1)[-1].strip()
        tempzz = tempzz + 1

    #选手个人数据统计和打印
    for name,mapcount,rating,id,rounds,flag in zip(Name,Mapcount,Rating,Id,Rounds,Flag):
        #加入选手姓名，图池数，rating，回合数（用于计算）
        row = [name,mapcount,rating,rounds]
        ratingnum = float(rating)
        if ratingnum <= minrating:
            break
        #上传CTrating
        for name1,rating1,flag1 in zip(CTname,CTrating,CTflag):
            name1=name1.split(keyword, 1)[-1].strip()
            rating1=rating1.split(keyword, 1)[-1].strip()
            if name1 == name and flag1 == flag:
                row.append(rating1)
                break
        #上传Trating
        for name1,rating1,flag1 in zip(Tname,Trating,Tflag):
            name1=name1.split(keyword, 1)[-1].strip()
            rating1=rating1.split(keyword, 1)[-1].strip()
            if name1 == name and flag1 == flag:
                row.append(rating1)
                break
        #上传首杀相关数据（回合首杀在选手个人页面中）
        for openingkillname,openingkillattempts,openingkillsuccess,openingkillrating,openingkillflag in zip(Openingkillname,Openingkillattempts,Openingkillsuccess,Openingkillrating,Openingkillflag):
            openingkillname=openingkillname.split(keyword, 1)[-1].strip()
            openingkillrating=openingkillrating.split(keyword, 1)[-1].strip()
            if openingkillname == name and openingkillflag == flag:
                row.append(openingkillattempts)
                row.append(openingkillsuccess)
                row.append(openingkillrating)
                break
        #上传手枪局rating
        for name1,rating1,flag1 in zip(Pistolname,Pistolrating,Pistolflag):
            name1=name1.split(keyword, 1)[-1].strip()
            rating1=rating1.split(keyword, 1)[-1].strip()
            if name1 == name and flag1 == flag:
                row.append(rating1)
                break
        #网址清理，用于进入选手个人界面
        statsuffix = id.replace('amp;','')
        driver.get(webfront+statsuffix)
        time.sleep(0.6657)
        content = driver.page_source
        #获取选手面板数据，rating已经统计不被需要
        Playerstatform=re.findall('class="summaryStatBreakdownDataValue">(.*?)</div>',content)
        #获取选手面板数据，rating已经统计不被需要
        Playerstatform=re.findall('<div class="player-summary-stat-box-data traditionalData">(.*?)</div>',content)
        DPR = Playerstatform[0]
        row.append(DPR)
        KAST=re.findall('<div class="player-summary-stat-box-data traditionalData">(.*?)<span',content)
        row.append(KAST[0])
        RS = re.findall('<div class="player-summary-stat-box-data">(.*?)<span class="',content)
        row.append(RS[0])
        ADR = Playerstatform[3]
        row.append(ADR)
        KPR = Playerstatform[4]
        row.append(KPR)
        Playerstatform_eco=re.findall('<div class="player-summary-stat-box-data ecoAdjustedData hidden">(.*?)</div>',content)
        DPRE = Playerstatform_eco[0]
        row.append(DPRE)
        KASTE=re.findall('<div class="player-summary-stat-box-data ecoAdjustedData hidden">(.*?)<span',content)
        row.append(KASTE[0])
        MULTIKILL = Playerstatform_eco[2]
        row.append(MULTIKILL)
        ADRE = Playerstatform_eco[3]
        row.append(ADRE)
        KPRE = Playerstatform_eco[4]
        row.append(KPRE)

        kills = re.findall('Total kills</span><span>(.*?)</span></div>',content)
        kills = kills[0]
        deaths = re.findall('Total deaths</span><span>(.*?)</span></div>',content)
        deaths = deaths[0]
        headshot = re.findall('Headshot %</span><span>(.*?)</span></div>',content)
        row.append(int(kills)-int(deaths))
        chartstat = re.findall('<div class="role-stats-data">(.*?)</div>',content)
        charttotalstat = re.findall('"row-stats-section-score">(.*?)<',content)
        #新增数据
        kprw = chartstat[6]
        adrw = chartstat[18]
        assist_kill_percentage = chartstat[51]
        damage_per_kill = chartstat[54]
        winafteropeningkill = chartstat[69]
        last_alive_percentage = chartstat[78]
        saveperroundlose = chartstat[87]
        traded_death_percentage = chartstat[30]
        traded_kill = chartstat[45]
        flash_assist = chartstat[114]
        utility_damage = chartstat[105]
        traded_death = chartstat[27]
        traded_kill_percentage = chartstat[48]
        save_teammate = chartstat[42]
        saved_by_teammate = chartstat[24]
        support_round_percent = chartstat[39]
        attack_in_round = chartstat[72]
        winrate_1v1 = chartstat[81]
        livetime_perround_str = chartstat[84]
        livetime = re.findall("\d+\.?\d*",livetime_perround_str)
        livetime_perround = float(livetime[0])*60.0+float(livetime[1])
        snipkill_perround = chartstat[90]
        snipkill_percent = chartstat[93]
        snipkillround_percent = chartstat[96]
        utlility_kill_round = chartstat[108]
        throw_flash_perround = chartstat[111]
        time_opponent_flashed = chartstat[117]
        traded_kill_percentage = chartstat[48]

        firepower = charttotalstat[0]
        entrying = charttotalstat[3]
        trading = charttotalstat[6]
        opening = charttotalstat[9]
        clutching = charttotalstat[12]
        sniping = charttotalstat[15]
        utility = charttotalstat[18]
        #统计选手对阵top5数据
        VStop5maplist =   re.findall('vs top 5 opponents</div>\n                      <div class="rating-maps">(.*?)</div>',content)
        VStop5map = VStop5maplist[0]
        VStop5map = VStop5map.replace('(','')
        VStop5map = VStop5map.replace(' maps)','')
        row.append(VStop5map)
        VStop5rating = re.findall('<div class="rating-value">(.*?)</div>\n                      <div class="rating-description">vs top 5 opponents',content)
        row.append(VStop5rating[0])
        #统计选手对阵top10数据
        VStop10maplist = re.findall('vs top 10 opponents</div>\n                      <div class="rating-maps">(.*?)</div>',content)
        VStop10map = VStop10maplist[0]
        VStop10map = VStop10map.replace('(','')
        VStop10map = VStop10map.replace(' maps)','')
        row.append(VStop10map)
        VStop10rating = re.findall('<div class="rating-value">(.*?)</div>\n                      <div class="rating-description">vs top 10 opponents',content)
        row.append(VStop10rating[0])
        #统计选手对阵top20数据
        VStop20maplist = re.findall('vs top 20 opponents</div>\n                      <div class="rating-maps">(.*?)</div>',content)
        VStop20map = VStop20maplist[0]
        VStop20map = VStop20map.replace('(','')
        VStop20map = VStop20map.replace(' maps)','')
        row.append(VStop20map)
        VStop20rating = re.findall('<div class="rating-value">(.*?)</div>\n                      <div class="rating-description">vs top 20 opponents',content)
        row.append(VStop20rating[0])

        #进入individual界面，统计首杀数和回合击杀
        time.sleep(0.6657)
        driver.get(webfront+"/individual"+statsuffix)
        content = driver.page_source
        openingkills = re.findall('Total opening kills</span><span>(.*?)</span></div>',content)
        row.append(float(openingkills[0]) / float(rounds))
        round0kill = re.findall('0 kill rounds</span><span>(.*?)</span></div>',content)
        row.append((float(rounds)-float(round0kill[0]))/float(rounds))
        round1kill = re.findall('1 kill rounds</span><span>(.*?)</span></div>',content)
        round2kill = re.findall('2 kill rounds</span><span>(.*?)</span></div>',content)
        round3kill = re.findall('3 kill rounds</span><span>(.*?)</span></div>',content)
        round4kill = re.findall('4 kill rounds</span><span>(.*?)</span></div>',content)
        round5kill = re.findall('5 kill rounds</span><span>(.*?)</span></div>',content)
        row.append((float(rounds)-float(round0kill[0])-float(round1kill[0]))/float(rounds))
        row.append((float(round5kill[0])+float(round4kill[0])+float(round3kill[0]))/float(rounds))


        #进入match界面，统计对局的小局rating,获胜地图rating和回家局rating
        time.sleep(0.6657)
        driver.get(webfront+"/matches"+statsuffix)
        content = driver.page_source

        singlemaprating = re.findall('"none">(.*?)</td>\n                  </tr>',content)
        singlemapround = re.findall(r'</span></a><span> \((.*?)\)</span></div>',content)
        #统计回家局数据
        singlemapoutdate = re.findall('00000">(.*?)</div>',content)#需要提取数字处理
        singlemapoutwin = re.findall('match-(.*?) rating',content)
        singlemapoutvstemp = re.findall('">(.*?)</span></a><span>',content) # 提了两个数据，取奇数个为对阵战队
        singlemapoutround = 0
        singlemapoutrating = 0
        singlemapoutmap = 0
        winround = 0.0
        tempzz7 = 0
        #求失败回合KPR和ADR
        while tempzz7 < len(singlemapround)-1:
            winround += float(singlemapround[tempzz7])
            tempzz7+=2
        kprl = (float(kills)-float(kprw)*winround)/float(float(rounds)-winround)
        adrl = (float(float(ADR)*float(rounds))-float(adrw)*winround)/float(float(rounds)-winround)

        #初始化
        tempzz5 = 0
        singlemapout = []
        singlemapoutdate.reverse()
        singlemapoutwin.reverse()
        singlemapoutvstemp.reverse()
        singlemaprating.reverse()
        singlemapround.reverse()
        #数据集中处理
        for i in singlemaprating:
            singlemapout.append([float(i)])
            date = re.findall("\d+\.?\d*", singlemapoutdate[tempzz5])
            date = list(map(int,date))
            singlemapout[tempzz5].append(date[0])
            singlemapout[tempzz5].append(date[1])
            singlemapout[tempzz5].append(float(singlemapround[2*tempzz5]) + float(singlemapround[2*tempzz5+1]))
            singlemapout[tempzz5].append(singlemapoutvstemp[2*tempzz5])
            singlemapout[tempzz5].append(singlemapoutwin[tempzz5])
            tempzz5 +=1
        tempzz5 = 0
        maplistzz = 0
        while tempzz5 < len(singlemapout):
            out1 = singlemapout[tempzz5]
            date1 = stagedate[maplistzz]
            datenext = stagedate[maplistzz+1]
            if tempzz5 >=len(singlemapout):
                break
            # out[1]: 日期 out[2]: 月份
            #date[0] , date[2]:日期  date[1] date[3]: 月份
            #当前小于最近赛事，此地图不纳入统计
            #当前大于最近赛事区间，找到对应的赛事
            if (out1[2] == date1[3] and out1[1] > date1[2]) or out1[2]>date1[3]:
                while 1:
                    maplistzz += 1
                    if maplistzz >= len(stagedate):
                        break
                    date1 = stagedate[maplistzz]
                    if (out1[2] == date1[3] and out1[1] > date1[2]) or out1[2]>date1[3]:
                        continue
                    else:
                        break
            if (out1[2] == date1[1] and out1[1] < date1[0]) or out1[2]<date1[1]:
                while 1:
                    tempzz5 += 1
                    if tempzz5 >=len(singlemapout):
                        break
                    out1 = singlemapout[tempzz5]
                    if(out1[2] == date1[1] and out1[1] < date1[0]) or out1[2]<date1[1]:
                        continue
                    else:
                        break
            if tempzz5 >=len(singlemapout):
                break
            #找到对应赛事和地图，开始分析 out[0]rating out[3]round out[4]对手 out[5]胜利与否
            #date1[4] 多少败淘汰 date1[5] 赢几把多一条命
            wincount = 0
            losecount = 0
            rating1 = 0
            round1 = 0
            map1 = 0
            losecountforwin = 0
            nextnot = 0
            blasttemp = 0
            while 1:
                if tempzz5 >= len(singlemapout):
                    break
                out1 = singlemapout[tempzz5]
                if ((out1[2] == date1[1] and out1[1] < date1[0]) or out1[2]<date1[1]) or ((out1[2] == date1[3] and out1[1] > date1[2]) or out1[2]>date1[3]):
                    break
                vszz = out1[4] #存储对手
                #此处需要更改
                """
                if (maplistzz ==0 or maplistzz == 25) and wincount == 2 and losecount == 0:
                    blasttemp = 1

                """
                if wincount >= date1[5] and blasttemp == 0:
                    losecountforwin = 1
                while out1[4] == vszz and (not((out1[2] == date1[1] and out1[1] < date1[0]) or out1[2]<date1[1]) and (not((out1[2] == date1[3] and out1[1] > date1[2]) or out1[2]>date1[3]))):
                    if losecount == date1[4] - 1 + losecountforwin:
                        round1 += out1[3]
                        rating1 += out1[0] * out1[3]
                        map1 +=1
                    tempzz5+=1
                    if tempzz5 < len(singlemapout):
                        out1 = singlemapout[tempzz5]
                    else:
                        break
                outtemp = singlemapout[tempzz5-1]
                if outtemp[2]==date1[3] and outtemp[1] ==date1[2]:
                    if wincount+losecount==0 and not (outtemp[1] == 18 and outtemp[2] == 7):
                        tempzz5-=1
                        out1=outtemp
                        rating1 = 0
                        round1 = 0
                        map1 = 0
                        wincount = 0
                        losecount = 0
                        maplistzz+= 1
                        break
                    elif out1[1] == outtemp[1] and out1[2] == outtemp[2] and not(out1[1]==18 and out1[2]==7) and out1[1] == datenext[0] and out1[2] == datenext[1]:
                        singlemapoutrating  += rating1
                        singlemapoutround += round1
                        singlemapoutmap += map1
                        maplistzz +=1
                        wincount = 0
                        losecount = 0
                        rating1 = 0
                        round1 = 0
                        map1 = 0
                        break
                if outtemp[5] == 'won':
                    wincount += 1
                else:
                    losecount += 1
                continue
            singlemapoutrating  += rating1
            singlemapoutround += round1
            singlemapoutmap += map1
        ishere = 0
        #统计获胜地图数据和大于指定数字rating比例
        singlemapwinround = 0
        singlemapwinrating = 0
        ratingabove085 = 0
        ratingabove100 = 0
        ratingabove115 = 0
        ratingabove130 = 0
        ratingabove145 = 0
        tempzz4 = 0
        for i in singlemaprating:
            rating1 = float(i)
            if float(singlemapround[2*tempzz4]) < float(singlemapround[2*tempzz4+1]) :
                totalround = float(singlemapround[2*tempzz4]) + float(singlemapround[2*tempzz4+1])
                singlemapwinround = singlemapwinround + totalround
                singlemapwinrating = singlemapwinrating + (totalround * rating1)
            if rating1 >= 0.85:
                ratingabove085 += 1
            if rating1 >= 1:
                ratingabove100 += 1
            if rating1 >= 1.15:
                ratingabove115 += 1
            if rating1 >= 1.30:
                ratingabove130 += 1
            if rating1 >= 1.45:
                ratingabove145 += 1
            tempzz4 = tempzz4 + 1
        row.append(ratingabove085)
        row.append(ratingabove100)
        row.append(ratingabove115)
        row.append(ratingabove130)
        row.append(ratingabove145)

        #统计选手残局获胜次数
        pattern = r"(/[0-9]+)"
        time.sleep(0.6657)
        driver.get(webfront+"/clutches"+re.sub(pattern,r'\1'+"/1on1",statsuffix,1))
        content = driver.page_source
        clutch1v1win = re.findall('<div class="value">(.*?)</div>',content)
        time.sleep(0.6657)
        driver.get(webfront+"/clutches"+re.sub(pattern,r'\1'+"/1on2",statsuffix,1))
        content = driver.page_source
        clutch1v2win = re.findall('<div class="value">(.*?)</div>',content)
        time.sleep(0.6657)
        driver.get(webfront+"/clutches"+re.sub(pattern,r'\1'+"/1on3",statsuffix,1))
        content = driver.page_source
        clutch1v3win = re.findall('<div class="value">(.*?)</div>',content)
        time.sleep(0.6657)
        driver.get(webfront+"/clutches"+re.sub(pattern,r'\1'+"/1on4",statsuffix,1))
        content = driver.page_source
        clutch1v4win = re.findall('<div class="value">(.*?)</div>',content)
        time.sleep(0.6657)
        driver.get(webfront+"/clutches"+re.sub(pattern,r'\1'+"/1on5",statsuffix,1))
        content = driver.page_source
        clutch1v5win = re.findall('<div class="value">(.*?)</div>',content)
        time.sleep(0.6657)
        if clutch1v5win[0] =="-":
            clutch1v5win[0] = "0"
        if clutch1v4win[0] =="-":
            clutch1v4win[0] = "0"
        if clutch1v3win[0] =="-":
            clutch1v3win[0] = "0"
        if clutch1v2win[0] =="-":
            clutch1v2win[0] = "0"
        if clutch1v1win[0] =="-":
            clutch1v1win[0] = "0"
        row.append(int(clutch1v5win[0])+int(clutch1v4win[0])+int(clutch1v3win[0])+int(clutch1v2win[0])+int(clutch1v1win[0]))
        row.append( (float(clutch1v5win[0])*16.0+float(clutch1v4win[0])*8.0+float(clutch1v3win[0])*4.0+float(clutch1v2win[0])*2.0+float(clutch1v1win[0])) /float(rounds))

        row.append(kprw)
        row.append(singlemapoutround)
        if singlemapoutround != 0:
            row.append(singlemapoutrating/singlemapoutround)
        else:
            row.append("-")
        row.append(adrw)
        row.append(winafteropeningkill)
        row.append(saveperroundlose)
        row.append(assist_kill_percentage)
        row.append(damage_per_kill)
        row.append(last_alive_percentage)
        row.append(kprl)
        row.append(adrl)
        row.append(traded_kill)
        row.append(traded_death_percentage)
        row.append(flash_assist)
        row.append(utility_damage)
        row.append(firepower)
        row.append(entrying)
        row.append(trading)
        row.append(opening)
        row.append(clutching)
        row.append(sniping)
        row.append(utility)
        row.append(headshot[0])
        if float(singlemapwinround) != 0:
            row.append(float(singlemapwinrating)/float(singlemapwinround))
        else:
            row.append("-")
        row.append(traded_death)
        row.append(save_teammate)
        row.append(saved_by_teammate)
        row.append(support_round_percent)
        row.append(attack_in_round)
        row.append(winrate_1v1)
        row.append(livetime_perround)
        row.append(snipkill_perround)
        row.append(snipkill_percent)
        row.append(snipkillround_percent)
        row.append(utlility_kill_round)
        row.append(throw_flash_perround)
        row.append(time_opponent_flashed)
        row.append(traded_kill_percentage)
        print(row) #用于测试
        ws.append(row) #在表格中打印
    #保存表格
    wb.save(file_path)
    # 关闭浏览器
    driver.close()
    driver.quit()


if __name__ == "__main__":
    scrape_single_event()
