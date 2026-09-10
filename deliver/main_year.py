# -*- coding: utf-8 -*-
"""年度榜单爬虫 —— exe 入口脚本。

职责：
  1. 让 Windows 黑窗正常显示中文；
  2. 找到 exe 旁边的“配置_year.ini”，没有则用内置模板生成一份；
  3. 把配置翻译成 hltvnew.run_yearly_scrape 需要的参数并调用；
  4. 任何错误都翻译成面向零基础用户的中文提示，最后暂停等待回车。

注意：抓取/计算逻辑全部在 hltvnew.py 里，本文件不改动它任何口径。
"""

import os
import sys

# 确保能 import 同目录的模块（源码运行时 / PyInstaller 收集时都有效）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hltvnew as core            # noqa: E402  核心爬虫（原封复制，未改动）
import shared_lib as sl           # noqa: E402  共享工具

# ---- 与源脚本“初始数据区”锁定的常量（保持不变，勿改）-----------------
WEBFRONT = "https://www.hltv.org/stats/players"   # 统计页 URL 前缀
KEYWORD = ">"                                     # 清洗 name/rating 的分隔符
CONFIG_NAME = "配置_year.ini"
OUT_DEFAULT_NAME = "rating2026.xlsx"
DEFAULT_MIN_MAPS = 65          # 源脚本默认 &minMapCount=65
DEFAULT_MIN_RATING = 1.04      # 源脚本默认 minrating
# ---- /常量区 -----------------------------------------------------------


def build_kwargs(parser):
    """把 ConfigParser 里的配置翻译成核心函数所需的关键字参数。

    键名与 hltvnew.run_yearly_scrape 的形参一一对应，可放心 **kwargs 调用。
    """
    base = sl.app_dir()
    min_maps = sl.get_int(parser, "常用设置", "minMapCount", default=DEFAULT_MIN_MAPS, label="最少图数")
    min_rating = sl.get_float(parser, "常用设置", "minrating", default=DEFAULT_MIN_RATING, label="最低rating")
    chrome_version = sl.get_optional_int(parser, "常用设置", "chrome_version", label="Chrome主版本")
    out_dir = sl.get_raw(parser, "常用设置", "output_dir")
    out_name = sl.get_raw(parser, "常用设置", "output_name", default=OUT_DEFAULT_NAME, label="输出文件名")
    file_path = sl.resolve_output_path(base, out_dir, out_name)

    # 五条赛事口径串：缺任何一条都直接报中文错（它们是“高级/口径”内容）
    def need(key):
        value = sl.get_raw(parser, "赛事口径设置", key, label=key)
        if not value:
            raise sl.FriendlyError(
                f"配置里缺少【{key}】。请用记事本打开 {CONFIG_NAME}，\n"
                f"在 [赛事口径设置] 一节把它补上（原样复制回来即可）。"
            )
        return value

    kwargs = dict(
        webfront=WEBFRONT,
        eventfilter=need("eventfilter"),
        bigeventfilter=need("bigeventfilter"),
        eliteeventfilter=need("eliteeventfilter"),
        supereliteeventfilter=need("supereliteeventfilter"),
        arenafilter=need("arenafilter"),
        keyword=KEYWORD,
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
            print("请先用【记事本】打开它按需修改（至少确认要抓哪些赛事），保存后再次运行本程序。")
            sl.pause()
            return

        parser = sl.load_ini(config_path)
        kwargs = build_kwargs(parser)

        print("=" * 56)
        print("年度榜单爬虫 开始运行")
        print(f"  Chrome版本：{kwargs['chrome_version'] if kwargs['chrome_version'] else '自动探测'}")
        print(f"  最少图数  ：{kwargs['minMapCountfilter']}")
        print(f"  最低rating：{kwargs['minrating']}")
        print(f"  输出文件  ：{kwargs['file_path']}")
        print("=" * 56)
        print("正在抓取，期间会弹出 Chrome 窗口，请不要关闭，也不要手动操作它。")
        print("每个选手要开好几个页面，整体需要较长时间，请耐心等待……\n")

        core.run_yearly_scrape(**kwargs)

        print("\n✅ 全部完成！表格已保存到：")
        print("   " + kwargs["file_path"])
        print("打开该 Excel 文件即可查看结果。")
    except Exception as exc:      # noqa: BLE001 —— 给零基础用户兜底提示
        sl.show_error(exc)
    finally:
        sl.pause()


if __name__ == "__main__":
    main()
