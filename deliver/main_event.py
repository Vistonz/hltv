# -*- coding: utf-8 -*-
"""单赛事爬虫 —— exe 入口脚本。

职责：
  1. 让 Windows 黑窗正常显示中文；
  2. 找到 exe 旁边的“配置_event.ini”，没有则用内置模板生成一份；
  3. 把配置翻译成 hltvsingleevent.scrape_single_event 需要的参数并调用；
  4. 任何错误都翻译成面向零基础用户的中文提示，最后暂停等待回车。

注意：抓取/计算逻辑全部在 hltvsingleevent.py 里，本文件不改动它任何口径。
"""

import os
import sys

# 确保能 import 同目录的模块（源码运行时 / PyInstaller 收集时都有效）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hltvsingleevent as core    # noqa: E402  核心爬虫（原封复制，未改动）
import shared_lib as sl           # noqa: E402  共享工具

# ---- 与源脚本“初始数据区”锁定的常量（保持不变，勿改）-----------------
WEBFRONT = "https://www.hltv.org/stats/players"   # 统计页 URL 前缀
KEYWORD = ">"                                     # 清洗 name/rating 的分隔符
CONFIG_NAME = "配置_event.ini"
OUT_DEFAULT_NAME = "rating_group.xlsx"
DEFAULT_MIN_MAPS = 0          # 源脚本默认 &minMapCount=0
DEFAULT_MIN_RATING = 0.0      # 源脚本默认 minrating
# ---- /常量区 -----------------------------------------------------------


def build_kwargs(parser):
    """把 ConfigParser 里的配置翻译成核心函数所需的关键字参数。

    键名与 hltvsingleevent.scrape_single_event 的形参一一对应。
    """
    base = sl.app_dir()
    min_maps = sl.get_int(parser, "常用设置", "minMapCount", default=DEFAULT_MIN_MAPS, label="最少图数")
    min_rating = sl.get_float(parser, "常用设置", "minrating", default=DEFAULT_MIN_RATING, label="最低rating")
    chrome_version = sl.get_optional_int(parser, "常用设置", "chrome_version", label="Chrome主版本")
    out_dir = sl.get_raw(parser, "常用设置", "output_dir")
    out_name = sl.get_raw(parser, "常用设置", "output_name", default=OUT_DEFAULT_NAME, label="输出文件名")
    file_path = sl.resolve_output_path(base, out_dir, out_name)

    eventfilter = sl.get_raw(parser, "常用设置", "eventfilter", label="赛事筛选")
    if not eventfilter:
        raise sl.FriendlyError(
            f"配置里没填【赛事筛选】。请用记事本打开 {CONFIG_NAME}，\n"
            f"把浏览器地址栏里 “?event=……” 那段（含问号）复制到 eventfilter 那一行。"
        )

    stagedate_raw = sl.get_raw(parser, "高级设置", "stagedate", label="赛事阶段stagedate")
    stagedate = sl.parse_stagedate(stagedate_raw)

    kwargs = dict(
        webfront=WEBFRONT,
        eventfilter=eventfilter,
        keyword=KEYWORD,
        stagedate=stagedate,
        minMapCountfilter=f"&minMapCount={min_maps}",
        minrating=min_rating,
        file_path=file_path,
        chrome_version=chrome_version,
    )
    return kwargs


def main():
    sl.setup_console()
    try:
        config_path, created = sl.find_or_materialize_config(CONFIG_NAME)
        if created:
            print(f"第一次运行：已在 exe 旁边生成配置文件 {CONFIG_NAME}。")
            print("请先用【记事本】打开它，填好想抓的赛事后保存，再次运行本程序。")
            sl.pause()
            return

        parser = sl.load_ini(config_path)
        kwargs = build_kwargs(parser)

        print("=" * 56)
        print("单赛事爬虫 开始运行")
        print(f"  赛事筛选  ：{kwargs['eventfilter']}")
        print(f"  赛事阶段数：{len(kwargs['stagedate'])} 组")
        print(f"  Chrome版本：{kwargs['chrome_version'] if kwargs['chrome_version'] else '自动探测'}")
        print(f"  输出文件  ：{kwargs['file_path']}")
        print("=" * 56)
        print("正在抓取，期间会弹出 Chrome 窗口并逐位选手翻页，请勿手动操作浏览器。")
        print("单赛事包含大量选手，耗时较长，请耐心等待……\n")

        core.scrape_single_event(**kwargs)

        print("\n✅ 全部完成！表格已保存到：")
        print("   " + kwargs["file_path"])
        print("打开该 Excel 文件即可查看结果。")
    except Exception as exc:      # noqa: BLE001 —— 给零基础用户兜底提示
        sl.show_error(exc)
    finally:
        sl.pause()


if __name__ == "__main__":
    main()
