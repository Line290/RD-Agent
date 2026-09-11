# Qlib A股数据字段清单

## 数据来源

- **数据包**：`qlib_data_cn_1d_latest.zip`
- **下载地址**：`https://github.com/SunsetWolf/qlib_dataset/releases/download/v2/qlib_data_cn_1d_latest.zip`
- **本地路径**：`~/.qlib/qlib_data/cn_data/`
- **数据频率**：日线（1d）
- **最后更新**：2020-09-25（官方 latest 数据包已停止更新）

---

## 目录结构

```
~/.qlib/qlib_data/cn_data/
├── calendars/
│   └── day.txt              # 交易日历
├── instruments/
│   ├── all.txt              # 全市场股票（含指数）
│   ├── csi100.txt           # 沪深100成分股
│   ├── csi300.txt           # 沪深300成分股
│   └── csi500.txt           # 中证500成分股
└── features/
    ├── sh000300/            # 沪深300指数
    ├── sh000903/            # 中证100指数
    ├── sh000905/            # 中证500指数
    ├── sh600000/            # 个股（上交所）
    ├── sh600004/
    ├── ...
    └── szXXXXXX/            # 个股（深交所）
```

---

## 交易日历（calendars/day.txt）

| 属性 | 值 |
|------|-----|
| 文件 | `calendars/day.txt` |
| 总交易日数 | 4,943 天 |
| 起始日期 | 1999-11-10 |
| 截止日期 | 2020-09-25 |
| 格式 | 每行一个日期，格式 `YYYY-MM-DD` |

---

## 股票池（instruments）

### 可用股票池

| 文件 | 股票池 | 股票数量 | 说明 |
|------|--------|---------|------|
| `all.txt` | 全市场 | 3,875 | 含所有A股 + 指数 |
| `csi100.txt` | 沪深100 | 246 | 大盘蓝筹股 |
| `csi300.txt` | 沪深300 | 820 | 沪深两市前300只（含历史调整记录） |
| `csi500.txt` | 中证500 | 2,017 | 中型股（含历史调整记录） |

> 注：csi300.txt 有820行，因为包含历史成分股调整记录（同一股票可能有多行不同时间段）

### 文件格式

```
SH600000	2005-01-01	2020-09-25
SH600004	2018-12-17	2020-09-25
```

每行：`股票代码 \t 入选日期 \t 剔除日期`

Qlib 在回测时根据每行的日期范围动态确定每个交易日的股票池，自动处理半年度调仓。

### 交易所分布

| 交易所 | 代码前缀 | 股票数量 |
|--------|---------|---------|
| 上海证券交易所 | `sh` | 1,565 |
| 深圳证券交易所 | `sz` | 2,310 |
| **合计** | | **3,875** |

### 可用指数

| 代码 | 名称 |
|------|------|
| `SH000300` | 沪深300指数 |
| `SH000903` | 中证100指数 |
| `SH000905` | 中证500指数 |

> 注：深交所指数（如 SZ399001 深证成指、SZ399006 深证100）不在数据包中。

---

## 数据字段（features）

每个股票目录下包含以下7个 `.day.bin` 文件：

| 字段 | Qlib表达式 | 文件名 | 含义 | 示例值 |
|------|-----------|--------|------|--------|
| 开盘价 | `$open` | `open.day.bin` | 当日开盘价（后复权） | 7.782 |
| 收盘价 | `$close` | `close.day.bin` | 当日收盘价（后复权） | 7.704 |
| 最高价 | `$high` | `high.day.bin` | 当日最高价（后复权） | — |
| 最低价 | `$low` | `low.day.bin` | 当日最低价（后复权） | — |
| 成交量 | `$volume` | `volume.day.bin` | 当日成交量（股） | — |
| 涨跌幅 | `$change` | `change.day.bin` | 当日涨跌幅（百分比） | -0.0101 |
| 复权因子 | `$factor` | `factor.day.bin` | 后复权因子 | 0.7829 |

### 字段说明

- **OHLCV**（Open/High/Low/Close/Volume）：标准行情数据，价格为**后复权**价
- **$change**：当日涨跌幅，计算方式为 `(close - 前一日close) / 前一日close`
- **$factor**：复权因子，用于将复权价还原为真实价格：`真实价格 = 复权价格 / factor`

### 数据访问示例

```python
import qlib
qlib.init(provider_uri='~/.qlib/qlib_data/cn_data', region='cn')

from qlib.data import D

# 获取沪深300股票的OHLCV数据
instruments = D.instruments(market='csi300')
df = D.features(
    instruments,
    ['$open', '$close', '$high', '$low', '$volume', '$change', '$factor'],
    start_time='2020-09-20',
    end_time='2020-09-25'
)
print(df.head())
```

输出示例：

```
                          $open    $close    $high     $low   $volume  $change   $factor
instrument datetime
SH600000   2020-09-21  7.782    7.704    ...      ...     ...    -0.0101  0.7829
           2020-09-22  7.680    7.594    ...      ...     ...    -0.0142  0.7829
           2020-09-23  7.602    7.539    ...      ...     ...    -0.0072  0.7829
           2020-09-24  7.524    7.438    ...      ...     ...    -0.0135  0.7829
           2020-09-25  7.438    7.414    ...      ...     ...    -0.0032  0.7829
```

---

## 数据限制

| 限制项 | 说明 |
|--------|------|
| 截止日期 | 2020-09-25（最新可用日期） |
| 无 csi800 | 数据包不包含 csi800 股票池（可合并 csi300+csi500 生成） |
| 无深证指数 | 不含 SZ399001（深证成指）、SZ399006（深证100）等 |
| 无分钟数据 | 仅日线数据（1d），无分钟级别 |
| 无基本面数据 | 不含财务报表、估值等基本面数据 |
| 无北交所 | 不含 BJ 开头的北交所股票 |

---

## Alpha20 基础因子（由代码计算，非数据包内置）

回测中使用的 Alpha20 因子是通过 Qlib 表达式从上述7个基础字段实时计算的技术指标：

| 因子名 | 公式 | 说明 |
|--------|------|------|
| RESI5 | `Resi($close, 5)/$close` | 5日回归残差 |
| WVMA5 | `Std(Abs($close/Ref($close,1)-1)*$volume, 5)/(Mean(Abs($close/Ref($close,1)-1)*$volume, 5)+1e-12)` | 5日加权成交量波动率 |
| RSQR5 | `Rsquare($close, 5)` | 5日R²（线性拟合优度） |
| KLEN | `($high-$low)/$open` | K线长度 |
| RSQR10 | `Rsquare($close, 10)` | 10日R² |
| CORR5 | `Corr($close, Log($volume+1), 5)` | 5日价量相关性 |
| CORD5 | `Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 5)` | 5日收益率-成交量变化相关性 |
| CORR10 | `Corr($close, Log($volume+1), 10)` | 10日价量相关性 |
| ROC60 | `Ref($close, 60)/$close` | 60日收益率 |
| RESI10 | `Resi($close, 10)/$close` | 10日回归残差 |
| VSTD5 | `Std($volume, 5)/($volume+1e-12)` | 5日成交量标准差 |
| RSQR60 | `Rsquare($close, 60)` | 60日R² |
| CORR60 | `Corr($close, Log($volume+1), 60)` | 60日价量相关性 |
| WVMA60 | `Std(Abs($close/Ref($close,1)-1)*$volume, 60)/(Mean(Abs($close/Ref($close,1)-1)*$volume, 60)+1e-12)` | 60日加权成交量波动率 |
| STD5 | `Std($close, 5)/$close` | 5日收盘价标准差 |
| RSQR20 | `Rsquare($close, 20)` | 20日R² |
| CORD60 | `Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 60)` | 60日收益率-成交量变化相关性 |
| CORD10 | `Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 10)` | 10日收益率-成交量变化相关性 |
| CORR20 | `Corr($close, Log($volume+1), 20)` | 20日价量相关性 |
| KLOW | `(Less($open, $close)-$low)/$open` | 下影线长度 |

---

## 数据更新方案（如需2020年后的数据）

由于 Qlib 官方数据包已停止更新（截止2020-09-25），如需更新的数据可选：

1. **akshare/tushare 下载**：从第三方数据源下载行情数据，用 Qlib 的 `dump_bin` 工具转换为 `.day.bin` 格式
2. **增量更新**：保留现有数据，仅追加2020-09-25之后的新数据
3. **替代数据源**：使用 baostock、jqdata 等其他数据源

```bash
# Qlib 数据转换工具
python scripts/dump_bin.py dump_update \
  --csv_path 1m_data.csv \
  --qlib_dir ~/.qlib/qlib_data/cn_data \
  --freq 1d \
  --date_field_name date \
  --symbol_field_name code
```
