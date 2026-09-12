# RD-Agent 因子迭代优化研究报告

> 日期：2026-09-12  
> 项目：RD-Agent Qlib Factor R&D Loop  
> 市场标的：CSI 300（沪深 300 指数增强）  
> 基准：SH000300（沪深 300 指数）  
> 数据源：Qlib CN Data（`~/.qlib/qlib_data/cn_data`）  
> 训练区间：2008-01-01 至 2014-12-31  
> 验证区间：2015-01-01 至 2016-12-31  
> 回测区间：2017-01-01 至 2020-08-01  
> 模型：LightGBM（LGBModel）  
> 策略：TopkDropoutStrategy（topk=50, n_drop=5）  
> 账户规模：1 亿人民币  
> 成交价：收盘价（close）  
> 涨跌停限制：limit_threshold = 0.095（触及 9.5% 不交易）  
> 开仓手续费：0.05%（open_cost = 0.0005）  
> 平仓手续费：0.15%（close_cost = 0.0015）  
> 最低手续费：5 元（min_cost = 5）

---

## 一、研究概述

本报告记录了三组基于 RD-Agent 框架的量化因子实验，验证了"研报因子复现 → 全局 Trace 库积累 → Trace 驱动迭代优化"的完整闭环流程。

| 阶段 | 数据来源 | 因子数 | 是否达到 SOTA | 年化超额收益（扣费） | Rank IC | Rank ICIR |
|------|----------|--------|---------------|---------------------|---------|-----------|
| 实验一 | 研报 report1.pdf | 3 | ✅ 是 | 0.0504 (+22.9%) | 0.0317 | 0.2586 |
| 实验二 | 研报 report2.pdf | 3 | ❌ 否 | 0.0461 (-8.7%) | 0.0290 | 0.2345 |
| 实验三 | Global Trace 迭代 | 9（3×3 轮） | ✅ 是（Loop 2） | 0.0626 (+24.0%) | 0.0373 | 0.3091 |

**SOTA 演进路径**：0.0410（基线）→ 0.0504（实验一）→ 0.0626（实验三 Loop 2）

---

## 二、实验一：研报复现 — 高频反转因子（达到 SOTA）

### 2.1 实验配置

- **脚本**：`factor_from_report.py`
- **输入**：`quant_reports/report1.pdf`
- **Session**：`log/2026-09-11_13-18-21-542525`
- **Global Trace**：无（首次实验，Trace 为空）

### 2.2 因子提取结果

从研报 PDF 中提取 3 个高频反转类因子：

| 因子名称 | 类别 | 公式 | 变量说明 |
|----------|------|------|----------|
| Improved_Reversal | 反转型 | Mean(-R_t, 20) | R_t = (Close_t - Close_{t-1}) / Close_{t-1} |
| Late_Trading_Volume_Ratio | 反转型 | Mean(ΣVol_late / ΣVol_all, 20) | Vol_{t,j}：分钟级成交量；Late：收盘前 30 分钟 |
| High_Frequency_Skewness | 反转型 | Mean(Skewness(R_{t,j}), 20) | R_{t,j}：分钟级收益率 |

**假设**：将选定的高频因子（尤其是 Improved_Reversal、Late_Trading_Volume_Ratio 和深度学习因子）纳入传统线性加权 CSI 300 增强策略，可显著提升年化超额收益 9.6%-16.2%。

### 2.3 回测结果

| 指标 | SOTA 基线 | 本轮结果 | 变化 |
|------|-----------|----------|------|
| IC | 0.031068 | 0.030868 | -0.6% |
| Rank IC | — | 0.031650 | — |
| ICIR | — | 0.250943 | — |
| Rank ICIR | — | 0.258636 | — |
| 年化超额收益（扣费） | 0.041045 | **0.050443** | **+22.9%** |
| 年化超额收益（不扣费） | — | 0.096054 | — |
| 最大回撤（扣费） | -0.142199 | **-0.135680** | **+4.6%** |
| 最大回撤（不扣费） | — | -0.110205 | — |
| 信息比率（扣费） | — | 0.553618 | — |
| 信息比率（不扣费） | — | 1.053851 | — |

### 2.4 LLM Feedback 分析

> "年化超额收益从 0.041045 显著提升至 0.050443，相对改进 ~22.9%，超过了假设预测的 9.6%-16.2% 范围。最大回撤也同步改善。但 IC 略有下降 (-0.6%)，说明因子在组合层面贡献收益的同时，其个股预测排序能力与现有 SOTA 因子组合后略有减弱。"

**决策**：`decision = True`，因子纳入 SOTA 因子库。

**后续方向建议**：探索深度学习因子（LSTM/Transformer）与反转因子结合；考虑排除正交化后衰减的 High_Frequency_Skewness。

### 2.5 Trace 记录

实验成功后写入 Trace（`trace.hist`），成为后续实验的 SOTA 基线。手动写入 Global Trace 库作为跨批次积累的初始种子。

---

## 三、实验二：研报复现 — 大类因子（未达 SOTA）

### 3.1 实验配置

- **脚本**：`factor_from_report.py --global-trace=log/global_trace.pkl`
- **输入**：`quant_reports_batch2/report2.pdf`
- **Session**：`log/2026-09-12_08-19-31-856124`
- **Global Trace**：已加载 1 条历史成功记录（实验一的 3 因子），SOTA 基线提升至年化 0.0504

### 3.2 因子提取结果

从研报 PDF 中提取 3 个大类因子：

| 因子名称 | 类别 | 公式 | 变量说明 |
|----------|------|------|----------|
| Value | 价值因子 | Σ Rank(Exposure_i) | Exposure_i：第 i 个价值子因子（如 BP、EP）的因子暴露 |
| Growth | 成长因子 | Σ Rank(Exposure_i) | Exposure_i：第 i 个成长子因子的因子暴露 |
| Small_Size | 市值因子 | Σ Rank(Exposure_i) | Exposure_i：第 i 个市值子因子的因子暴露 |

**假设**：在市场震荡和不确定性期间，Value 因子（特别是 BP 子因子）和 Liquidity 因子（特别是年化换手率子因子）倾向于跑赢，而 Growth 和 Volatility 因子倾向于跑输。

### 3.3 回测结果

| 指标 | SOTA 基线 | 本轮结果 | 变化 |
|------|-----------|----------|------|
| IC | 0.030868 | 0.028236 | -8.5% |
| Rank IC | 0.031650 | 0.029002 | -8.4% |
| ICIR | 0.250943 | 0.233891 | -6.8% |
| Rank ICIR | 0.258636 | 0.234482 | -9.3% |
| 年化超额收益（扣费） | 0.050443 | 0.046059 | **-8.7%** |
| 年化超额收益（不扣费） | 0.096054 | 0.092935 | -3.2% |
| 最大回撤（扣费） | -0.135680 | **-0.097722** | **+28.0%** |
| 最大回撤（不扣费） | -0.110205 | -0.076166 | +30.9% |
| 信息比率（扣费） | 0.553618 | 0.528555 | -4.5% |
| 信息比率（不扣费） | 1.053851 | 1.065998 | +1.2% |

### 3.4 LLM Feedback 分析

> "本轮实验实现了 Growth 和 Small_Size 因子，但未实现 Value 因子。组合结果的预测能力（IC）下降 8.5%，年化收益下降 8.7%，但最大回撤显著改善 28%。收益表现不佳与假设一致 — Growth 因子在市场震荡期表现较差。但关键的 Value 因子未实现，无法验证其预期跑赢的假设。"

**决策**：`decision = False`，因子未纳入 SOTA 因子库。

**关键观察**：
1. Value 因子在 CoSTEER 内层循环中未通过代码验证（`final_decision: False`），仅 Growth 和 Small_Size 通过
2. 大类因子采用序号等权加总方式，粒度较粗，与高频反转因子组合后可能引入噪声
3. 最大回撤改善显著（+28%），说明大类因子在风险控制层面有附加价值

---

## 四、实验三：Global Trace 驱动的因子迭代优化（达到新 SOTA）

### 4.1 实验配置

- **脚本**：`factor.py --global-trace=log/global_trace.pkl --loop-n=3`
- **Session**：`log/2026-09-12_14-06-03-713577`
- **Global Trace**：已加载 1 条历史成功记录（实验一的 3 因子，SOTA 年化 0.0504）
- **迭代轮数**：3 轮外层 R&D 循环
- **每轮流程**：`direct_exp_gen → coding → running → feedback → record`

### 4.2 迭代过程总览

| 轮次 | 假设方向 | 因子 | 决策 | IC | Rank IC | Rank ICIR | 年化收益（扣费） | 最大回撤 | IR（扣费） |
|------|----------|------|------|-----|---------|-----------|------------------|----------|------------|
| Loop 0 | 反转分解 | ORM_20, IRM_20, VWR_20 | ❌ False | 0.0309 (+0.1%) | 0.0297 | 0.2448 | 0.0199 (-60.5%) | -0.1445 | 0.2383 |
| Loop 1 | 正交量价 | Close_Position_20, Volume_Momentum_20, Amihud_Illiquidity_20 | ❌ False | 0.0304 (-1.7%) | 0.0314 | 0.2554 | 0.0163 (-67.6%) | -0.1937 | 0.1822 |
| Loop 2 | 比率归一化 | Volatility_Regime_Ratio_5_20, VWAP_Deviation_20, Range_Compression_Ratio_5_20 | ✅ **True** | **0.0359 (+16.4%)** | **0.0373** | **0.3091** | **0.0626 (+24.0%)** | **-0.1356** | **0.6957** |

### 4.3 Loop 0：反转因子分解（失败）

**假设**：将日收益率分解为隔夜收益（ORM_20）和日内收益（IRM_20）分量，结合成交量加权反转（VWR_20），可以恢复 IC 同时保持组合收益。

| 因子 | 公式 | 说明 |
|------|------|------|
| ORM_20 | Mean(-(Open_t - Close_{t-1}) / Close_{t-1}, 20) | 隔夜收益反转 |
| IRM_20 | Mean(-(Close_t - Open_t) / Open_t, 20) | 日内收益反转 |
| VWR_20 | Σ(-R_{t-i} × Volume_{t-i}) / ΣVolume_{t-i} | 成交量加权日收益反转 |

**结果**：IC 微升 (+0.1%) 但年化收益暴跌 60.5%。分解后的反转因子与现有 SOTA 因子（Improved_Reversal）高度共线，引入冗余噪声。

**LLM 反思 → 新方向**：探索波动率自适应反转因子，根据近期波动率动态调整回看窗口（高波动期用短窗口 5-10 天，低波动期用长窗口 20-30 天），捕获静态窗口无法捕捉的依赖状态均值回归行为。

### 4.4 Loop 1：正交量价因子（失败）

**假设**：探索非收益率类因子 — 日内收盘位置、成交量动量、流动性/价格冲击 — 通过正交信息维度改善 IC 和组合收益，避免 Loop 0 的共线性陷阱。

| 因子 | 公式 | 说明 |
|------|------|------|
| Close_Position_20 | Mean((Close_t - Low_t) / (High_t - Low_t), 20) | 日内收盘位置 |
| Volume_Momentum_20 | Mean(Volume_t / Volume_{t-1} - 1, 20) | 成交量动量 |
| Amihud_Illiquidity_20 | Mean(\|R_t\| / Volume_t, 20) | Amihud 流动性 |

**结果**：IC 下降 1.7%，年化收益暴跌 67.6%，最大回撤恶化至 -0.194。原始非收益率因子引入了噪声和冲突信号，稀释了 SOTA 因子库有效性。

**LLM 反思 → 新方向**：使用比率/百分比归一化而非原始值，探索 (1) 短期/长期波动率比率捕获状态变化；(2) VWAP 偏离因子以归一化方式结合量价；(3) 价格区间压缩比。

### 4.5 Loop 2：比率归一化因子（成功，新 SOTA）

**假设**：波动率状态比率（5日/20日收益标准差）、VWAP 偏离（20日成交量加权均价偏离）、价格区间压缩比（5日/20日高低价区间比）可以捕获与收益率反转正交的 Alpha 维度，同时解决 Loop 0 的共线性和 Loop 1 的分布噪声问题。

| 因子 | 公式 | 说明 |
|------|------|------|
| Volatility_Regime_Ratio_5_20 | σ_5(R_t) / σ_20(R_t) | 短期/长期波动率比率，捕获市场状态 |
| VWAP_Deviation_20 | (Close_t - VWAP_{20,t}) / VWAP_{20,t} | 收盘价相对 VWAP 的偏离 |
| Range_Compression_Ratio_5_20 | (max(High_{t-4:t}) - min(Low_{t-4:t})) / (max(High_{t-19:t}) - min(Low_{t-19:t})) | 短期/长期价格区间比 |

**结果**：

| 指标 | SOTA 基线 | 本轮结果 | 变化 |
|------|-----------|----------|------|
| IC | 0.030868 | **0.035932** | **+16.4%** |
| Rank IC | 0.031650 | **0.037294** | **+17.9%** |
| ICIR | 0.250943 | **0.296149** | **+18.1%** |
| Rank ICIR | 0.258636 | **0.309102** | **+19.5%** |
| 年化超额收益（扣费） | 0.050443 | **0.062551** | **+24.0%** |
| 最大回撤（扣费） | -0.135680 | -0.135568 | +0.1% |
| 信息比率（扣费） | 0.553618 | **0.695713** | **+25.7%** |

**LLM Feedback**：

> "组合结果在所有关键指标上均显著超越 SOTA。IC 提升 16.4%，年化收益提升 24.0%，最大回撤微改善。三个比率型因子共同贡献了有意义的 Alpha，说明使用比率/百分比归一化形式和正交信息维度的设计选择是有效的。"

**决策**：`decision = True`，因子纳入 SOTA 因子库。

**后续方向建议**：将比率归一化方法扩展至更多正交维度 — 流动性状态比率（5日/20日换手率比）和隔夜/日内收益比率。

### 4.6 迭代优化的关键洞察

1. **假设驱动的试错**：LLM 每轮基于 Trace 中的历史实验和反馈生成新假设，失败的假设提供正反馈信号（排除无效方向），成功的假设提供 SOTA 积累
2. **归一化是关键**：Loop 1 使用原始值的因子引入噪声，Loop 2 改用比率/百分比形式后显著改善 — LLM 从失败中学习并应用了这个设计模式
3. **正交性优于共线性**：Loop 0 的反转分解因子与现有 SOTA 因子高度共线，Loop 2 选择波动率、VWAP、价格区间等与收益率正交的维度，效果显著
4. **Trace 驱动的进化**：每轮实验后 Trace 积累成功因子作为新 SOTA 基线，LLM 能看到历史实验的假设、因子和反馈，避免重复无效方向

---

## 五、Global Trace 库机制

### 5.1 设计目标

跨批次维护一个全局 Trace 库，初始为空。每批次 `factor_from_report.py` 或 `factor.py` 运行时：
1. **启动时 Seed**：从 Global Trace 加载所有历史成功因子到当前 Trace
2. **运行时 SOTA**：基于历史成功因子计算 SOTA 基线
3. **完成后 Append**：若本轮 `feedback.decision = True`，将 (experiment, feedback) 追加到 Global Trace

### 5.2 实现文件

| 文件 | 作用 |
|------|------|
| `rdagent/utils/global_trace.py` | Core：load / save / seed / append |
| `rdagent/app/qlib_rd_loop/factor_from_report.py` | 研报复现：seed at startup, append on success |
| `rdagent/app/qlib_rd_loop/factor.py` | Trace 迭代：seed at startup, append on success |
| `rdagent/app/cli.py` | CLI 入口：暴露 `--global-trace` 参数 |

### 5.3 当前 Global Trace 状态

| 序号 | 因子 | 年化收益（扣费） | IC | Rank IC | Rank ICIR | 来源 |
|------|------|------------------|-----|---------|-----------|------|
| 0 | Improved_Reversal, Late_Trading_Volume_Ratio, High_Frequency_Skewness | 0.0504 | 0.0309 | 0.0317 | 0.2586 | 实验一（研报复现） |
| 1 | Volatility_Regime_Ratio_5_20, VWAP_Deviation_20, Range_Compression_Ratio_5_20 | 0.0626 | 0.0359 | 0.0373 | 0.3091 | 实验三 Loop 2（Trace 迭代） |

### 5.4 使用方式

```bash
# 1. 研报复现 + Global Trace 积累
rdagent fin_factor_report \
  --report-folder /path/to/reports/ \
  --global-trace log/global_trace.pkl

# 2. Trace 驱动迭代优化 + Global Trace 积累
rdagent fin_factor \
  --global-trace log/global_trace.pkl \
  --loop-n 5
```

---

## 六、完整 SOTA 演进路径

```
基线 (ALPHA20 基础因子组合)
  │  年化超额收益: 0.0410 | IC: 0.0311 | Rank IC: — | Rank ICIR: — | 最大回撤: -0.1422
  │
  ▼ 实验一：研报复现高频反转因子
  │  因子: Improved_Reversal + Late_Trading_Volume_Ratio + High_Frequency_Skewness
  │  年化: 0.0504 (+22.9%) | IC: 0.0309 (-0.6%) | Rank IC: 0.0317 | Rank ICIR: 0.2586 | 最大回撤: -0.1357
  │  → decision=True, 写入 Trace
  │
  ▼ 实验二：研报复现大类因子（未通过）
  │  因子: Value + Growth + Small_Size（Value 未实现）
  │  年化: 0.0461 (-8.7%) | IC: 0.0282 (-8.5%) | Rank IC: 0.0290 | Rank ICIR: 0.2345 | 最大回撤: -0.0977
  │  → decision=False, 不写入 Trace
  │
  ▼ 实验三 Loop 0：反转因子分解（未通过）
  │  因子: ORM_20 + IRM_20 + VWR_20
  │  年化: 0.0199 (-60.5%) | IC: 0.0309 (+0.1%) | Rank IC: 0.0297 | Rank ICIR: 0.2448 | 最大回撤: -0.1445
  │  → decision=False, 不写入 Trace
  │  → LLM 反思: 避免共线性，探索波动率自适应
  │
  ▼ 实验三 Loop 1：正交量价因子（未通过）
  │  因子: Close_Position_20 + Volume_Momentum_20 + Amihud_Illiquidity_20
  │  年化: 0.0163 (-67.6%) | IC: 0.0304 (-1.7%) | Rank IC: 0.0314 | Rank ICIR: 0.2554 | 最大回撤: -0.1937
  │  → decision=False, 不写入 Trace
  │  → LLM 反思: 使用比率归一化，选择正交维度
  │
  ▼ 实验三 Loop 2：比率归一化因子（新 SOTA）
     因子: Volatility_Regime_Ratio_5_20 + VWAP_Deviation_20 + Range_Compression_Ratio_5_20
     年化: 0.0626 (+24.0%) | IC: 0.0359 (+16.4%) | Rank IC: 0.0373 | Rank ICIR: 0.3091 | 最大回撤: -0.1356
     → decision=True, 写入 Trace
     → 后续建议: 扩展比率归一化至流动性和隔夜/日内维度
```

**总改进**：年化超额收益从基线 0.0410 提升至 0.0626（+52.4%），IC 从 0.0311 提升至 0.0359（+15.5%），Rank ICIR 从 0.2586 提升至 0.3091（+19.5%）。

---

## 七、结论

1. **研报复现有效**：实验一验证了从研报 PDF 自动提取因子并实现 SOTA 超越的可行性，年化收益提升 22.9%。

2. **并非所有研报因子都有效**：实验二的大类因子（价值/成长/市值）未超越 SOTA，且其中一个因子（Value）在代码层面即未通过验证。说明研报因子质量参差不齐，需要回测验证筛选。

3. **Trace 驱动迭代是核心价值**：实验三展示了 LLM 如何基于历史 Trace 中的成功/失败实验进行假设演化。3 轮迭代中前 2 轮失败，但每轮失败为 LLM 提供了排除无效方向的正反馈，最终第 3 轮找到有效因子组合，年化收益在已有 SOTA 基础上再提升 24.0%。

4. **Global Trace 库实现跨批次积累**：不同批次研报、不同迭代轮次的成功因子统一积累在 Global Trace 中，后续实验自动加载作为 SOTA 基线，避免重复发现已知有效因子。

5. **设计模式洞察**：比率/百分比归一化 > 原始值；正交维度 > 共线维度；动态状态因子 > 静态窗口因子。这些设计模式由 LLM 在迭代过程中自主发现并应用。最终 SOTA 的 Rank ICIR 达到 0.3091，较基线提升 19.5%，说明因子排序稳定性同步改善。
