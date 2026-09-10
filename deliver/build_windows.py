# -*- coding: utf-8 -*-
"""Windows 一键打包脚本。

在【装有 Python 3.11 + 谷歌 Chrome】的 Windows 电脑上运行：

    python build_windows.py
    （或直接双击 build_windows.bat）

脚本会：
  1. 安装/更新打包所需依赖（openpyxl、selenium、undetected-chromedriver、pyinstaller）；
  2. 把三个入口各打成一个“单文件 exe”；
  3. 整理出交付文件夹 dist_交付（内含 3 个 exe + 3 份配置文件 + 使用说明）。

⚠ PyInstaller 只能在"当前这台机器对应的系统"上生成可执行文件：
  本脚本必须在 Windows 上运行，产出的 exe 才能给 Windows 朋友用。
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist_交付")
WORK = os.path.join(HERE, "build_tmp")
SPEC = os.path.join(HERE, "spec_tmp")

# (exe 显示名, 入口脚本, 对应内置的配置模板)
PROJECTS = [
    ("年度榜单爬虫", "main_year.py", "配置_year.ini"),
    ("单赛事爬虫",   "main_event.py", "配置_event.ini"),
    ("队伍爬虫",     "main_team.py",  "配置_team.ini"),
]


def step(msg):
    print("\n" + "=" * 60)
    print(msg)
    print("=" * 60)


def ensure_deps():
    """确保依赖齐全；缺 pyinstaller 时自动安装。"""
    step("第 1/4 步：检查依赖")
    try:
        import openpyxl  # noqa: F401
        import selenium  # noqa: F401
        import undetected_chromedriver  # noqa: F401
        print("✅ openpyxl / selenium / undetected-chromedriver 已安装")
    except ImportError:
        print("⬇️  正在安装基础依赖……")
        subprocess.run([sys.executable, "-m", "pip", "install", "-U",
                        "openpyxl", "selenium", "undetected-chromedriver"],
                       check=True)
    try:
        import PyInstaller  # noqa: F401
        print("✅ PyInstaller 已安装")
    except ImportError:
        print("⬇️  正在安装 PyInstaller……")
        subprocess.run([sys.executable, "-m", "pip", "install", "-U", "pyinstaller"],
                       check=True)


def clean_old():
    """清空旧的中间目录，避免残留影响本次打包。"""
    for path in (DIST, WORK, SPEC):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    os.makedirs(DIST, exist_ok=True)


def build_one(name, script, ini_name):
    """用 PyInstaller 把一个入口打成单文件 console exe。"""
    print(f"\n正在打包【{name}】……（约需 1~3 分钟）")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--console",
        "--distpath", DIST,
        "--workpath", WORK,
        "--specpath", SPEC,
        "--name", name,
        # 配置模板打进 exe：程序首次运行会自动把它释放到 exe 旁边
        "--add-data", f"{os.path.join(HERE, ini_name)};.",
        # uc 是运行时高度动态的库，整包收集以防缺文件
        "--collect-all", "undetected_chromedriver",
        os.path.join(HERE, script),
    ]
    subprocess.run(cmd, check=True)
    exe_path = os.path.join(DIST, name + ".exe")
    if not os.path.isfile(exe_path):
        raise SystemExit(f"❌ 打包完成但没找到输出：{exe_path}")
    print(f"✅ 已生成：{exe_path}")


def assemble_dist():
    """把 exe 与配置文件、使用说明放到同一个交付文件夹。"""
    step("第 4/4 步：整理交付文件夹")
    for _, _, ini_name in PROJECTS:
        shutil.copy2(os.path.join(HERE, ini_name), os.path.join(DIST, ini_name))
    usage = os.path.join(HERE, "使用说明_给朋友.txt")
    if os.path.isfile(usage):
        shutil.copy2(usage, os.path.join(DIST, "使用说明_给朋友.txt"))
    print(f"\n🎉 全部完成！交付文件夹在这里：\n   {DIST}\n")
    print("把它整个拷贝/压缩发给朋友即可。")
    print("（朋友电脑需要先安装 Google Chrome 并联网。）")


def main():
    if os.name != "nt":
        print("⚠ 本脚本只能在 Windows 上运行（PyInstaller 不能跨系统打包）。")
        print("  请在 Windows 电脑上把整个 deliver 文件夹拷过去再运行。")
        sys.exit(1)
    ensure_deps()
    clean_old()
    step("第 2/4 步：逐个打包（共 3 个）")
    for name, script, ini_name in PROJECTS:
        build_one(name, script, ini_name)
    assemble_dist()


if __name__ == "__main__":
    main()
