# RD-Agent 迭代机制说明

## 迭代机制说明

**有迭代，但是是跨报告迭代，不是同一报告内的反馈迭代。**

`FactorReportLoop` 的迭代逻辑如下：

### 1. 迭代次数 = 报告数量

```python
# factor_from_report.py:107
self.loop_n = min(len(self.judge_pdf_data_items), FACTOR_FROM_REPORT_PROP_SETTING.report_limit)
```

你的 `/Users/lindq/Downloads/quant_research/quant_reports` 文件夹里只有 **1 个 PDF**，所以 `loop_n = 1`，跑完 1 个就终止了。

### 2. 每次迭代的步骤

每个 loop 执行 5 个 step（`rd_loop.py` 中定义）：

1. `direct_exp_gen` — 从 PDF 提取因子
2. `coding` — LLM 生成因子代码
3. `running` — Qlib 回测
4. `feedback` — LLM 分析回测结果，给出改进建议
5. `record` — 记录到 trace

### 3. 反馈没有被用来改进同一因子

反馈（feedback）会存入 `self.trace.hist`，但它的作用是**作为下一个 loop 的 `based_experiments` 参考上下文**，而不是对同一因子进行二次改进：

```python
# factor_from_report.py:124-126
exp.based_experiments = [QlibFactorExperiment(...)] + [
    t[0] for t in self.trace.hist if t[1]  # 之前成功的实验作为参考
]
```

### 怎么实现更多迭代？

**方法一：放入更多 PDF 报告**

```bash
# 把更多研报 PDF 放入文件夹，loop_n 会自动增加（上限 report_limit=20）
rdagent fin_factor_report --report-folder=/path/to/many_reports
```

**方法二：用 `factor` 命令做纯 R&D 迭代**（不依赖 PDF）

```bash
rdagent fin_factor --step_n 10
```

`factor.py` 的 `main()` 支持 `step_n` 和 `loop_n` 参数，可以指定迭代次数。这个模式下，`hypothesis_gen` 会基于 trace 历史自动生成新假设，形成"生成→测试→反馈→新假设"的闭环。

**方法三：用 `all_duration` 持续运行**

```bash
rdagent fin_factor_report --report-folder=... --all_duration 2h
```

设置运行时长，在时间内持续迭代。

### 总结

| 命令 | 迭代方式 | 反馈用途 |
|------|----------|----------|
| `fin_factor_report` | 跨报告迭代，1 报告 = 1 loop | 作为历史上下文给下一个报告参考 |
| `fin_factor` | 基于假设的 R&D 闭环迭代 | 驱动下一轮假设生成 |

你之前只放了 1 个 PDF，所以只跑了 1 个 loop 就结束了。如果想看到反馈驱动的迭代闭环，应该用 `fin_factor` 命令并指定 `step_n` 或 `loop_n`。
