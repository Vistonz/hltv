import re 
import os 
from openpyxl import Workbook
import undetected_chromedriver as uc
import time


wb = Workbook()
ws = wb.active
driver = uc.Chrome(version_main=9) # 打开网页 

"""
以下为初始数据区，需要定时更改

"""
webfront="https://www.hltv.org/stats/teams"#默认头，无需更改
#赛事筛选，在hltv筛选器中筛选后复制？之后的文字
eventfilter="?event=8914"
keyword = ">" #用于清除rating和name之前的一些多余字符
#用于填写表格的第一行
minMapCountfilter="&minMapCount=0" # 图池数筛选器，更改数字使用
file_path = os.path.join("C:\\Users\\10725\\Desktop\\hltv\\hltv team", "teamstat.xlsx") #表格文件保存路径，根据需要更改

"""
初始数据区 over

"""

# 普通rating，图池
driver.get(webfront+"/ftu"+eventfilter+minMapCountfilter) 
time.sleep(25.3547) #可加可不加，加了提前点不需要rookie爬的会快一些
content = driver.page_source 
Name = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
count = len(Name) / 4
Mapcount = re.findall('"statsDetail gtSmartphone-only">(.*?)</td>',content)
statitem =  re.findall('"center (.*?)</td>',content)
Roundwin = []
OpK = []
MultiK  = []
win5v4 = []
win4v5 = []
Traded = []
HeADR = []
FlashAssist = []
#名字和rating的数据清理
tempzz = 0
while tempzz < count:
    Name[tempzz]=Name[tempzz].split(keyword, 1)[-1].strip()
    Roundwin.append(statitem[tempzz*8].split(keyword, 1)[-1].strip())
    OpK.append(statitem[tempzz*8+1].split(keyword, 1)[-1].strip())
    MultiK.append(statitem[tempzz*8+2].split(keyword, 1)[-1].strip())
    win5v4.append(statitem[tempzz*8+3].split(keyword, 1)[-1].strip())
    win4v5.append(statitem[tempzz*8+4].split(keyword, 1)[-1].strip())
    Traded.append(statitem[tempzz*8+5].split(keyword, 1)[-1].strip())
    HeADR.append(statitem[tempzz*8+6].split(keyword, 1)[-1].strip())
    FlashAssist.append(statitem[tempzz*8+7].split(keyword, 1)[-1].strip())
    tempzz = tempzz + 1

#CT
driver.get(webfront+"/ftu"+eventfilter+"&side=COUNTER_TERRORIST"+minMapCountfilter) 
content = driver.page_source
CTName = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
statitem =  re.findall('"center (.*?)</td>',content)
CTRoundwin = []
CTOpK = []
CTMultiK  = []
CTwin5v4 = []
CTwin4v5 = []
CTTraded = []
CTHeADR = []
CTFlashAssist = []
#名字和rating的数据清理
tempzz = 0
while tempzz < count:
    CTName[tempzz]=Name[tempzz].split(keyword, 1)[-1].strip()
    CTRoundwin.append(statitem[tempzz*8].split(keyword, 1)[-1].strip())
    CTOpK.append(statitem[tempzz*8+1].split(keyword, 1)[-1].strip())
    CTMultiK.append(statitem[tempzz*8+2].split(keyword, 1)[-1].strip())
    CTwin5v4.append(statitem[tempzz*8+3].split(keyword, 1)[-1].strip())
    CTwin4v5.append(statitem[tempzz*8+4].split(keyword, 1)[-1].strip())
    CTTraded.append(statitem[tempzz*8+5].split(keyword, 1)[-1].strip())
    CTHeADR.append(statitem[tempzz*8+6].split(keyword, 1)[-1].strip())
    CTFlashAssist.append(statitem[tempzz*8+7].split(keyword, 1)[-1].strip())
    tempzz = tempzz + 1

#T
driver.get(webfront+"/ftu"+eventfilter+"&side=TERRORIST"+minMapCountfilter) 
content = driver.page_source
TName = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
statitem =  re.findall('"center (.*?)</td>',content)
TRoundwin = []
TOpK = []
TMultiK  = []
Twin5v4 = []
Twin4v5 = []
TTraded = []
THeADR = []
TFlashAssist = []
#名字和rating的数据清理
tempzz = 0
while tempzz < count:
    TName[tempzz]=Name[tempzz].split(keyword, 1)[-1].strip()
    TRoundwin.append(statitem[tempzz*8].split(keyword, 1)[-1].strip())
    TOpK.append(statitem[tempzz*8+1].split(keyword, 1)[-1].strip())
    TMultiK.append(statitem[tempzz*8+2].split(keyword, 1)[-1].strip())
    Twin5v4.append(statitem[tempzz*8+3].split(keyword, 1)[-1].strip())
    Twin4v5.append(statitem[tempzz*8+4].split(keyword, 1)[-1].strip())
    TTraded.append(statitem[tempzz*8+5].split(keyword, 1)[-1].strip())
    THeADR.append(statitem[tempzz*8+6].split(keyword, 1)[-1].strip())
    TFlashAssist.append(statitem[tempzz*8+7].split(keyword, 1)[-1].strip())
    tempzz = tempzz + 1

#pistolround
driver.get(webfront+"/pistols"+eventfilter+minMapCountfilter)
content = driver.page_source
PistolName = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
count = len(PistolName) 
statitem = re.findall('"center (.*?)</td>',content)
Pistolroundwin = []
WinAfterPistolwin = []
WinAfterPistolLose = []
tempzz = 0
while tempzz < count:
    PistolName[tempzz]=Name[tempzz].split(keyword, 1)[-1].strip()
    Pistolroundwin.append(statitem[tempzz*4+1].split(keyword, 1)[-1].strip())
    WinAfterPistolwin.append(statitem[tempzz*4+2].split(keyword, 1)[-1].strip())
    WinAfterPistolLose.append(statitem[tempzz*4+3].split(keyword, 1)[-1].strip())
    tempzz = tempzz + 1

driver.get(webfront+"/pistols"+eventfilter+"&side=COUNTER_TERRORIST"+minMapCountfilter) 
content = driver.page_source
CTPistolName = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
statitem = re.findall('"center (.*?)</td>',content)
CTPistolroundwin = []
CTWinAfterPistolwin = []
CTWinAfterPistolLose = []
tempzz = 0
while tempzz < count:
    CTPistolName[tempzz]=Name[tempzz].split(keyword, 1)[-1].strip()
    CTPistolroundwin.append(statitem[tempzz*4+1].split(keyword, 1)[-1].strip())
    CTWinAfterPistolwin.append(statitem[tempzz*4+2].split(keyword, 1)[-1].strip())
    CTWinAfterPistolLose.append(statitem[tempzz*4+3].split(keyword, 1)[-1].strip())
    tempzz = tempzz + 1

driver.get(webfront+"/pistols"+eventfilter+"&side=TERRORIST"+minMapCountfilter) 
content = driver.page_source
TPistolName = re.findall('data-tooltip-id="uniqueTooltipId-(.*?)</a></td>',content)
statitem = re.findall('"center (.*?)</td>',content)
TPistolroundwin = []
TWinAfterPistolwin = []
TWinAfterPistolLose = []
tempzz = 0
while tempzz < count:
    TPistolName[tempzz]=Name[tempzz].split(keyword, 1)[-1].strip()
    TPistolroundwin.append(statitem[tempzz*4+1].split(keyword, 1)[-1].strip())
    TWinAfterPistolwin.append(statitem[tempzz*4+2].split(keyword, 1)[-1].strip())
    TWinAfterPistolLose.append(statitem[tempzz*4+3].split(keyword, 1)[-1].strip())
    tempzz = tempzz + 1

tempzz = 0
while tempzz<count:
    row = []
    row.append(Name[tempzz])
    row.append(Mapcount[tempzz])
    row.append(Roundwin[tempzz])
    row.append(OpK[tempzz])
    row.append(MultiK[tempzz])
    row.append(win5v4[tempzz])
    row.append(win4v5[tempzz])
    row.append(Traded[tempzz])
    row.append(HeADR[tempzz])
    row.append(FlashAssist[tempzz])
    row.append(Pistolroundwin[tempzz])
    row.append(WinAfterPistolwin[tempzz])
    row.append(WinAfterPistolLose[tempzz])
    row.append(CTRoundwin[tempzz])
    row.append(CTOpK[tempzz])
    row.append(CTMultiK[tempzz])
    row.append(CTwin5v4[tempzz])
    row.append(CTwin4v5[tempzz])
    row.append(CTTraded[tempzz])
    row.append(CTHeADR[tempzz])
    row.append(CTFlashAssist[tempzz])
    row.append(CTPistolroundwin[tempzz])
    row.append(CTWinAfterPistolwin[tempzz])
    row.append(CTWinAfterPistolLose[tempzz])
    row.append(TRoundwin[tempzz])
    row.append(TOpK[tempzz])
    row.append(TMultiK[tempzz])
    row.append(Twin5v4[tempzz])
    row.append(Twin4v5[tempzz])
    row.append(TTraded[tempzz])
    row.append(THeADR[tempzz])
    row.append(TFlashAssist[tempzz])
    row.append(TPistolroundwin[tempzz])
    row.append(TWinAfterPistolwin[tempzz])
    row.append(TWinAfterPistolLose[tempzz])
    print(row) #用于测试
    ws.append(row) #在表格中打印
    tempzz += 1
#保存表格
wb.save(file_path)
# 关闭浏览器 
driver.close()            
driver.quit() 