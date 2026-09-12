# Global Trace 库内容详解

> 日期：2026-09-12  
> 项目：RD-Agent Qlib Factor R&D Loop  
> 文件路径：`log/global_trace.pkl`  
> 序列化格式：`RDAGENT_SIGNED_PICKLE_V1`（需用 `rdagent.core.serialization.loads()` 解析）

---

## 一、数据结构概览

Global Trace 本质上是一个 `list[(Experiment, ExperimentFeedback)]`，每条 entry 对应一次 `decision=True` 的成功实验。当前包含 **2 条 entry**：

| 序号 | 来源 | 因子数 | 年化超额收益（扣费） | IC | Rank IC | Rank ICIR |
|------|------|--------|---------------------|-----|---------|-----------|
| 0 | 实验一（研报复现） | 3 | 0.0504 | 0.0309 | 0.0317 | 0.2586 |
| 1 | 实验三 Loop 2（Trace 迭代） | 3 | 0.0626 | 0.0359 | 0.0373 | 0.3091 |

每条 entry 包含四个层次的信息：

```
Entry
├── ExperimentFeedback（反馈层）
├── Experiment（实验层）
│   ├── Hypothesis（假设对象）
│   ├── base_features（20 个基础 Qlib 因子算子）
│   ├── based_experiments（依赖的历史 SOTA 实验链）
│   ├── sub_tasks[3]（因子定义层）
│   │   └── FactorTask（每个因子一个）
│   └── sub_workspace_list[3]（代码层）
│       └── Workspace（含 factor.py 完整源码）
```

---

## 二、Entry 0：高频反转因子（实验一）

### 2.1 反馈层 (ExperimentFeedback)

| 字段 | 值 |
|------|-----|
| `decision` | True |
| `reason` | "The current results demonstrate that high-frequency reversal factors add significant value at the portfolio level, but the slight IC decline indicates room for improvement in factor-level predictive power..." |
| `code_change_summary` | — |
| `eda_improvement` | — |
| `exception` | None |

### 2.2 假设 (Hypothesis)

> **假设**：将选定的高频因子（尤其是 Improved_Reversal、Late_Trading_Volume_Ratio 和深度学习因子）纳入传统线性加权 CSI 300 增强策略，可显著提升年化超额收益 9.6%-16.2%。
>
> **推理**：研报表明高频因子已成为量化选股不可或缺的 alpha 来源，尤其是在中小盘股池如 CSI 300 中。关键观察：(1) 在反转类高频因子中，Improved_Reversal 和 Late_Trading_Volume_Ratio 在与基础因子正交化后仍保持或提升预测力；(2) 周度再平衡下，反转和动量高频因子的年化多空超额收益为 15%-20%；(3) 引入增强策略后年化超额收益稳定在 24% 以上；(4) 基本面因子（Profitability、SUE）在短预测周期下仍有益。

### 2.3 实验层 (Experiment)

| 字段 | 值 |
|------|-----|
| `sub_tasks` 数量 | 3 |
| `based_experiments` 数量 | 1（基线实验） |
| `base_features` 数量 | 20 个 Qlib 算子因子 |

**base_features（前 5 个示例）**：

| 名称 | 算子表达式 |
|------|-----------|
| RESI5 | `Resi($close, 5)/$close` |
| WVMA5 | `Std(Abs($close/Ref($close, 1)-1)*$volume, 5)/(Mean(...)+1e-12)` |
| RSQR5 | `Rsquare($close, 5)` |
| KLEN | `($high-$low)/$open` |
| RSQR10 | `Rsquare($close, 10)` |

完整 20 个：RESI5, WVMA5, RSQR5, KLEN, RSQR10, CORR5, CORD5, CORR10, ROC60, RESI10, VSTD5, RSQR60, CORR60, WVMA60, STD5, RSQR20, CORD60, CORD10, CORR20, KLOW

### 2.4 因子定义层 (FactorTask × 3)

#### Task 0：Improved_Reversal

| 字段 | 内容 |
|------|------|
| factor_name | `Improved_Reversal` |
| formulation | `\text{Improved\_Reversal} = \text{Mean}(-R\_t, 20)` |
| variables | `Mean`: 过去 20 日均值函数; `R_t`: 日收益率 (Close_t - Close_{t-1})/Close_{t-1}; `Close_t`: 收盘价 |
| description | 反转型高频因子，计算过去 20 日的均值，刻画投资者过度反应的行为特征 |
| implementation | True |

#### Task 1：Late_Trading_Volume_Ratio

| 字段 | 内容 |
|------|------|
| factor_name | `Late_Trading_Volume_Ratio` |
| formulation | `\text{Mean}\left(\frac{\sum_{j \in \text{Late}} \text{Volume}_{t,j}}{\sum_{j \in \text{All}} \text{Volume}_{t,j}}, 20\right)` |
| variables | `Mean`: 20 日均值; `Volume_{t,j}`: 分钟级成交量; `Late`: 收盘前 30 分钟; `All`: 全日所有交易分钟 |
| description | 反转型高频因子，正交化后有效性和稳定性显著提升 |
| implementation | True |

#### Task 2：High_Frequency_Skewness

| 字段 | 内容 |
|------|------|
| factor_name | `High_Frequency_Skewness` |
| formulation | `\text{Mean}(\text{Skewness}(R\_{t,j}), 20)` |
| variables | `Mean`: 20 日均值; `Skewness`: 日内收益率偏度; `R_{t,j}`: 分钟级收益率; `Close_{t,j}`: 分钟级收盘价 |
| description | 反转型高频因子，正交化后性能显著下降 |
| implementation | True |

### 2.5 代码层 (Workspace × 3)

每个 Workspace 包含 `file_dict: {'factor.py': '...'}`，即完整可运行的 Python 因子代码。

#### Improved_Reversal — factor.py

```python
import pandas as pd
import numpy as np

def calculate_improved_reversal():
    df = pd.read_hdf("daily_pv.h5", key="data")
    df = df.sort_index()

    # 日收益率: R_t = (Close_t - Close_{t-1}) / Close_{t-1}
    df['return'] = df.groupby('instrument')['$close'].pct_change()
    df['neg_return'] = -df['return']

    # Mean(-R_t, 20)
    df['Improved_Reversal'] = df.groupby('instrument')['neg_return'].transform(
        lambda x: x.rolling(window=20).mean()
    )

    result = df[['Improved_Reversal']].copy()
    result = result.dropna()
    result.to_hdf("result.h5", key="data")
    return result

if __name__ == "__main__":
    calculate_improved_reversal()
```

#### Late_Trading_Volume_Ratio — factor.py

```python
import pandas as pd
import numpy as np

def calculate_late_trading_volume_ratio():
    df = pd.read_hdf("daily_pv.h5", key="data")
    df = df.sort_index()

    # $factor 列包含预计算的尾盘成交量占比（尾盘成交量/全天成交量）
    # Late_Trading_Volume_Ratio = Mean(ratio_t, 20)
    df['Late_Trading_Volume_Ratio'] = df.groupby('instrument')['$factor'].transform(
        lambda x: x.rolling(window=20).mean()
    )

    result = df[['Late_Trading_Volume_Ratio']].copy()
    result = result.dropna()
    result.to_hdf("result.h5", key="data")
    return result

if __name__ == "__main__":
    calculate_late_trading_volume_ratio()
```

#### High_Frequency_Skewness — factor.py

```python
import pandas as pd
import numpy as np

def calculate_high_frequency_skewness():
    df = pd.read_hdf("daily_pv.h5", key="data")

    # 用 OHLC 构造 3 个日内收益率作为分钟级近似
    open_price = df['$open'].astype(np.float64)
    high_price = df['$high'].astype(np.float64)
    low_price = df['$low'].astype(np.float64)
    close_price = df['$close'].astype(np.float64)

    R1 = (high_price - open_price) / open_price   # 开盘到最高
    R2 = (low_price - high_price) / high_price     # 最高到最低
    R3 = (close_price - low_price) / low_price     # 最低到收盘

    R1 = R1.replace([np.inf, -np.inf], np.nan)
    R2 = R2.replace([np.inf, -np.inf], np.nan)
    R3 = R3.replace([np.inf, -np.inf], np.nan)

    returns = np.column_stack([R1.values, R2.values, R3.values])

    # 总体偏度 = m3 / m2^(3/2)
    with np.errstate(invalid='ignore', divide='ignore'):
        mean_vals = np.mean(returns, axis=1, keepdims=True)
        deviations = returns - mean_vals
        m2 = np.mean(deviations**2, axis=1)
        m3 = np.mean(deviations**3, axis=1)
        std = np.sqrt(m2)
        daily_skewness = np.where(std > 1e-10, m3 / (std**3), np.nan)

    df['daily_skewness'] = daily_skewness

    # Mean(Skewness, 20)
    df['High_Frequency_Skewness'] = df.groupby('instrument')['daily_skewness'].rolling(20).mean().reset_index(level=0, drop=True)

    result = df[['High_Frequency_Skewness']].copy()
    result = result.dropna()
    result.to_hdf("result.h5", key="data")
    return result

if __name__ == "__main__":
    calculate_high_frequency_skewness()
```

---

## 三、Entry 1：比率归一化因子（实验三 Loop 2）

### 3.1 反馈层 (ExperimentFeedback)

| 字段 | 值 |
|------|-----|
| `decision` | True |
| `reason` | "The success of the ratio-based formulation approach (normalizing distributions, bounding values, centering around meaningful thresholds) suggests this methodology can be applied to other information dimensions..." |
| `exception` | None |

### 3.2 假设 (Hypothesis)

> **假设**：波动率状态比率（5日/20日收益标准差）、VWAP 偏离（20日成交量加权均价偏离）、价格区间压缩比（5日/20日高低价区间比）可以捕获与收益率反转正交的 Alpha 维度，同时解决 Loop 0 的共线性和 Loop 1 的分布噪声问题。
>
> **推理**：这三个因子天然归一化（比率在 1 附近或百分比偏离在 0 附近），与收益率反转真正正交（使用波动率幅度、量价加权价格、日内区间而非收益方向），且有强学术支撑。Loop 0 失败因为分解收益率引入共线性，Loop 1 失败因为原始未归一化因子分布极端——这些因子通过使用不同数据维度和内在归一化解决了两个问题。

### 3.3 实验层 (Experiment)

| 字段 | 值 |
|------|-----|
| `sub_tasks` 数量 | 3 |
| `based_experiments` 数量 | 2（Entry 0 的 SOTA + 空基线） |
| `base_features` 数量 | 20（与 Entry 0 相同） |

### 3.4 因子定义层 (FactorTask × 3)

#### Task 0：Volatility_Regime_Ratio_5_20

| 字段 | 内容 |
|------|------|
| factor_name | `Volatility_Regime_Ratio_5_20` |
| formulation | `\frac{\sigma_5(R_t)}{\sigma_{20}(R_t)}` |
| variables | `σ_5`: 5 日滚动标准差 (min_periods=5); `σ_20`: 20 日滚动标准差 (min_periods=20); `R_t`: 日收益率; `Close_t`: 收盘价 |
| description | 波动率因子，5日/20日波动率比率，捕获市场状态变化 |
| implementation | True |

#### Task 1：VWAP_Deviation_20

| 字段 | 内容 |
|------|------|
| factor_name | `VWAP_Deviation_20` |
| formulation | `\frac{\text{Close}_t - \text{VWAP}_{20,t}}{\text{VWAP}_{20,t}}` |
| variables | `VWAP_{20,t}`: 20 日成交量加权均价 = Σ(Close×Volume)/Σ(Volume); `Close_t`: 收盘价; `Volume_i`: 成交量 |
| description | 量价因子，收盘价相对 VWAP 的百分比偏离 |
| implementation | True |

#### Task 2：Range_Compression_Ratio_5_20

| 字段 | 内容 |
|------|------|
| factor_name | `Range_Compression_Ratio_5_20` |
| formulation | `\frac{\max(\text{High}_{t-4:t}) - \min(\text{Low}_{t-4:t})}{\max(\text{High}_{t-19:t}) - \min(\text{Low}_{t-19:t})}` |
| variables | `max(High_{t-4:t})`: 5 日最高价最大值; `min(Low_{t-4:t})`: 5 日最低价最小值; `max(High_{t-19:t})`: 20 日最高价最大值; `min(Low_{t-19:t})`: 20 日最低价最小值 |
| description | 区间因子，5日/20日价格区间压缩比，短期区间相对长期区间的比率 |
| implementation | True |

### 3.5 代码层 (Workspace × 3)

#### Volatility_Regime_Ratio_5_20 — factor.py

```python
import pandas as pd
import numpy as np

def calculate_volatility_regime_ratio_5_20():
    df = pd.read_hdf("daily_pv.h5", key="data")
    df = df.sort_index()

    # 日收益率
    df['return'] = df.groupby('instrument')['$close'].pct_change()

    # 5 日滚动标准差 (min_periods=5)
    df['sigma_5'] = df.groupby('instrument')['return'].transform(
        lambda x: x.rolling(window=5, min_periods=5).std()
    )

    # 20 日滚动标准差 (min_periods=20)
    df['sigma_20'] = df.groupby('instrument')['return'].transform(
        lambda x: x.rolling(window=20, min_periods=20).std()
    )

    # 比率 = σ_5 / σ_20
    df['Volatility_Regime_Ratio_5_20'] = df['sigma_5'] / df['sigma_20']

    result = df[['Volatility_Regime_Ratio_5_20']].copy()
    result = result.dropna()
    result.to_hdf("result.h5", key="data")
    return result

if __name__ == "__main__":
    calculate_volatility_regime_ratio_5_20()
```

#### VWAP_Deviation_20 — factor.py

```python
import pandas as pd
import numpy as np

def calculate_vwap_deviation_20():
    df = pd.read_hdf("daily_pv.h5", key="data")
    df = df.sort_index()

    # Close × Volume
    df['close_vol'] = df['$close'] * df['$volume']

    # 20 日滚动求和
    df['sum_close_vol'] = df.groupby('instrument')['close_vol'].transform(
        lambda x: x.rolling(window=20, min_periods=20).sum()
    )
    df['sum_vol'] = df.groupby('instrument')['$volume'].transform(
        lambda x: x.rolling(window=20, min_periods=20).sum()
    )

    # VWAP_20 = Σ(Close×Volume) / Σ(Volume)
    df['VWAP_20'] = df['sum_close_vol'] / df['sum_vol']

    # 偏离 = (Close - VWAP) / VWAP
    df['VWAP_Deviation_20'] = (df['$close'] - df['VWAP_20']) / df['VWAP_20']

    result = df[['VWAP_Deviation_20']].copy()
    result = result.dropna()
    result.to_hdf("result.h5", key="data")
    return result

if __name__ == "__main__":
    calculate_vwap_deviation_20()
```

#### Range_Compression_Ratio_5_20 — factor.py

```python
import pandas as pd
import numpy as np

def calculate_Range_Compression_Ratio_5_20():
    df = pd.read_hdf("daily_pv.h5", key="data")
    df = df.sort_index()

    # 5 日最高价最大值
    high_5 = df["$high"].groupby(level="instrument").rolling(window=5, min_periods=5).max()
    if high_5.index.nlevels > 2:
        high_5 = high_5.droplevel(0)

    # 5 日最低价最小值
    low_5 = df["$low"].groupby(level="instrument").rolling(window=5, min_periods=5).min()
    if low_5.index.nlevels > 2:
        low_5 = low_5.droplevel(0)

    # 20 日最高价最大值
    high_20 = df["$high"].groupby(level="instrument").rolling(window=20, min_periods=20).max()
    if high_20.index.nlevels > 2:
        high_20 = high_20.droplevel(0)

    # 20 日最低价最小值
    low_20 = df["$low"].groupby(level="instrument").rolling(window=20, min_periods=20).min()
    if low_20.index.nlevels > 2:
        low_20 = low_20.droplevel(0)

    # 区间比率 = (5日区间) / (20日区间)
    range_5 = high_5 - low_5
    range_20 = high_20 - low_20
    ratio = range_5 / range_20
    ratio = ratio.replace([np.inf, -np.inf], np.nan)

    result = pd.DataFrame({"Range_Compression_Ratio_5_20": ratio})
    result.to_hdf("result.h5", key="data")
    return result

if __name__ == "__main__":
    calculate_Range_Compression_Ratio_5_20()
```

---

## 四、信息层次总结

Global Trace 的信息密度很高，从假设到代码全链路保存：

| 层次 | 存储对象 | 关键字段 | 用途 |
|------|----------|----------|------|
| **反馈层** | `ExperimentFeedback` | `decision`, `reason`, `code_change_summary`, `eda_improvement` | LLM 对实验结果的评价和决策 |
| **实验层** | `Experiment` | `hypothesis`, `base_features`, `based_experiments`, `running_info` | 实验配置、基础特征、SOTA 依赖链 |
| **因子定义层** | `FactorTask` | `factor_name`, `factor_formulation`, `variables`, `factor_description`, `factor_implementation` | 因子数学公式、变量定义、描述 |
| **代码层** | `Workspace` | `file_dict['factor.py']`, `running_info`, `feedback`, `change_summary` | 完整可运行的 Python 因子实现 |

### LLM 如何利用 Global Trace

后续实验在 `factor.py` 或 `factor_from_report.py` 启动时，通过 `seed_trace_from_global()` 将 Global Trace 加载到 `trace.hist` 中。LLM 在生成新假设时能看到：

1. **历史成功的假设和推理** — 避免重复已知有效方向
2. **历史失败的假设和反馈** — 避免重蹈覆辙（从 `based_experiments` 链推断）
3. **因子的数学公式和变量定义** — 理解因子构造方式
4. **因子的完整 Python 代码** — 可直接复用或修改已有实现
5. **基础特征算子** — 了解当前因子库中已有的 20 个 Qlib 算子因子
6. **LLM 的反馈评价** — 知道什么设计模式有效（如比率归一化 > 原始值）

---

## 五、嗅探脚本

Global Trace 的内容可通过以下脚本查看：

```bash
# 基本信息（因子名、公式、变量、描述）
python scripts/inspect_global_trace.py

# 完整信息（包含 factor.py 源码）
python scripts/inspect_global_trace.py --show-code

# 指定路径
python scripts/inspect_global_trace.py --path log/global_trace.pkl --show-code
```

脚本位于 `scripts/inspect_global_trace.py`。
