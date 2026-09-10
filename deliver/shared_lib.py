# -*- coding: utf-8 -*-
"""deliver 打包工程的共享工具库（纯标准库，无第三方依赖，便于 PyInstaller 收集）。

给三个 exe 入口脚本（main_year.py / main_event.py / main_team.py）共用：
  - 定位 exe/脚本真正所在目录，解决原脚本硬编码的 Linux 绝对路径；
  - Windows 黑窗中文不乱码；
  - 读取/校验 exe 旁的 .ini 配置文件（类型化取值 + 中文报错）；
  - 构建输出 xlsx 的绝对路径（默认 exe 旁自动建"结果"目录）；
  - 配置缺失时从 exe 内置模板自动释放一份；
  - 结束暂停（防双击后窗口闪退）与友好的中文错误输出。
"""

import configparser
import os
import shutil
import sys


class FriendlyError(Exception):
    """带面向"零基础用户"中文说明的配置/环境错误。"""


# ---------------------------------------------------------------------------
# 路径定位
# ---------------------------------------------------------------------------
def app_dir():
    """返回 exe（打包态）或脚本（开发态）真实所在的目录。

    PyInstaller --onefile 打包后 sys.executable 指向 exe 本身而非临时解压目录，
    开发态指向本文件所在目录。程序的一切读写（配置、结果表、断点续爬文件）
    都以此为基础，避免"双击启动时的工作目录不是 exe 目录"这一类坑。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir():
    """PyInstaller 打包后存放内置资源（配置文件模板）的解压目录。

    --onefile 启动时会把 exe 内打包的数据解压到 _MEIPASS；开发态退回 app_dir()。
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return base
    return app_dir()


# ---------------------------------------------------------------------------
# 控制台（Windows 黑窗中文不乱码）
# ---------------------------------------------------------------------------
def setup_console():
    """让 Windows 控制台正确显示中文。

    1. Windows 下先执行 chcp 65001 切到 UTF-8 代码页；
    2. 把 stdout/stderr 重配为 UTF-8，即便平台不支持也不至于抛 UnicodeEncodeError。
    """
    if os.name == "nt":
        try:
            os.system("chcp 65001 >nul")
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 配置文件读取（.ini，utf-8-sig 兼容记事本保存的 BOM）
# ---------------------------------------------------------------------------
def load_ini(path):
    """读取 .ini，返回 ConfigParser；键名大小写原样保留，不做 % 插值。

    不开 inline_comment_prefixes：这样配置值内部的 ';'（如 stagedate 的分隔符）
    不会被误当成行尾注释吞掉。行首的 '#' 或 ';' 仍是注释行。
    """
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # 保留键原本的大小写
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            parser.read_file(fh)
    except OSError as exc:
        raise FriendlyError(f"无法读取配置文件：{path}\n原因：{exc}") from exc
    except configparser.Error as exc:
        raise FriendlyError(f"配置文件格式有误（请用记事本打开检查是否改动坏了）：{path}\n原因：{exc}") from exc
    return parser


def get_raw(parser, section, key, default="", label=""):
    """取字符串值：不存在或留空 -> default；存在 -> 去首尾空格。"""
    if parser.has_option(section, key):
        value = parser.get(section, key).strip()
        return value if value else default
    return default


def get_int(parser, section, key, default=0, label="该项"):
    """取整数，填错给出带字段名的中文提示。"""
    raw = get_raw(parser, section, key, default=None, label=label)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        raise FriendlyError(
            f"配置【{label}】应当填整数，但你填的是：{raw!r}\n"
            f"请用记事本打开配置文件，把 {key} 改回一个整数（或留空用默认值）。"
        ) from None


def get_float(parser, section, key, default=0.0, label="该项"):
    """取小数，填错给出带字段名的中文提示。"""
    raw = get_raw(parser, section, key, default=None, label=label)
    if raw is None:
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        raise FriendlyError(
            f"配置【{label}】应当填数字，但你填的是：{raw!r}\n"
            f"请用记事本打开配置文件，把 {key} 改回一个数字（或留空用默认值）。"
        ) from None


def get_optional_int(parser, section, key, label="该项"):
    """取可选整数：留空/不存在返回 None（表示交给程序自动判断）。"""
    raw = get_raw(parser, section, key, default="", label=label)
    if not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        raise FriendlyError(
            f"配置【{label}】留空即可（程序会自动判断），或填一个整数（Chrome 主版本号）。\n"
            f"你当前填的是：{raw!r}，请修正后重试。"
        ) from None


def parse_stagedate(raw):
    """把 stagedate 字符串解析成 [[int×6], ...]。

    格式：每组 [起始日,起始月,结束日,结束月,淘汰数,复活数]，多组之间用英文分号 ;
    例如：16,5,19,5,2,9999 ; 99,99,99,99,99,9999
    返回空的二维 int 列表；解析失败给中文提示。
    """
    if raw is None or not str(raw).strip():
        raise FriendlyError(
            "配置缺少【赛事阶段 stagedate】。请用记事本打开配置文件，在 [高级设置] 下\n"
            "填写 stagedate = 起始日,起始月,结束日,结束月,淘汰数,复活数 ; 下一组..."
        )
    groups = []
    for item in str(raw).split(";"):
        item = item.strip()
        if not item:
            continue
        fields = [part.strip() for part in item.split(",") if part.strip() != ""]
        if len(fields) != 6:
            raise FriendlyError(
                f"配置【赛事阶段 stagedate】中每组必须恰好是 6 个数字，但你写了：{item!r}\n"
                f"格式应为：起始日,起始月,结束日,结束月,淘汰数,复活数 ；两组之间用分号 ; 分隔"
            )
        try:
            groups.append([int(f) for f in fields])
        except ValueError:
            raise FriendlyError(
                f"配置【赛事阶段 stagedate】里包含了非数字内容：{item!r}\n"
                f"请只填数字和英文逗号。"
            ) from None
    if not groups:
        raise FriendlyError("配置【赛事阶段 stagedate】解析结果为空，请检查是否填写正确。")
    return groups


# ---------------------------------------------------------------------------
# 输出路径
# ---------------------------------------------------------------------------
def resolve_output_path(base_dir, output_dir_cfg, output_name, default_dir="结果"):
    """构造结果 xlsx 的绝对路径，并确保目录存在。

    - output_dir_cfg 留空 -> base_dir/结果（自动创建）
    - 填相对路径   -> 相对 base_dir 解析
    - 填绝对路径   -> 直接使用
    返回绝对路径字符串。
    """
    out_dir = str(output_dir_cfg or "").strip()
    if not out_dir:
        out_dir = os.path.join(base_dir, default_dir)
    elif not os.path.isabs(out_dir):
        out_dir = os.path.join(base_dir, out_dir)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        raise FriendlyError(f"无法创建输出目录：{out_dir}\n原因：{exc}") from exc
    name = str(output_name or "").strip()
    if not name:
        raise FriendlyError("配置缺少【输出文件名】，请检查配置文件。")
    return os.path.join(out_dir, name)


# ---------------------------------------------------------------------------
# 配置文件定位 / 内置模板释放
# ---------------------------------------------------------------------------
def find_or_materialize_config(template_name):
    """返回 exe 旁的配置文件路径；不存在则从 exe 内置模板释放一份并提示用户。

    开发态模板就在同目录，同样适用。返回 (config_path, 是否刚生成)。
    """
    target = os.path.join(app_dir(), template_name)
    if os.path.isfile(target):
        return target, False
    # 尝试从内置模板释放（PyInstaller --add-data 打进 exe；开发态退回同目录）
    src = os.path.join(bundle_dir(), template_name)
    if os.path.isfile(src):
        try:
            shutil.copy2(src, target)
        except OSError:
            raise FriendlyError(
                f"程序想在 exe 旁边生成配置文件 {template_name}，但没有写权限。\n"
                f"请把整个文件夹放到有权限的目录（如桌面、文档）再运行。"
            ) from None
        return target, True
    raise FriendlyError(
        f"找不到配置文件 {template_name}，且程序内置的模板也丢失了。\n"
        f"请重新获取一份完整的程序文件夹（exe 与配置文件要放在一起）。"
    )


# ---------------------------------------------------------------------------
# 交互辅助
# ---------------------------------------------------------------------------
def pause():
    """结束前暂停，防止用户双击运行后窗口瞬间闪退。"""
    try:
        input("\n按【回车】键关闭窗口……")
    except Exception:
        pass


def show_error(exc):
    """把异常输出成对零基础用户友好的中文说明。"""
    print("\n" + "=" * 56)
    print("程序出错了，没能完成抓取。")
    if isinstance(exc, FriendlyError):
        print(str(exc))
    else:
        print(f"错误类型：{type(exc).__name__}")
        print(f"错误内容：{exc}")
        print("\n常见原因（按顺序排查）：")
        print("  1. 没有安装 Google Chrome，或 Chrome 不在默认安装位置 —— 请先安装 Chrome 再试；")
        print("  2. 电脑当前没联网，或无法访问 hltv.org；")
        print("  3. HLTV 网页被 Cloudflare 反爬拦截 —— 稍等片刻重跑一次；")
        print("  4. 网络慢，Chrome 首次运行需要自动下载驱动 —— 请耐心等待并重试。")
        print("若反复失败，请把上方红字内容截图发给发给你这个工具的人。")
    print("=" * 56)
