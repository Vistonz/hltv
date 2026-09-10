"""
EVP 新算法实验脚本 (v1 草案)
====================================
按"单场 BO 对决"给分, 而非现有按单图给分。

数据流:
  raw_event_{id}_data.xlsx  (Step1 采集, 保留不动)
      ↓ 层1: 连续段分组 → 识别每场 BO 对决 (带 bo_id)
      ↓ 层2: 单图给分 (绝对 rating 75% + 相对队伍 25%, 胜图 ×WIN_MULT)
      ↓ 层3: BO 给分 = Σ 各图分, 应用平滑软上限 (BO1=1/BO3=2/BO5=3 为参考点, 封底 -1)
      ↓ 层4: 阶段差异化 (小组赛 cap 参考点 ×GROUP_MULT)
      ↓ 层5: 选手总分 = 淘汰赛分 + 长度惩罚 + 双轨小组总分上限
             (豁免组=直接进四强宽松; 普通组=打了QF收紧)

输出:
  experiment_{id}_evp_new.xlsx   选手汇总 + BO汇总 + 单图给分
  experiment_{id}_bo_details.xlsx  中间产物: 每场BO每个选手的逐图给分明细
"""
import math
import pandas as pd

# ----------------------------------------------------------------------
# 0. 系数集中配置区 (用户之后统一调整)
# ----------------------------------------------------------------------
EVP_CONFIG = {
    # --- 单图给分 ---
    "ABS_WEIGHT": 0.967283326073,       # 绝对部分权重 (rating)
    "REL_WEIGHT": 0.081752117242,       # 相对部分权重 (rating/team_avg) —— 恢复: 保留队友相对惩罚
    "REL_CLIP_NEG": False,    # rel 负值是否归零: False = 保留负值惩罚 (全胜队内部也能区分谁相对平庸)
    "ABS_SCALE": 0.809400133269,         # F_abs = (rating - 1.0) * ABS_SCALE
    "REL_SCALE": 1.672849406939,         # F_rel = (rating/team_avg - 1.0) * REL_SCALE
    "GAMMA_ABS": 0.749616129187,         # 基础映射非线性度 (2026-08-29): F_abs = sign(x)·|x|^γ · ABS_SCALE, x=rating-1.
                              #   1.0=线性; <1 压缩高端(低端差异更陡, log 型); >1 放大高端(高端差异更陡).
    "GAMMA_REL": 1.255465302184,         # 相对部分同理, x = rating/team_avg - 1.
    "WIN_MULT": 2.32716651439,          # 胜利BO的胜利地图加成: 只有整场BO赢下时, 胜图才 × 此系数 (推动胜利进程)
    # --- 对手强度 (用户 hltv evp.py 原始设计: rank_weight = BASE_WEIGHT_C + RANK_K/(rank+5)) ---
    # 反比例: rank 越小(对手越强)权重越大, 无排名(999)趋近 BASE_WEIGHT_C. 强队放大+弱队打折.
    "BASE_WEIGHT_C": 1.0,    # 基准权重: rank→∞ 时的 rank_weight. 1.0=弱队不改变分值.
    "RANK_K": 0.0,           # 强度梯度系数: rank=1 时权重=BASE_WEIGHT_C+RANK_K/6. 0=关闭.
    "LOSE_MULT": 1.345823166718,       # 输图正分压缩: 输图 ms>0 时 × LOSE_MULT. 1.0=不压缩.
    "BO_LOSS_FACTOR": 1.276719505085,    # 整场BO输掉时正分打折系数: 1.0 = 不打折 (负分照扣, 输 BO 不额外砍正分)
    "BO_LOSS_FACTOR_NORMAL": 1.21416484122,  # 普通组(打了QF)输掉的BO正分打折: 败者组爬回的队伍, 输掉的BO含金量低.
                              #   1.0=与豁免组一致; 0.0=输掉的BO正分归零(治"输家还拿分", 只影响普通组, 豁免组保留)
    "MAP_SOFT_CAP": 0.874054682227,      # 单图软上限: 超过后增速 -50% (平滑打折). 小组赛基准.
    "MAP_HARD_MAX": 1.937228702786,      # 单图绝对上限: 达到后锁定为最大值. 小组赛基准.
    # --- 阶段化单图上限 (2026-08-29, 展开现有参数而非新机制) ---
    # 淘汰赛/决赛的单图上限 = 小组基准 × 对应乘子. 1.0 = 与小组一致 (round11 行为).
    "PO_SOFT_MULT": 0.436631099822,         # 淘汰赛 (Quarter/Semi, 不含 GF) 软上限乘子
    "PO_HARD_MULT": 1.277831624519,         # 淘汰赛硬上限乘子
    "GF_SOFT_MULT": 1.535186839517,         # 决赛 (Grand final) 软上限乘子
    "GF_HARD_MULT": 0.952537520458,         # 决赛硬上限乘子
    # --- BO 封顶 (最多/最少分) ---
    "CAP_BO1": 1.022027214358,            # BO1 单场封顶 (2026-08-31 新口径调优 ×2.5)
                              #   旧值 0.855 太低: BO1 单图 map_sum 在 0.85~2.0 之间全被 soft_cap
                              #   打折压平, 丢失神级 BO1 表现的真实差异. 旧口径 TPE 收敛 0.855
                              #   是被 mismatch 惩罚绑架 (调高 → BO1 分差变大 → mismatch 变差).
                              #   新口径(无 mismatch) 大尺度粗扫发现强单调正增益: ×2.5 → obj +1.62
                              #   (峰值平台 x2.2~x2.55, 28 赛事受惠, 15 改善 9 恶化, 3 次稳定).
                              #   副作用温和: BO1 赛事分数涨 → 中档 top1 z +0.5~0.6, 顶流摊薄 -0.1.
    "CAP_BO3": 1.917766475722,           # BO3 最多 +2 分
    "CAP_BO5": 3.252394606849,           # BO5 最多 +3 分
    "BO_FLOOR": -1.0,         # 单场 BO 最多扣 1 分 (崩盘兜底, 不再保命)
    # 赢 BO 里的崩盘: 队伍赢下系列赛但选手个人地图净负分, 不享受输 BO 的兜底 → floor 更深.
    #   区分点: 输 BO 的崩盘已被"输掉系列赛"本身惩罚; 赢 BO 还崩盘 = 拖后腿, 该实扣.
    #   8240 特例: YEKINDAR 小组赢 Astralis 但 Σ-2.09 (floor 保命到 -1.0), molodoy 决赛输
    #   Vitality 但 Σ-1.65 (输 BO 崩盘, 不受此影响) → 只命中 YEKINDAR, 精确区分同队选手.
    #   -1.0 = 与输 BO 相同 (不启用); 更低值 = 更深的兜底 (可设 -2.0 或 直接实扣 -99)
    "WIN_BO_FLOOR": -99.0,
    # --- 阶段差异化 ---
    "GROUP_MULT": 1.83542937657,       # 小组赛封顶 = 淘汰赛 × 0.75 (BO3 小组赛 = 1.5)
    "GROUP_STAGES": ["Groups", "Online", "3rd place"],   # 3rd place 是安慰赛, 参照小组赛打折
    # --- 平滑软上限 (soft-landing + soft-saturate) ---
    "OVER_CAP_SLOPE": 0.739602351516,       # 淘汰赛 BO 超过 cap 后的增速比例 (0=硬切, 1=不压缩)
    "GROUP_OVER_CAP_SLOPE": 0.724323727776, # 小组赛 BO 超过 cap 后的增速比例: 豁免组(直接进四强, 全胜晋级, 神图是有效晋级图)不压
    "GROUP_OVER_CAP_SLOPE_NORMAL": 0.09609552026,  # 小组赛 BO 超额收紧: 普通组(打了 QF, 败者组爬回)的神图累积压更狠
    "SOFT_LAND_SPREAD": 0.297602959708, # cap 后软着陆宽度 = cap 的倍数 (过渡区)
    "SATURATE_TAU": 0.661931752091,      # 普通组小组 BO 超额指数衰减时间常数 (None=不启用 saturate, 走斜率)
    "SATURATE_R0": 0.45199795487,      # saturate 衰减段的起始增速
    "SATURATE_FLAT": 0.371882866569,     # 超额豁免区: 超额 ≤ flat 完全按 soft_cap 给足 (小额神图照给), 超过才衰减.
                              #   None = 默认 cap*SOFT_LAND_SPREAD (与旧行为一致).
                              #   8240 关键: Spinx 的 NRG 超额 0.61 vs YEKINDAR 的 NAVI 1.37/MongolZ 1.03,
                              #   取 flat≈0.5-0.8 时 NRG 几乎不受影响而 NAVI/MongolZ 被衰减 → 同时满足
                              #   "Spinx≥5" 且 "YEKINDAR<5" (两人都是普通组, 但神图超额量级不同).
    # --- 小组赛总分软上限 (双轨: 豁免组 vs 普通组) ---
    # 豁免组(exempt) = 小组第一直接进四强(打了SF没打QF): 全胜晋级, 胜图全是有效晋级图,
    #                  上限高、压得少 (起点 4.5, 到输入 6.0 封顶, 输出最大值 4.8)
    # 普通组         = 小组第二(打了 QF): 败者组爬回多打, 上限低、压得狠 (起点 4.0, 封顶 5.0)
    "GROUP_CAP_EXEMPT": {"soft": 2.128492538434, "xmax": 10.219140636659, "slope": 0.303087235995},
    # 普通组(打了QF)总 cap: xmax 提到 8.0/slope 0.4 后, 8248 的 donk(组原始高)能从 5.0 附近涨到 5.2,
    #   且 8240 无损 (YEKINDAR 组 1.87 远低于 soft=4.0, 完全不受影响)
    "GROUP_CAP_NORMAL": {"soft": 2.29238633514, "xmax": 16.127916151131, "slope": 0.456896467889},
    # --- 豁免组补偿 (简化替代双轨 cap 差异) ---
    # 豁免组(小组第一直接进四强)少打一场 6进4(QF): 小组分等比上浮后再进小组总分软上限.
    # 补偿乘在 cap 之前 → 高小组分(撞 cap)的增量被上限吸收, 低小组分获得真实补偿:
    # 不放大"小组分优势", 不破坏 ropz>ZywOo 这类组内相对顺序 (ZywOo 小组撞cap补不到, ropz 补到).
    "EXEMPT_COMP": 1.851880339307,         # 1.0=不补偿; >1 = 豁免组小组分在 cap 前 × 该系数
    # --- 决赛(Grand final)独立单 BO cap ---
    # 决赛赛制是 BO5, 数据只记录实际打的 3 图 (2-0/2-1 提前结束), 却按 nmaps 归入 CAP_BO3=2.0,
    # 系统性低估决赛统治表现. 决赛独立 cap (BO5 允许更高), 只影响决赛.
    # 8248: ropz GF map_sum 3.87 → CAP_GF=3.4 后保留到 ~3.8, ropz 8.33 > ZywOo 8.23 达成分区 MVP 第一.
    # 8240: GF 选手 ZywOo 5.49/其他选手均被 CAP_GF 提高但都在各自榜单头部, 相对顺序不变, YEKINDAR(1.04)不受影响.
    "CAP_GF": 4.361143354446,
    # --- 淘汰赛总分软上限 (双轨) ---
    # 2026-08-30 最终定案 (纯全局 obj 目标, 用户确认): 原 soft=999 形同虚设 → 淘汰赛分全数计入.
    # PLAYOFF soft×2 由 optuna_mp TPE 纯 obj 搜索联动得出 + 全 SPACE touch 2000 trials 精调 (obj=107.03).
    #   ordered 77.11% 不变, 高分档比手动平均高 +0.26.
    #   联动规则 (optuna_mp._norm_playoff 同款): xmax=soft×1.5, slope=0.1.
    "PLAYOFF_CAP_EXEMPT": {"soft": 7.06285005424, "xmax": 14.601438395556, "slope": 0.1},
    "PLAYOFF_CAP_NORMAL": {"soft": 6.37543923335, "xmax": 4.528850346147, "slope": 0.1},
    # 纯淘汰赛赛事补偿 (2026-08-30): 无小组赛的赛事 (BLAST赏金赛 8246 / EPL S23 8413)
    # 总分 = 淘汰赛单段, 缺"小组段"垫底 → 系统性比"小组+淘汰两段"的正常赛事低 ~0.8×.
    # 淘汰分乘 NO_GROUP_MULT 补偿缺失的小组段.
    # 历史: TPE 纯 obj 收敛 1.533, 但把 makazze(8413)放大虚高; 用户 2026-08-30 定为 1.3
    # (缓解 makazze 虚高, 但 8246 nota 与 m0NESY 差 0.001 属 5 分线旧口径噪声).
    # 2026-08-31 新口径 (无 mismatch, topN 判定) 验证: 评估平台上 NGM∈[0.26,0.40] 时
    # ordered 212/326 (obj 121.95→122.26 +0.31), 但该增益仅来自 8413 (3rd place 分不乘 NGM,
    # phzy #6→#3), 且 NGM=0.35 会把纯淘汰赛 MVP 的 z_score 从 +3.5 打到 +0.6 (makazze/donk),
    # 直接破坏荣誉分跨赛事可比性 → 副作用不可接受, 维持 1.3.
    # [2026-08-31 修正] "无真实可调增益"结论已被 CAP_BO1/LEN_PENALTY 推翻:
    #   旧口径 TPE 收敛被 mismatch 惩罚绑架, 新口径(无 mismatch, W_MVP=0.4) 大尺度粗扫(×0.35~×2.2)
    #   发现 CAP_BO1 ×2.5 (+1.62) 与 LEN_PENALTY ×1.8 (+0.26) 两个真实增益, obj 136.912→138.791.
    #   随机精调 (±20% × 42 维 × 600 组合) 0/601 提升 → 多维局部最优, 已定案.
    #   教训: 单参数双向小尺度(±15%)扫不到非线性拐点, 必须大尺度粗扫.
    "NO_GROUP_MULT": 1.272155240542,
    # --- 小组赛长度边际递减 (核心: 按"胜利地图数 vs 进淘汰赛最少需要数") ---
    # 原则: 赛事中进淘汰赛最少需要多少张胜利地图 = MIN_WIN_MAPS.
    #   超出该标准的胜利图 = "输了再爬回来"走弯路的代价, 每超出 1 张, 累积总价值 × (1 - LEN_PENALTY).
    #   8240 里进淘汰赛最短是 4 张 (GSL 小组赛首轮 2-0 + 胜者赛 2-0), molodoy 打了 6 张 → 超 2 张 → 惩罚.
    # 图少/直接全胜晋级不受影响; 不再按"平均每图得分"单独划线 (长度惩罚已覆盖长赛程虚高).
    # MIN_WIN_MAPS 不全局写死: None = 每次运行先用 determine_min_win_maps 自动确定
    #   (取"打进淘汰赛的选手中最小的小组赛胜利图数"), 赛制不同则值不同.
    #   8240 (ESL/GSL) 与 8248 (BLAST Open) 自动确定都是 4. 若某赛事需要显式指定, 直接给数值.
    "MIN_WIN_MAPS": None,     # None = 每次运行先自动确定 (晋级淘汰赛最少胜利地图数)
    "LEN_PENALTY": 0.023826973206,     # 每超出 1 张胜利图, 累积总价值缩减比例 (1.2%):
                              #   2026-08-31 新口径调优 ×1.8 (旧 0.00674=0.7%). 演进: 旧口径
                              #   (W_MVP=0.2) 峰值 x1.5; 用户加码 MVP 权重 (W_MVP=0.4) 后
                              #   峰值漂移到 x1.7~x1.8 (mvp 189 vs 188 差异被权重放大), 取 1.8.
                              #   语义: 加重"多打才晋级"的弯路惩罚. 副作用温和 (4/254 |Δz|>0.5).
    # --- ESL/GSL 赛制特殊处理 (大部分赛制胜利图数已统一, 只有 ESL/GSL 双败有"直接进四强"vs"进淘汰赛"之分) ---
    # 小组第一直接进四强(没打 QF 就打 SF)的选手, 胜利图全是有效晋级图 → 豁免长度惩罚.
    # 进淘汰赛(打了 QF)的选手 → 多余胜利图数 × ESL_GSL_FACTOR 折算后再惩罚 (先按用户给的 5/6).
    "ESL_GSL_MODE": True,     # 本赛事是 ESL/GSL 赛制
    "ESL_GSL_FACTOR": 1.05503206976,  # ESL/GSL 下多余胜利图的折算系数 (调优确定)
}

# ----------------------------------------------------------------------
# 0b. CS2 段独立配置 (两套分拆, 2026-09-09 用户指令 "拆成两套")
# ----------------------------------------------------------------------
# EVP_CONFIG = CS:GO 段逐字节冻结源 (42 核心参数, 永不含 CS2 机制键).
# CS2 段 = EVP_CONFIG + CS2_OVERRIDES (cfg_for merge). CS2_OVERRIDES 可覆写任意键:
#   机制轴权重 (CS2_<AXIS>_W) 在此; 若未来要 CS2 独立漂移, 42 核心参数也可放这里 —
#   CS:GO 永远不 merge → 逐字节冻结保证在架构层面而非仅结构性.
#
# CS2 mapstats 事件级加成机制轴 (2026-09-09):
#   - 旧 2 轴定案 (obj 161.2287→162.3726, 2026-09-09 已验证写回) 迁名:
#     CS2_CLUTCH_W → CS2_KPRW_E_W (语义即 kprw_e), CS2_DPR_W 名保留.
#   - 预检 v3 (score-matched 边界配对, 2026-09-09): 同 total_score 下官方入选者偏好更高
#     kprw_e (o>n 0.628) 与更低 dpr (o>n 0.417). 当时因与 rating3 共线 0.73–0.93 排除了
#     swing/adr/kpr/mk/kast 等轴. 2026-09-09 用户指令 "CS2 添加所有这些参数跑回归" →
#     全候选轴机制化 (下方默认 0 的键): 每轴一个权重键, 符号由回归拟合, 不再预筛丢弃.
#   - r30 (≡ 公式 rating 输入, corr 1.000) 不设键 (公式已直接用, 无增量).
#   - 量纲: 事件内 z 标准化 → 权重单位 ≈ 分数. 触发: 任一非 0 轴权重 且 raw 带 CS2
#     专属列 (CS:GO raw 结构无列 → 永不触发 → 冻结双保险).
CS2_OVERRIDES = {
    # --- 旧 2 轴定案迁移 (2026-09-09, 全量 obj 162.3726 已验证) ---
    # 权重带符号: 机制引擎统一 bonus = Σ w·z(feature). 旧引擎对 dpr 是 −0.04·z(dpr)
    # (官方偏好低 dpr), 迁移等价于 CS2_DPR_W = −0.04 (回归系数本就该带符号, 不预写死方向).
    "CS2_KPRW_E_W": 0.19,   # kprw_e: Σwon_kills/Σrounds_won (按获胜回合加权击杀效率)
    "CS2_DPR_W": -0.04,     # dpr: 存活控制 (官方偏好低值 → 负权重)
    # --- 2026-09-09 新增候选轴 (全候选机制化, 默认 0 = 待回归定夺) ---
    "CS2_KPRW_AVG_W": 0.0,  # kprw 各图简单平均 (对照 kprw_e 的回合加权口径)
    "CS2_KPR_W": 0.0,       # kpr: 每回合击杀
    "CS2_KAST_W": 0.0,      # kast: KAST 贡献%
    "CS2_MK_W": 0.0,        # mk: 多杀 rating
    "CS2_ADR_W": 0.0,       # adr: 平均每回合伤害
    "CS2_SWING_SUM_W": 0.0, # swing 事件总和 (赛事内累积影响力)
    "CS2_SWING_AVG_W": 0.0, # swing 每图均值 (影响力速率)
}


def cfg_for(segment, base=None, cs2_overrides=None):
    """产品段配置: segment=='cs2' → base + CS2 覆写; 否则 → base (EVP_CONFIG 冻结).

    cs2_overrides=None → 模块 CS2_OVERRIDES (生产默认, 复现 obj 162.3726);
    {} → 强制机制关 (闸门基线); dict → 自定义覆写 (搜索逐点传入).
    base=None → EVP_CONFIG (CS:GO 冻结源). 返回 dict 副本, 不污染调用方.
    """
    base = dict(EVP_CONFIG if base is None else base)
    if segment == "cs2":
        ov = CS2_OVERRIDES if cs2_overrides is None else cs2_overrides
        if ov:
            base.update(ov)
    return base


# ----------------------------------------------------------------------
# 层1: BO 识别 (连续段分组)
# raw 行序 = 抓取顺序 = 比赛顺序; 同一 (对手对,阶段) 连续出现的地图块 = 同一场 BO
# ----------------------------------------------------------------------
def split_into_bos(df):
    bos = []
    cur_pair = None
    cur_rows = []
    bo_id = 0
    for idx, r in df.iterrows():
        pair = (
            min(r["team"], r["opponent"]),
            max(r["team"], r["opponent"]),
            r["match_stage"],
        )
        if pair != cur_pair:
            if cur_pair is not None:
                bo_id += 1
                bos.append((bo_id, cur_pair, pd.DataFrame(cur_rows)))
            cur_pair = pair
            cur_rows = []
        cur_rows.append(r)
    if cur_pair is not None:
        bo_id += 1
        bos.append((bo_id, cur_pair, pd.DataFrame(cur_rows)))
    return bos

# ----------------------------------------------------------------------
# 层2: 单图给分 (每张图 = 段内连续 10 行: team1 5人 + team2 5人)
# ----------------------------------------------------------------------
def map_scores_for_bo(bo_id, bo_df, cfg):
    """返回带每行 map_score 的 DataFrame, 以及该 BO 的图数"""
    # 先判断本 BO 各队胜负: 赢图数 > 输图数 = 赢下整场 BO
    # (raw 每张图 = 连续 10 行: 各队 5 人; 给每行加临时图索引用于统计)
    tmp = bo_df.copy()
    tmp["_map"] = tmp.index // 10  # 行序即图序, 每 10 行一张图
    team_win_bo = {}
    for team, g in tmp.groupby("team"):
        per_map = g.groupby("_map")["round_differential"].first()
        team_win_bo[team] = (per_map > 0).sum() > (per_map < 0).sum()

    rows = []
    nmaps = len(bo_df) // 10
    for gi in range(nmaps):
        block = bo_df.iloc[gi * 10 : gi * 10 + 10]
        for _, r in block.iterrows():
            win = r["round_differential"] > 0
            win_bo = team_win_bo[r["team"]]
            # 基础映射: F(x) = sign(x)·|x|^γ (带符号幂). γ=1 线性(round11 基线);
            # γ<1 压缩高端(低 rating 差异放大, log 型); γ>1 放大高端(高 rating 差异放大).
            _gamma = lambda x, g: math.copysign(abs(x) ** g, x) if x else 0.0
            abs_score = _gamma(r["rating"] - 1.0, cfg.get("GAMMA_ABS", 1.0)) * cfg["ABS_SCALE"]
            rel_score = _gamma(r["rating"] / r["team_avg_rating"] - 1.0, cfg.get("GAMMA_REL", 1.0)) * cfg["REL_SCALE"]
            if cfg.get("REL_CLIP_NEG") and rel_score < 0:
                rel_score = 0.0
            ms = cfg["ABS_WEIGHT"] * abs_score + cfg["REL_WEIGHT"] * rel_score
            # 对手强度因子 (用户 hltv evp.py 原始设计): rank_weight = BASE_WEIGHT_C + RANK_K/(rank+5).
            # 反比例: rank 越小(对手越强)权重越高; 无排名(999)时趋近 BASE_WEIGHT_C. 强队放大+弱队打折.
            # BASE_WEIGHT_C=1.0 且 RANK_K=0 时恒等于 1.0 (关闭, 保持 round11 行为).
            ms *= cfg.get("BASE_WEIGHT_C", 1.0) + cfg.get("RANK_K", 0.0) / (r["opponent_rank"] + 5.0)
            # 胜利地图加成: 默认只有整场BO赢下时, 胜图才 × WIN_MULT (推动胜利进程).
            # WIN_ALL_MAPS=True 时所有胜利地图都加成 (广义胜利地图): 输BO里的胜图同样
            # 是"赢下一张地图"的表现, 也承认其推进价值 (仍受 BO_LOSS_FACTOR 整体打折约束).
            if win and (cfg.get("WIN_ALL_MAPS", False) or win_bo):
                ms *= cfg["WIN_MULT"]
            # 整场BO输掉的队伍, 正分打折 (输掉系列赛不奖励)
            if not win_bo and ms > 0:
                ms *= cfg["BO_LOSS_FACTOR"]
            # 输掉的图: 正 rating 是"虽败犹荣", 官方 EVP 不奖励 → 压缩. LOSE_MULT=1.0 不压缩.
            if not win and ms > 0:
                ms *= cfg.get("LOSE_MULT", 1.0)
            # 阶段化单图上限: 淘汰赛/决赛用独立 cap (乘子相对小组基准, 1.0=一致). 无新机制.
            _st = r["match_stage"]
            _soft = cfg["MAP_SOFT_CAP"]
            _hard = cfg["MAP_HARD_MAX"]
            if _st == "Grand final":
                _soft *= cfg.get("GF_SOFT_MULT", 1.0)
                _hard *= cfg.get("GF_HARD_MULT", 1.0)
            elif _st not in cfg["GROUP_STAGES"]:
                _soft *= cfg.get("PO_SOFT_MULT", 1.0)
                _hard *= cfg.get("PO_HARD_MULT", 1.0)
            # 单图软上限: 超过后增速减半 (平滑打折)
            ms = soft_cap(ms, _soft, cfg)
            # 单图绝对上限: 达到后锁定
            ms = min(ms, _hard)
            rows.append({
                "bo_id": bo_id,
                "player": r["player"],
                "team": r["team"],
                "opponent": r["opponent"],
                "opponent_rank": r["opponent_rank"],
                "match_stage": r["match_stage"],
                "map_idx": gi + 1,
                "total_rounds": r["total_rounds"],
                "rating": r["rating"],
                "team_avg_rating": r["team_avg_rating"],
                "round_differential": r["round_differential"],
                "win": win,
                "win_bo": win_bo,
                "abs_score": round(abs_score, 4),
                "rel_score": round(rel_score, 4),
                "map_score": round(ms, 4),
            })
    return pd.DataFrame(rows), nmaps

# ----------------------------------------------------------------------
# 层3+4: BO 给分 (Σ 各图分 → 平滑软上限, 以 BO 长度+阶段确定 cap 参考点)
# ----------------------------------------------------------------------
def bo_cap_for(nmaps, stage, cfg):
    if stage == "Grand final" and cfg.get("CAP_GF") is not None:
        # 决赛是 BO5 赛制(数据只记实际打的图), 独立 cap 避免按 nmaps 低估决赛统治表现
        base = cfg["CAP_GF"]
    elif nmaps == 1:
        base = cfg["CAP_BO1"]
    elif nmaps in (2, 3):
        base = cfg["CAP_BO3"]
    else:
        base = cfg["CAP_BO5"]
    if stage in cfg["GROUP_STAGES"]:
        base = base * cfg["GROUP_MULT"]
    return base

def soft_cap(x, cap, cfg, slope=None):
    """平滑软上限 (soft-landing + soft-saturate).

    取代原先的硬 clip, 形状:
      - x <= 0     : 原样返回 (负分不压缩, 下限由调用方 clip)
      - 0 < x <= cap: 线性, 斜率 1 —— 低分不被放大
      - x > cap    : 斜率在 [cap, cap+spread] 内从 1 平滑降到 OVER_CAP_SLOPE
                     (smoothstep 过渡, 斜率连续), 之后按 OVER_CAP_SLOPE 恒定增速
      - 即"到达 cap 后按比例减少增加速度", 但不再硬切; 出色表现仍能明显超出 cap

    参数:
      slope  : 超出 cap 后的稳定增速比例 (默认取 cfg['OVER_CAP_SLOPE']).
               小组赛 BO 可传 cfg['GROUP_OVER_CAP_SLOPE'] 独立收紧"神图累积".
      SOFT_LAND_SPREAD : 过渡区宽度 = cap × 该值
    """
    if x <= 0 or cap <= 0:
        return x
    if x <= cap:
        return x
    r = slope if slope is not None else cfg["OVER_CAP_SLOPE"]
    spread = cap * cfg["SOFT_LAND_SPREAD"]
    u = x - cap
    if u <= spread:
        t = u / spread
        # smoothstep 减速: 斜率从 1 平滑降到 r, 积分得到增量
        ease = t * t * (3.0 - 2.0 * t)          # 3t² - 2t³
        slope_integral = u - (1.0 - r) * spread * (t ** 3 - t ** 4 / 2.0)
        return cap + slope_integral
    # 过渡区之后: 恒定斜率 r
    landing_gain = spread * (1.0 + r) / 2.0
    return cap + landing_gain + r * (u - spread)

def saturate_cap(x, cap, cfg, r0=None, tau=None, flat=None):
    """超额递减软上限: 超过 cap 后, 增速从 r0 指数衰减到 0 (超额越大越不值钱).

    与 soft_cap 的区别: soft_cap 超出后保持恒定斜率 (神图越大给越多, 只是打折);
      saturate_cap 超出后增速一路衰减, 神图再高给分也逼近饱和 → 专治"单场超高神图"的虚高,
      且超额小的 (刚过 cap) 几乎不受影响 → 精准区分"一两张爆炸神图" vs "每张都小幅超出".

    参数:
      flat : 超额豁免区. 超额 ≤ flat 的部分完全按原 soft_cap 给足 (与软上限一致, 小额超额不罚);
             超过 flat 才开始指数衰减. 用于"小额神图照给、超大额神图才压"的区分.
             默认 None = cap*SOFT_LAND_SPREAD (即过渡区结束处才开始衰减, 与旧行为一致).

    形状:
      - x <= cap: 线性, 斜率 1
      - cap < x <= cap+flat: 同 soft_cap (平滑过渡到 r0, 小额超额几乎全给)
      - x > cap+flat: 在 flat 处接指数衰减, 增速降到 0
        (渐近最大值 = cap + soft_cap(flat) + r0*tau)
    """
    if x <= cap or cap <= 0:
        return x
    if r0 is None:
        r0 = cfg.get("SATURATE_R0", 0.35)
    if tau is None:
        tau = cfg.get("SATURATE_TAU", 1.0)
    if flat is None:
        flat = cap * cfg["SOFT_LAND_SPREAD"]
    # 超额豁免区: 完全按 soft_cap (与软上限一致)
    y_flat = soft_cap(cap + flat, cap, cfg, slope=r0)
    if x <= cap + flat:
        return soft_cap(x, cap, cfg, slope=r0)
    # 超过 flat: 从 y_flat 开始, 增速指数衰减到 0
    v = x - (cap + flat)
    extra = r0 * tau * (1.0 - math.exp(-v / tau))
    return y_flat + extra

def total_cap(x, cc):
    """通用双轨总分软上限: 超过 soft 后增速骤降, 到输入 xmax 时达到输出最大值, 之后停止增加.

    形状:
      - x <= soft: 线性, 斜率 1 (低分不受影响)
      - soft < x < xmax: 每多打 1 分只算 slope 分 (增速骤降)
      - x >= xmax: 输出恒等于 soft + (xmax-soft)*slope (最大值, 停止增加)
    """
    lo = cc["soft"]
    xmax = cc["xmax"]
    slope = cc["slope"]
    if x <= lo:
        return x
    if x >= xmax:
        return lo + (xmax - lo) * slope
    return lo + (x - lo) * slope

def group_total_cap(x, cfg, exempt=False):
    """小组赛总分软上限 (双轨): 超过 soft 后增速骤降, 到输入 xmax 时达到输出最大值, 之后停止增加.

    exempt=True  (直接进四强的小组第一, 全胜晋级): 胜图全是有效晋级图 → 宽松配置 (起点高, 压得少)
    exempt=False (打了 QF 的小组第二, 败者组爬回)  : 多打的胜图含金量低 → 收紧配置 (起点低, 压得狠)
    """
    cc = cfg["GROUP_CAP_EXEMPT"] if exempt else cfg["GROUP_CAP_NORMAL"]
    return total_cap(x, cc)

def playoff_total_cap(x, cfg, exempt=False):
    """淘汰赛总分软上限 (双轨).

    exempt=True  (直接进四强): 只打 SF+GF 两场, 全是有效晋级分 → 不压.
    exempt=False (打了 QF)    : 打了 QF+SF+GF 三场, QF 是败者组多打的 → 总分起点低、压得狠,
                                专治"每场都稳定正分"的累积虚高.
    """
    cc = cfg["PLAYOFF_CAP_EXEMPT"] if exempt else cfg["PLAYOFF_CAP_NORMAL"]
    return total_cap(x, cc)

def aggregate_bo_scores(map_df, cfg, meta=None):
    """按选手聚合 BO 总分, 应用平滑软上限 (封底仍为硬下限).

    双轨差异 (需 meta: player → {"direct_semi": bool}):
      - 小组赛 BO 超额斜率: 豁免组(直接进四强, 神图是有效晋级图)用 GROUP_OVER_CAP_SLOPE 不压;
        普通组(打了 QF, 败者组爬回)用 GROUP_OVER_CAP_SLOPE_NORMAL 收紧 (神图累积压更狠)
      - 赢 BO 的崩盘兜底: 队伍赢了系列赛但选手个人负分, 用 WIN_BO_FLOOR (更深, 不享受输 BO 的兜底)
    meta 为空时退化为旧行为 (全员默认斜率 + 统一 BO_FLOOR).
    """
    grouped = map_df.groupby("player")["map_score"].sum()
    stage = map_df["match_stage"].iloc[0]
    nmaps = map_df["map_idx"].max()
    cap = bo_cap_for(nmaps, stage, cfg)
    is_group = stage in cfg["GROUP_STAGES"]
    # 赢/输 BO 判定 (每选手)
    win_bo_map = map_df.groupby("player")["win_bo"].first()

    def _bo_score(player, v):
        floor = cfg["BO_FLOOR"]
        is_exempt = bool(meta is not None and meta.get(player, {}).get("direct_semi"))
        if is_group:
            # 赢 BO 的崩盘兜底更深: 队伍赢了但个人负分 → 实扣不保命
            if bool(win_bo_map.get(player, False)):
                floor = min(floor, cfg.get("WIN_BO_FLOOR", cfg["BO_FLOOR"]))
            if is_exempt:
                # 豁免组(直接进四强): 神图是有效晋级图, 超额不收紧
                val = soft_cap(v, cap, cfg, slope=cfg.get("GROUP_OVER_CAP_SLOPE", cfg["OVER_CAP_SLOPE"]))
            else:
                # 普通组(打了QF): 若启用超额递减则用 saturate, 否则用收紧斜率
                if "SATURATE_TAU" in cfg and cfg["SATURATE_TAU"] is not None:
                    val = saturate_cap(v, cap, cfg, flat=cfg.get("SATURATE_FLAT", None))
                else:
                    val = soft_cap(v, cap, cfg, slope=cfg.get("GROUP_OVER_CAP_SLOPE_NORMAL", cfg["OVER_CAP_SLOPE"]))
        else:
            val = soft_cap(v, cap, cfg)
        return max(floor, val)

    out = pd.DataFrame([(p, _bo_score(p, v)) for p, v in grouped.items()],
                       columns=["player", "bo_score"])    # 季军赛是安慰赛, 总得分正负都再除 2 (如 Spirit 2-0 赢的季军战也要减半)
    if stage == "3rd place":
        out["bo_score"] = out["bo_score"] / 2.0
    # 高质量胜利加权: 赢 BO 的正分, 对手 rank 靠前(≤MAX)时 ×K.
    # 治"赢强队 vs 赢弱队"的含金量差: 弱队(高 rank)分数由对手 rating 拉高, 但不代表晋级含金量;
    # 只在 BO 层(cap 后)乘, 不与单图 cap 耦合.
    wrk = cfg.get("WIN_RANK_K", 1.0)
    if wrk != 1.0:
        wr_max = cfg.get("WIN_RANK_MAX", 0)
        wb = map_df.groupby("player")["win_bo"].first()
        rank_map = map_df.drop_duplicates("player").set_index("player")["opponent_rank"]
        strong = out["player"].map(rank_map).fillna(99) <= wr_max
        out.loc[(out["bo_score"] > 0) & out["player"].map(wb) & strong, "bo_score"] *= wrk
    # 赢弱队打折: 赢 BO 的正分, 对手 rank ≥ MIN 时 ×P (治"刷弱队凑分")
    wwk = cfg.get("WIN_WEAK_P", 1.0)
    if wwk != 1.0:
        ww_min = cfg.get("WIN_WEAK_MIN", 99)
        wb = map_df.groupby("player")["win_bo"].first()
        rank_map = map_df.drop_duplicates("player").set_index("player")["opponent_rank"]
        weak = out["player"].map(rank_map).fillna(0) >= ww_min
        out.loc[(out["bo_score"] > 0) & out["player"].map(wb) & weak, "bo_score"] *= wwk
    out["bo_id"] = map_df["bo_id"].iloc[0]
    out["match_stage"] = stage
    out["nmaps"] = nmaps
    out["cap"] = cap
    out["map_sum"] = grouped.values
    # 补充队名 (供汇总展示)
    team_map = map_df.drop_duplicates("player").set_index("player")["team"]
    out["team"] = out["player"].map(team_map)
    return out

def determine_min_win_maps(map_all, cfg, meta=None):
    """自动确定"晋级淘汰赛最少胜利地图数" (MIN_WIN_MAPS).

    原则: 长度惩罚的基准线 = 该赛事实际打进淘汰赛(打了非小组赛阶段)的选手中,
      小组赛胜利地图数的最小值 → 这就是"这个赛制下晋级淘汰赛真正需要的胜图数".
      赛制不同则值不同: 8240 (ESL/GSL) = 4, 8248 (BLAST Open) = 4,
      其他赛制 (BO1 单循环 / 瑞士轮 / 双败 / 纯淘汰) 可能为 2/3/4/5.

    每次运行都要先确定 (不全局写死): 若 cfg 显式给了 MIN_WIN_MAPS (非 None),
      尊重显式值 (用户对特定赛事的指定); 否则用数据自动推导.

    退化处理:
      - 无淘汰赛数据 (纯小组赛赛事) → 无法从晋级者推断 → 返回 0 (长度惩罚不生效)
      - 进淘汰赛选手无小组赛记录 → 该选手 win_maps=0 计入最小, 惩罚不生效 (赛制确实不需要胜图)
    """
    if cfg.get("MIN_WIN_MAPS") is not None:
        return cfg["MIN_WIN_MAPS"]
    if meta is None:
        meta = compute_meta(map_all, cfg)
    advance_stages = [s for s in cfg["GROUP_STAGES"] if s != "3rd place"]
    knockout = map_all[~map_all["match_stage"].isin(advance_stages)]
    if knockout.empty:
        return 0
    players = knockout["player"].unique()
    mins = [meta[p]["win_maps"] for p in players if p in meta]
    return min(mins) if mins else 0

def group_length_factor(win_maps, cfg, direct_semi=False):
    """小组赛长度边际递减系数 (基于胜利地图数, 不按固定图数划线).

    原则: 赛事中进淘汰赛最少需要多少张胜利地图 = MIN_WIN_MAPS.
      超出该标准的胜利图 = "输了再爬回来"走弯路的代价, 每超 1 张 × (1 - LEN_PENALTY).
      图少 / 全胜直接晋级 → 1.0 (不打折).

    ESL/GSL 赛制特殊: 小组第一直接进四强(没打 QF 就打 SF)的选手,
      他们的胜利图全是有效晋级图, 豁免长度惩罚 (如 Vitality/Spirit 也 6 张胜利图但直接进四强).
    """
    pen = cfg.get("LEN_PENALTY", 0.0)
    if pen <= 0:
        return 1.0
    # ESL/GSL: 直接进四强的小组第一, 不打长度惩罚
    if cfg.get("ESL_GSL_MODE") and direct_semi:
        return 1.0
    base = cfg.get("MIN_WIN_MAPS", 4)
    excess = max(0.0, win_maps - base)
    # ESL/GSL 下多余的胜利图可能因双败多打场次而偏高, 先 × 折算系数 (默认 5/6)
    if cfg.get("ESL_GSL_MODE"):
        excess = excess * cfg.get("ESL_GSL_FACTOR", 1.0)
    return max(0.0, (1.0 - pen) ** excess)

def compute_meta(map_all, cfg):
    """每选手: 小组赛胜利地图数 + 是否直接进四强 (豁免组).

    direct_semi (豁免组) = 打了 SF 但没打 QF → 小组第一直接进四强, 全胜晋级.
    普通组 = 打了 QF → 败者组爬回, 小组神图含金量低 (超额斜率收紧 + 长度惩罚).
    """
    advance_stages = [s for s in cfg["GROUP_STAGES"] if s != "3rd place"]
    m = map_all.copy()
    m["_is_group"] = m["match_stage"].isin(advance_stages)
    meta = {}
    for player, g in m.groupby("player"):
        win_maps = int(g[g["_is_group"] & g["win"]].shape[0])
        stages = set(g["match_stage"])
        played_qf = "Quarter-final" in stages
        played_sf = "Semi-final" in stages
        meta[player] = {"win_maps": win_maps, "direct_semi": played_sf and not played_qf}
    return meta


# ----------------------------------------------------------------------
# 层5: 选手总分 (淘汰赛分 + 平滑软上限的小组赛总分)
# ----------------------------------------------------------------------
def summarize_players(bo_scores_df, map_all, cfg, meta=None):
    """选手总分 = 淘汰赛分 + 双轨小组总分上限(长度惩罚后的小组赛分)

    长度惩罚依据每个选手的小组赛胜利地图数:
      - win_maps 超过进淘汰赛最少需要数(MIN_WIN_MAPS)的部分才惩罚
      - ESL/GSL 赛制下直接进四强(打了 SF 没打 QF)的选手豁免
    小组总分上限双轨:
      - 豁免组(直接进四强): 全胜晋级, 胜图含金量高 → 宽松上限
      - 普通组(打了 QF)   : 败者组爬回, 多打胜图含金量低 → 收紧上限
    """
    if meta is None:
        meta = compute_meta(map_all, cfg)
    # 纯淘汰赛赛事判定 (如 BLAST赏金赛 8246 / EPL S23 8413): 无小组赛/线上阶段 (Groups/Online),
    # 3rd place 是安慰赛不算. 这类赛事总分 = 淘汰赛单段, 不存在"小组段+淘汰段两段叠加虚高",
    # PLAYOFF soft cap (限两段叠加) 在此会直接压低总分天花板 → 不压淘汰赛.
    has_groups = bool(map_all["match_stage"].isin(
        [s for s in cfg["GROUP_STAGES"] if s != "3rd place"]).any())

    # 每次运行先确定长度惩罚基准线 (晋级淘汰赛最少胜利地图数), 不全局写死
    min_win_maps = determine_min_win_maps(map_all, cfg, meta=meta)
    cfg = {**cfg, "MIN_WIN_MAPS": min_win_maps}  # 局部副本, 不污染调用方

    # 普通组(打了 QF 的)输掉的 BO, 正分打折 (治"输家还拿分": 败者组爬回, 输的 BO 含金量低).
    # 豁免组(直接进四强)的输 BO 是顶级对决 (SF/GF), 正分保留.
    loss_n = cfg.get("BO_LOSS_FACTOR_NORMAL", 1.0)
    if loss_n < 1.0:
        wb = map_all.groupby(["player", "bo_id"])["win_bo"].first().reset_index()
        bo_scores_df = bo_scores_df.merge(wb, on=["player", "bo_id"], how="left")
        mask = (
            bo_scores_df["player"].map(lambda p: not meta[p]["direct_semi"])
            & ~bo_scores_df["win_bo"]
            & (bo_scores_df["bo_score"] > 0)
        )
        bo_scores_df.loc[mask, "bo_score"] *= loss_n

    rows = []
    for player, g in bo_scores_df.groupby("player"):
        group_df = g[g["match_stage"].isin(cfg["GROUP_STAGES"])]
        playoff_df = g[~g["match_stage"].isin(cfg["GROUP_STAGES"])]
        group = group_df["bo_score"].sum()
        playoff = playoff_df["bo_score"].sum()
        win_maps = meta[player]["win_maps"]
        direct_semi = meta[player]["direct_semi"]
        # 长度边际递减: 超出"进淘汰赛最少胜利图数"的部分, 累积总分相对减少
        len_factor = group_length_factor(win_maps, cfg, direct_semi)
        group_eff = group * len_factor
        # 豁免组补偿: 直接进四强的小组第一少打一场 6进4(QF) → 小组分等比上浮后再进软上限.
        # 乘在 cap 之前: 高小组分(撞 cap)增量被上限吸收, 低小组分获得真实补偿
        # (不放大优势 → 不破坏 ropz>ZywOo; 相比固定加分, 补偿量按小组赛表现挂钩).
        if direct_semi and cfg.get("EXEMPT_COMP", 1.0) != 1.0:
            group_eff *= cfg["EXEMPT_COMP"]
        # 小组总分软上限: 豁免组(直接进四强)宽松 / 普通组(打了QF)收紧
        group_capped = group_total_cap(group_eff, cfg, exempt=direct_semi)
        # 淘汰赛总分软上限: 豁免组只打两场不压 / 普通组打了三场(含QF多打)收紧.
        # 纯淘汰赛赛事 (无小组赛) 总分 = 淘汰单段, 不压 (单段不存在两段叠加虚高).
        if has_groups:
            playoff_capped = playoff_total_cap(playoff, cfg, exempt=direct_semi)
        else:
            # 纯淘汰赛赛事 (无小组赛): 淘汰分承担"小组段+淘汰段"两段分量.
            # 不压 (单段无叠加虚高), 并按 NO_GROUP_MULT 补偿缺失的小组段 (默认 1.0=不补偿).
            playoff_capped = playoff * cfg.get("NO_GROUP_MULT", 1.0)
        rows.append({
            "player": player,
            "team": group_df["team"].iloc[0] if len(group_df) else playoff_df["team"].iloc[0],
            "n_bo_games": len(g),
            "group_win_maps": win_maps,
            "group_len_factor": round(len_factor, 4),
            "group_exempt": direct_semi,   # True=直接进四强(宽松上限), False=打了QF(收紧上限)
            "group_bo_total": round(group, 4),
            "group_effective": round(group_eff, 4),
            "group_soft_capped": round(group_capped, 4),
            "playoff_bo_total": round(playoff, 4),
            "playoff_soft_capped": round(playoff_capped, 4),
            "total_score": round(group_capped + playoff_capped, 4),
        })
    s = pd.DataFrame(rows).sort_values("total_score", ascending=False)
    s["rank"] = range(1, len(s) + 1)
    return s


# ----------------------------------------------------------------------
# CS2 mapstats 事件级加成 (2026-09-09 机制, 全候选轴版; 只改 CS2 排序, 见 run_experiment 注入)
# ----------------------------------------------------------------------
# CS2 专属列: 旧 HLTV 统计页 (CS:GO) 不提供 Swing/Rating3/KPRW → CS:GO raw 结构上无下列任
# 一列. 用这组列做触发门槛 = CS:GO 永不触发 (全量扫描 190+ 个 CS:GO raw 无一携带, 已验证).
_CS2_MAPSTAT_REQ = ("map_kprw", "map_won_kills", "map_kpr", "map_dpr", "map_kast",
                    "map_mk_rating", "map_swing_total", "map_adr", "map_rating30")

# 机制轴注册表: axis -> (聚合原始列, 聚合方式). 权重键 = "CS2_<AXIS>_W" (见 CS2_OVERRIDES).
#   "kprw_e" 特殊 (Σwon_kills / Σ(won_kills/kprw)): 需 map_kprw + map_won_kills 双列;
#   其余轴为逐图聚合 (mean 或 sum). 每轴权重带符号, 由搜索/回归定夺 — 不预写死方向.
_CS2_AXES = {
    "kprw_e":    ("map_kprw", "kprw_e"),
    "kprw_avg":  ("map_kprw", "mean"),
    "kpr":       ("map_kpr", "mean"),
    "kast":      ("map_kast", "mean"),
    "mk":        ("map_mk_rating", "mean"),
    "adr":       ("map_adr", "mean"),
    "dpr":       ("map_dpr", "mean"),
    "swing_sum": ("map_swing_total", "sum"),
    "swing_avg": ("map_swing_total", "mean"),
}


def _cs2_active_axes(cfg):
    """读 cfg 中非 0 机制轴权重 → [(axis, weight), ...]. 全 0 → [] (逐位复现基线)."""
    out = []
    for axis in _CS2_AXES:
        w = float(cfg.get(f"CS2_{axis.upper()}_W") or 0.0)
        if w:
            out.append((axis, w))
    return out


def _cs2_zscore(series):
    """事件内 z 标准化. 常数平移不影响排序 (机制只关心选手间差异). 零方差 → 全 0."""
    sd = series.std()
    if not sd or sd != sd:   # None / NaN / 0
        return series * 0.0
    return (series - series.mean()) / sd


def mapstats_player_adjust(raw_df, cfg):
    """CS2 mapstats 选手加成 {player: bonus}. 无激活轴或缺 CS2 列 → {} (逐位复现基线).

    聚合语义 (raw 一行/图, player 昵称与 summary 同源, 直接 dict 对齐):
      每激活轴先聚合成选手级标量, 再事件内 z 标准化; bonus = Σ w_axis · z(axis).
      轴缺失 (raw 无对应列 / 全 NaN) → 该轴跳过, 不阻断其余轴.
    """
    active = _cs2_active_axes(cfg)
    if not active:
        return {}
    if not any(c in raw_df.columns for c in _CS2_MAPSTAT_REQ):
        return {}   # 该 raw 不带任何 CS2 mapstat 列 (CS:GO 情形) → 永不触发
    df = raw_df.dropna(subset=["player"]).copy()
    if df.empty:
        return {}
    player = df["player"]
    feats = pd.DataFrame(index=pd.Index(df["player"].unique(), name="player"))
    for axis, _w in active:
        base_col, agg = _CS2_AXES[axis]
        if base_col not in df.columns:
            continue
        if axis == "kprw_e":
            if "map_won_kills" not in df.columns:
                continue
            won_k = pd.to_numeric(df["map_won_kills"], errors="coerce")
            kprw = pd.to_numeric(df[base_col], errors="coerce")
            ok = won_k.notna() & (kprw > 0)
            wsum = won_k.where(ok).groupby(player).sum()
            rsum = (won_k.where(ok) / kprw.where(ok)).groupby(player).sum()
            rsum = rsum.where(rsum > 0)          # 0 回合 → NaN, 除零保护
            feats[axis] = wsum.div(rsum)         # Σwon_kills / Σ获胜回合数
        else:
            vals = pd.to_numeric(df[base_col], errors="coerce")
            feats[axis] = vals.groupby(player).agg(agg if agg == "sum" else "mean")
    feats = feats.dropna(axis=1, how="all")      # 整列 NaN (该轴无数据) → 弃轴
    if feats.shape[1] == 0:
        return {}
    bonus = pd.Series(0.0, index=feats.index)
    for axis, w in active:
        if axis not in feats.columns:
            continue
        bonus = bonus + w * _cs2_zscore(feats[axis]).fillna(0.0)
    bonus = bonus.replace([float("inf"), float("-inf")], 0.0)
    return {p: float(b) for p, b in bonus.items() if b and b == b}

# ----------------------------------------------------------------------
# 中间产物: 每场BO每个选手的逐图给分明细
# ----------------------------------------------------------------------
def build_bo_details(map_all, bo_all, cfg):
    """每行 = 一个选手在一场 BO 中: 每张图给分 + 原始Σ + 实际给分(软上限后)"""
    # 每张图分转成宽表列 图1分/图2分/...
    map_pivot = map_all.pivot_table(
        index=["bo_id", "player", "team", "opponent", "match_stage"],
        columns="map_idx", values="map_score", aggfunc="first"
    ).reset_index()
    map_pivot.columns = [str(c) if isinstance(c, int) else c for c in map_pivot.columns]
    map_pivot = map_pivot.rename(columns={str(i): f"图{i}分" for i in range(1, 6)})

    det = map_pivot.merge(
        bo_all[["bo_id", "player", "nmaps", "cap", "map_sum", "bo_score"]],
        on=["bo_id", "player"], how="left"
    )
    det["cut_ratio"] = (det["bo_score"] / det["map_sum"]).round(3).where(det["map_sum"] != 0)
    # 软 cap: 原始分超过 cap 参考点 → 视为被压缩 (不再有 bo_score==cap 的硬命中)
    det["capped"] = det["map_sum"] > det["cap"]
    det["floored"] = det["bo_score"] == cfg["BO_FLOOR"]
    det = det.sort_values(["match_stage", "bo_id"])
    return det

# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------
def run_experiment(raw_path, out_path, details_path, cfg=EVP_CONFIG, save=True, raw_df=None):
    """save=False 为评估模式: 只计算不写盘 (调优搜索提速, 原 run_experiment 行为不变).
    raw_df: 预读缓存的原始 df (多进程搜索用, 避免每个 worker 重复读磁盘). None 则按路径读.
    """
    if raw_df is None:
        print(f"读取: {raw_path}")
        raw_df = pd.read_excel(raw_path)
    df = raw_df
    print(f"总行数: {len(df)}, 阶段: {dict(df['match_stage'].value_counts())}")

    # 层1
    bos = split_into_bos(df)
    print(f"识别到 BO 对决: {len(bos)} 场")

    # 先算单图层 map_all (compute_meta 需要), 再带 meta 聚合 BO 分 (豁免组/普通组双轨)
    map_rows = []
    for (bo_id, pair, bo_df) in bos:
        map_df, nmaps = map_scores_for_bo(bo_id, bo_df, cfg)
        map_rows.append(map_df)
    map_all = pd.concat(map_rows, ignore_index=True)

    # 层5 前置: meta (豁免组/普通组判定, 供小组 BO 超额斜率 + 长度惩罚共用)
    meta = compute_meta(map_all, cfg)
    # 每次运行先确定长度惩罚基准线: 晋级淘汰赛最少胜利地图数 (自动从数据推导)
    min_win_maps = determine_min_win_maps(map_all, cfg, meta=meta)
    print(f"确定长度惩罚基准: 晋级淘汰赛最少胜利地图数 MIN_WIN_MAPS = {min_win_maps} "
          f"({'显式指定' if cfg.get('MIN_WIN_MAPS') is not None else '自动推导'})")

    bo_rows = []
    for bo_id in map_all["bo_id"].unique():
        md = map_all[map_all["bo_id"] == bo_id]
        bo_rows.append(aggregate_bo_scores(md, cfg, meta=meta))
    bo_all = pd.concat(bo_rows, ignore_index=True)

    # 层5 选手汇总
    summary = summarize_players(bo_all, map_all, cfg, meta=meta)

    # --- CS2 mapstats 事件级加成注入 (2026-09-09; 默认全 0 或 CS:GO 无列 → 本块空转,
    #     summary 逐位等于 summarize_players 输出, 精确复现基线) ---
    # 机制叠加在 total_score 后重排: 不改单图/BO 层与 CS:GO 共享的已调优 caps/乘子.
    _adj = mapstats_player_adjust(df, cfg)
    if _adj:
        summary["total_score"] = summary["total_score"] + summary["player"].map(_adj).fillna(0.0)
        summary["total_score"] = summary["total_score"].round(4)
        summary = summary.sort_values("total_score", ascending=False).reset_index(drop=True)
        summary["rank"] = range(1, len(summary) + 1)

    # 中间产物: 每场BO逐图给分明细
    details = build_bo_details(map_all, bo_all, cfg)
    if save:
        details.to_excel(details_path, index=False, sheet_name="BO逐图给分明细")
        print(f"已输出中间产物: {details_path} ({len(details)} 行)")

        # 输出汇总表
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            summary.to_excel(writer, index=False, sheet_name="选手汇总")
            bo_all.to_excel(writer, index=False, sheet_name="BO_明细")
            map_all.to_excel(writer, index=False, sheet_name="单图给分")
        print(f"已输出新表: {out_path}")
    return summary, bo_all, map_all, details


if __name__ == "__main__":
    raw = "/home/hongbin/Desktop/hltv/database/event/8240/raw_event_8240_data.xlsx"
    # 中间产物与 raw 同级存放, 便于查找
    out = "/home/hongbin/Desktop/hltv/database/event/8240/experiment_8240_evp_new.xlsx"
    details_path = "/home/hongbin/Desktop/hltv/database/event/8240/experiment_8240_bo_details.xlsx"
    summary, bo_all, map_all, details = run_experiment(raw, out, details_path)
    print("\n=== 选手汇总 Top 15 ===")
    print(summary.head(15).to_string(index=False))
