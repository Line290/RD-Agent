# RD-Agent CoSTEER 因子迭代与评估机制详解

## 概述

RD-Agent 使用 CoSTEER（Code SynTEsis EvolutionaRy）框架进行因子代码的多轮迭代开发。本文档详细说明因子迭代流程、评估机制、提前退出逻辑以及 RAG 知识管理的作用。

---

## 1. 整体流程

### 1.1 R&D Loop 五步流程

每个 R&D 循环包含 5 个步骤（`rdagent/components/workflow/rd_loop.py`）：

```
direct_exp_gen → coding → running → feedback → record
```

1. **direct_exp_gen（假设生成 + 实验生成）**
   - 从研报 PDF 提取因子
   - LLM 生成假设（hypothesis）
   - 生成实验（FactorTask 列表）

2. **coding（CoSTEER 多轮代码迭代）**
   - 对每个因子生成 Python 代码
   - 多轮迭代优化，直到全部通过或达到上限
   - 详见下文第 2 节

3. **running（回测执行）**
   - 执行因子代码，生成因子值
   - 去重（IC < 0.99）
   - 合并因子，运行 Qlib 回测（LGBModel + TopkDropoutStrategy）

4. **feedback（LLM 反馈）**
   - 比较当前结果与 SOTA/Baseline
   - LLM 生成分析反馈
   - 判断假设是否成立（Decision: True/False）

5. **record（记录）**
   - 同步 DAG 父子关系和历史记录

### 1.2 关键配置

| 配置项 | 默认值 | 说明 | 来源文件 |
|--------|--------|------|----------|
| `max_loop` | 10 | CoSTEER 最大迭代轮数 | `rdagent/components/coder/CoSTEER/config.py:15` |
| `max_factors_per_exp` | 6 | 每次实验最大因子数 | `rdagent/app/qlib_rd_loop/conf.py:105` |
| `report_limit` | 20 | 最多处理 PDF 报告数 | `rdagent/app/qlib_rd_loop/conf.py` |
| `fail_task_trial_limit` | 20 | 单个因子失败上限（超过则跳过） | `rdagent/components/coder/CoSTEER/config.py:18` |

可通过 `.env` 环境变量调整，例如：
```
CoSTEER_max_loop=5
QLIB_FACTOR_MAX_FACTORS_PER_EXP=3
```

---

## 2. CoSTEER 因子代码迭代机制

### 2.1 迭代入口

**文件**：`rdagent/components/coder/CoSTEER/__init__.py:93-193`

```python
def develop(self, exp: Experiment) -> Experiment:
    evo_exp = EvolvingItem.from_experiment(exp)
    self.evolve_agent = RAGEvoAgent(
        max_loop=self.max_loop,          # 默认 10
        evolving_strategy=self.evolving_strategy,
        rag=self.rag,                     # RAG 知识库
        with_knowledge=self.with_knowledge,
        knowledge_self_gen=self.knowledge_self_gen,
        ...
    )
    for evo_exp in self.evolve_agent.multistep_evolve(evo_exp, self.evaluator):
        # 每轮产出代码和反馈
        logger.log_object(evo_exp.sub_workspace_list, tag="evolving code")
        ...
```

### 2.2 多轮迭代主循环

**文件**：`rdagent/core/evolving_agent.py:140-198`

```python
def multistep_evolve(self, evo, eva):
    for evo_loop_id in range(self.max_loop):          # 最多 max_loop 轮
        with logger.tag(f"evo_loop_{evo_loop_id}"):
            # 1. RAG：查询知识库
            queried_knowledge = self.rag.query(evo, self.evolving_trace)

            # 2. Evolve：只迭代未通过的因子
            evo_iter = self.evolving_strategy.evolve_iter(
                evo=evo,
                evolving_trace=self.evolving_trace,
                queried_knowledge=queried_knowledge,
            )

            # 3. Evaluate：评估每个因子代码
            eva_iter = eva.evaluate_iter(...)
            for evolved_evo in evo_iter:
                step_feedback = eva_iter.send(evolved_evo)

            # 4. 记录反馈
            es = EvoStep(evolved_evo, queried_knowledge, overall_feedback)
            logger.log_object(es.feedback, tag="evolving feedback")

            # 5. 更新演进轨迹
            self.evolving_trace.append(es)

            # 6. 知识自更新（可选）
            if self.knowledge_self_gen and self.rag is not None:
                self.rag.generate_knowledge(self.evolving_trace)
                self.rag.dump_knowledge_base()

            # 7. 检查是否全部完成
            if es.feedback is not None and es.feedback.finished():
                logger.info("All tasks in evolving subject have been completed.")
                break  # 提前退出
```

### 2.3 已通过因子的跳过逻辑

**文件**：`rdagent/components/coder/CoSTEER/evolving_strategy.py:108-173`

每轮迭代开始时，会根据 RAG 知识库判断哪些因子需要继续迭代：

```python
def evolve_iter(self, *, evo, queried_knowledge, evolving_trace, **kwargs):
    code_list = [None for _ in range(len(evo.sub_tasks))]

    last_feedback = evolving_trace[-1].feedback  # 上一轮的反馈

    # 1. 找出需要 evolve 的 task
    to_be_finished_task_index: list[int] = []
    for index, target_task in enumerate(evo.sub_tasks):
        target_task_desc = target_task.get_task_information()

        if target_task_desc in queried_knowledge.success_task_to_knowledge_dict:
            # ✅ 已通过的因子 → 使用缓存代码，跳过迭代
            code_list[index] = queried_knowledge \
                .success_task_to_knowledge_dict[target_task_desc] \
                .implementation.file_dict
        else:
            # 检查是否应该跳过
            skip_for_improve_mode = self.improve_mode and (
                last_feedback is None
                or last_feedback[index] is None
            )
            if target_task_desc not in queried_knowledge.failed_task_info_set \
               and not skip_for_improve_mode:
                # ❌ 未通过的因子 → 加入待迭代列表
                to_be_finished_task_index.append(index)

    # 2. 只对待迭代因子调用 LLM 生成/修改代码
    result = multiprocessing_wrapper(
        [
            (implement_func, (
                evo.sub_tasks[target_index],
                queried_knowledge,
                evo.experiment_workspace,
                None if last_feedback is None else last_feedback[target_index],
            ))
            for target_index in to_be_finished_task_index
        ],
        n=RD_AGENT_SETTINGS.multi_proc_n,
    )

    # 3. 将新代码分配到对应的 workspace
    for index, target_index in enumerate(to_be_finished_task_index):
        code_list[target_index] = result[index]

    self.assign_code_list_to_evo(code_list, evo)
    yield evo
```

**核心逻辑**：
- **通过的因子**：加入 `success_task_to_knowledge_dict`，后续轮次直接使用缓存代码，不再调用 LLM
- **未通过的因子**：进入 `to_be_finished_task_index`，继续调用 LLM 修改代码
- **失败次数过多的因子**：加入 `failed_task_info_set`，被跳过（避免无限重试）

---

## 3. 因子评估机制

### 3.1 三维度评估

**文件**：`rdagent/components/coder/factor_coder/evaluators.py:20-120`

每个因子在每轮迭代中经过 3 个维度的评估：

```
维度 1：执行验证 (FactorFBWorkspace.execute)
  → 运行因子 Python 代码
  → 读取 result.h5，检查是否生成有效因子值
  → 如果执行失败 → final_decision = False

维度 2：因子值检查 (FactorValueEvaluator)
  → 检查因子值格式（MultiIndex: datetime × instrument）
  → 检查数值范围、NaN 比例等
  → 如果值检查通过 → final_decision = True，跳过维度 3
  → 如果值检查不通过 → final_decision = False，跳过维度 3
  → 如果无法确定 → 进入维度 3

维度 3：代码审查 + 最终决策 (FactorCodeEvaluator + FactorFinalDecisionEvaluator)
  → LLM 审查代码质量和正确性
  → LLM 综合执行反馈 + 值反馈 + 代码反馈
  → 给出 final_decision: True/False
```

### 3.2 评估流程代码

```python
class FactorEvaluatorForCoder(CoSTEEREvaluator):
    def evaluate(self, target_task, implementation, ...):
        factor_feedback = FactorSingleFeedback()

        # 1. 执行因子代码
        execution_feedback, gen_df = implementation.execute()
        factor_feedback.execution_feedback = execution_feedback

        # 2. 因子值检查
        if gen_df is None:
            # 执行失败，无因子值
            factor_feedback.final_decision = False
        else:
            (factor_feedback.value_feedback,
             decision_from_value_check) = self.value_evaluator.evaluate(...)

            if decision_from_value_check is True:
                # 值检查通过 → 直接通过
                factor_feedback.final_decision = True
            elif decision_from_value_check is False:
                # 值检查不通过 → 直接不通过
                factor_feedback.final_decision = False
            else:
                # 无法确定 → LLM 代码审查 + 最终决策
                factor_feedback.code_feedback = self.code_evaluator.evaluate(...)
                (factor_feedback.final_decision,
                 factor_feedback.final_feedback) = self.final_decision_evaluator.evaluate(...)

        return factor_feedback
```

### 3.3 反馈内容

每个因子的 `FactorSingleFeedback` 包含以下字段：

| 字段 | 说明 |
|------|------|
| `execution_feedback` | 因子代码执行日志（stdout/stderr） |
| `value_feedback` | 因子值检查反馈 |
| `code_feedback` | LLM 对代码质量的审查意见 |
| `final_feedback` | LLM 综合判断的最终反馈 |
| `final_decision` | 最终决策（True=通过，False=不通过） |
| `value_generated_flag` | 是否生成了有效因子值 |
| `final_decision_based_on_gt` | 是否有 ground truth 参考实现 |

### 3.4 全部完成的判断

**文件**：`rdagent/components/coder/CoSTEER/evaluators.py:220-225`

```python
class CoSTEERMultiFeedback(Feedback):
    def finished(self) -> bool:
        # 所有非 None 的因子都通过才算完成
        return all(
            feedback.final_decision
            for feedback in self.feedback_list
            if feedback is not None
        )
```

只有当 **所有因子的 `final_decision` 都为 True** 时，`finished()` 返回 True，迭代提前退出。

---

## 4. 实际迭代示例

### 示例：3 个因子，6 轮迭代

**因子列表**：
1. `Improved_Reversal` — 改进反转因子
2. `Late_Trading_Volume_Ratio` — 尾盘成交占比
3. `High_Frequency_Skewness` — 高频偏度

**迭代过程**：

| 轮次 | 因子1 | 因子2 | 因子3 | 实际迭代内容 |
|------|-------|-------|-------|-------------|
| 1 | ✅ | ❌ | ✅ | 3 个因子都生成代码并评估 |
| 2 | (缓存) | ❌ | (缓存) | 只迭代因子2 |
| 3 | (缓存) | ❌ | (缓存) | 只迭代因子2 |
| 4 | (缓存) | ❌ | (缓存) | 只迭代因子2 |
| 5 | (缓存) | ❌ | (缓存) | 只迭代因子2 |
| 6 | (缓存) | ✅ | (缓存) | 因子2终于通过 → 全部完成，退出 |

- 因子1和3在第1轮就通过验证，后续5轮被缓存跳过
- 因子2连续失败5轮，每轮根据上一轮的反馈修改代码
- 第6轮因子2通过，`finished()` 返回 True，提前退出
- 如果因子2始终不通过，最多迭代到第10轮（`max_loop=10`）后强制退出

### 回测对比机制

#### 对比方式

两次回测使用**相同的 LGBModel + TopkDropoutStrategy**，区别在于输入因子集不同：

| | Baseline | 新因子组合 |
|---|---|---|
| **因子集** | Alpha20（20个基础因子） | Alpha20（20个基础因子）+ 3个新因子 |
| **模型** | LGBModel | LGBModel |
| **策略** | TopkDropoutStrategy | TopkDropoutStrategy |

- **Baseline**：只用 Alpha20 的20个基础因子（RESI5, WVMA5, RSQR5, KLEN, CORR5, CORR10, ROC60, RESI10, VSTD5, RSQR60, CORR60, WVMA60, STD5, RSQR20, CORD60, CORD10, CORD5, CORR20, KLOW, RSQR10）作为特征输入 LGBModel
- **新因子组合**：在 Alpha20 的基础上**追加**3个新因子（Improved_Reversal、Late_Trading_Volume_Ratio、High_Frequency_Skewness），共23个因子一起输入 LGBModel

> 对比的是"加不加这3个新因子"的差异，而不是"3个新因子单独 vs 20个基础因子单独"。

#### Alpha20 基础因子列表

| 因子名 | 公式 |
|--------|------|
| RESI5 | Resi($close, 5)/$close |
| WVMA5 | Std(Abs($close/Ref($close,1)-1)*$volume, 5)/(Mean(Abs($close/Ref($close,1)-1)*$volume, 5)+1e-12) |
| RSQR5 | Rsquare($close, 5) |
| KLEN | ($high-$low)/$open |
| RSQR10 | Rsquare($close, 10) |
| CORR5 | Corr($close, Log($volume+1), 5) |
| CORD5 | Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 5) |
| CORR10 | Corr($close, Log($volume+1), 10) |
| ROC60 | Ref($close, 60)/$close |
| RESI10 | Resi($close, 10)/$close |
| VSTD5 | Std($volume, 5)/($volume+1e-12) |
| RSQR60 | Rsquare($close, 60) |
| CORR60 | Corr($close, Log($volume+1), 60) |
| WVMA60 | Std(Abs($close/Ref($close,1)-1)*$volume, 60)/(Mean(Abs($close/Ref($close,1)-1)*$volume, 60)+1e-12) |
| STD5 | Std($close, 5)/$close |
| RSQR20 | Rsquare($close, 20) |
| CORD60 | Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 60) |
| CORD10 | Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 10) |
| CORR20 | Corr($close, Log($volume+1), 20) |
| KLOW | (Less($open, $close)-$low)/$open |

#### 3个新因子

| 因子名 | 类型 | 含义 |
|--------|------|------|
| `Improved_Reversal` | 反转型高频因子 | 过去20天收益均值的负值，刻画投资者过度反应，偏向前期跌幅较大的股票。公式：Mean(-R_t, 20) |
| `Late_Trading_Volume_Ratio` | 反转型高频因子 | 尾盘成交量占全天成交量的比例（过去20天均值），正交化后效果显著提升 |
| `High_Frequency_Skewness` | 反转型高频因子 | 日内高频收益的偏度（过去20天均值），正交化后效果下降 |

#### 回测结果对比

| 指标 | Baseline (Alpha20) | Alpha20 + 3新因子 | 变化 |
|------|-------------------|-------------------|------|
| Rank IC | 0.0335 | 0.0317 | -0.0018 |
| IC | 0.0311 | 0.0309 | -0.0002 |
| ICIR | 0.2606 | 0.2509 | -0.0097 |
| Rank ICIR | 0.2765 | 0.2586 | -0.0179 |
| 年化超额收益(扣费) | 4.10% | 5.04% | +22.9% |
| 年化超额收益(未扣费) | 8.63% | 9.61% | +11.3% |
| 信息比率(扣费) | 0.4646 | 0.5536 | +19.2% |
| 信息比率(未扣费) | 0.9759 | 1.0539 | +8.0% |
| 最大回撤(扣费) | -14.22% | -13.57% | 改善1.3% |
| 最大回撤(未扣费) | -11.92% | -11.02% | 改善1.1% |
| 日均超额(扣费) | 0.0172% | 0.0212% | +23.3% |

#### 结论

加入3个新因子后：
- **IC 相关指标略有下降**（Rank IC -0.0018，ICIR -0.0097），说明因子预测排名能力稍有稀释
- **收益指标显著提升**：年化超额收益(扣费) +22.9%，信息比率(扣费) +19.2%
- **风险控制改善**：最大回撤从 -14.22% 改善至 -13.57%
- 这3个高频因子提供了 Alpha20 未捕捉到的额外信息，在收益和风险控制方面均有正向贡献

---

## 5. 因子回测流程

### 5.1 回测整体流程

因子回测分为 7 个步骤，从因子代码执行到最终产出回测指标：

```
因子代码 → 执行生成 result.h5 → 因子数据处理 → 生成 Qlib 配置 → 执行 qrun 回测 → 提取结果
```

### 5.2 因子代码执行 → 生成因子值

CoSTEER 迭代阶段，每个因子的 Python 代码被执行后生成 `result.h5` 文件，包含一个 MultiIndex（datetime × instrument）的 DataFrame，即每日每股票的因子值。

### 5.3 因子数据处理（`QlibFactorRunner.develop`）

**文件**：`rdagent/scenarios/qlib/developer/factor_runner.py:64-202`

```python
def develop(self, exp: QlibFactorExperiment) -> QlibFactorExperiment:
    # 1. 如果有 based_experiments，先执行 baseline
    if exp.based_experiments and exp.based_experiments[-1].result is None:
        exp.based_experiments[-1] = self.develop(exp.based_experiments[-1])

    # 2. 准备环境变量（Alpha20 因子表达式 + 日期参数）
    env_to_use = {
        "feature_names": str(list(exp.base_features.keys())),
        "feature_expressions": str(list(exp.base_features.values())),
        "train_start": "2008-01-01", "train_end": "2014-12-31",
        "valid_start": "2015-01-01", "valid_end": "2016-12-31",
        "test_start": "2017-01-01", "test_end": "2020-08-01",
    }

    # 3. 处理新因子数据
    new_factors = process_factor_data(exp)  # 读取各因子 result.h5

    # 4. 去重：IC > 0.99 的新因子被剔除
    if SOTA_factor is not None:
        new_factors = self.deduplicate_new_factors(SOTA_factor, new_factors)

    # 5. 合并 Baseline 因子 + 新因子 → combined_factors_df.parquet
    combined_factors = pd.concat([SOTA_factor, new_factors], axis=1).dropna()
    combined_factors.to_parquet(target_path, engine="pyarrow")

    # 6. 执行 Qlib 回测
    result, stdout = exp.experiment_workspace.execute(
        qlib_config_name="conf_combined_factors.yaml",
        run_env=env_to_use,
    )
```

**去重逻辑**（`deduplicate_new_factors`）：
- 计算每个新因子与每个 Baseline 因子之间的 IC（信息系数）
- 如果 IC > 0.99，说明该新因子与已有因子高度相似，被剔除
- 避免冗余因子对模型造成干扰

### 5.4 Qlib 回测配置（YAML 模板）

**模板目录**：`rdagent/scenarios/qlib/experiment/factor_template/`

| 模板文件 | 用途 |
|----------|------|
| `conf_baseline.yaml` | 只用 Alpha20 基础因子跑回测（Baseline） |
| `conf_combined_factors.yaml` | Alpha20 + 新因子合并跑回测（LGBModel） |
| `conf_combined_factors_sota_model.yaml` | 新因子 + SOTA 模型跑回测 |

模板使用 Jinja2 渲染，`{{ feature_names }}`、`{{ feature_expressions }}` 渲染为 Alpha20 因子列表，`{{ train_start }}` 等渲染为实际日期。

### 5.5 Qlib 回测配置详解（`conf_combined_factors.yaml`）

```yaml
# ===== 数据源 =====
qlib_init:
    provider_uri: "~/.qlib/qlib_data/cn_data"   # A股日线数据
    region: cn

market: &market csi300          # 股票池：沪深300
benchmark: &benchmark SH000300   # 基准：沪深300指数

# ===== 数据加载器 =====
data_handler_config:
    start_time: 2008-01-01
    end_time: 2020-08-01
    instruments: csi300
    data_loader:
        class: NestedDataLoader              # 嵌套数据加载器
        kwargs:
            dataloader_l:
                # 加载器1：Alpha20 基础因子（20个技术指标）
                - class: Alpha158DL
                  kwargs:
                    config:
                        label:
                            - ["Ref($close, -2)/Ref($close, -1) - 1"]  # 未来2日收益率
                            - ["LABEL0"]
                        feature:
                            - {{ feature_expressions }}   # Alpha20 因子表达式
                            - {{ feature_names }}          # Alpha20 因子名

                # 加载器2：新因子（从 parquet 文件加载）
                - class: StaticDataLoader
                  kwargs:
                    config: "combined_factors_df.parquet"  # 新因子数据

# ===== 数据预处理 =====
    learn_processors:
        - DropnaLabel       # 去掉空标签
        - CSZScoreNorm      # 截面标准化（截面ZScore）
```

```yaml
# ===== 交易策略 =====
port_analysis_config:
    strategy:
        class: TopkDropoutStrategy        # Topk Dropout 策略
        module_path: qlib.contrib.strategy
        kwargs:
            signal: <PRED>               # 使用模型预测作为信号
            topk: 50                      # 每日持仓前50只股票
            n_drop: 5                     # 每日淘汰末5只
    backtest:
        start_time: 2017-01-01           # 回测开始
        end_time: 2020-08-01             # 回测结束
        account: 100000000               # 初始资金1亿
        benchmark: SH000300              # 基准：沪深300
        exchange_kwargs:
            limit_threshold: 0.095      # 涨跌停限制
            deal_price: close            # 以收盘价成交
            open_cost: 0.0005            # 买入手续费 0.05%
            close_cost: 0.0015           # 卖出手续费 0.15%（含印花税）
            min_cost: 5                  # 最低手续费5元
```

```yaml
# ===== 模型 =====
task:
    model:
        class: LGBModel                   # LightGBM 回归模型
        module_path: qlib.contrib.model.gbdt
        kwargs:
            loss: mse                     # 均方误差损失
            colsample_bytree: 0.8879     # 列采样
            learning_rate: 0.2            # 学习率
            subsample: 0.8789            # 行采样
            lambda_l1: 205.6999           # L1 正则化
            lambda_l2: 580.9768          # L2 正则化
            max_depth: 8                 # 树最大深度
            num_leaves: 210              # 叶子节点数
            num_threads: 20              # 并行线程数

    # ===== 数据分段 =====
    dataset:
        class: DatasetH
        module_path: qlib.data.dataset
        kwargs:
            handler:
                class: DataHandlerLP
                module_path: qlib.contrib.data.handler
                kwargs: *data_handler_config
            segments:
                train: [2008-01-01, 2014-12-31]   # 训练集（7年）
                valid: [2015-01-01, 2016-12-31]   # 验证集（2年）
                test:  [2017-01-01, 2020-08-01]   # 测试集（3.5年）

    # ===== 回测记录 =====
    record:
        - SignalRecord      # 记录模型预测信号
        - SigAnaRecord      # 计算 IC、ICIR 等指标
        - PortAnaRecord     # 计算组合收益、最大回撤等
```

### 5.6 回测执行流程

**执行入口**（`QlibFBWorkspace.execute`，`rdagent/scenarios/qlib/experiment/workspace.py`）：

```python
def execute(self, qlib_config_name="conf.yaml", run_env={}):
    qtde = QlibCondaEnv(conf=QlibCondaConf())  # conda 环境 rdagent4qlib
    qtde.prepare()

    # 第一步：执行 qrun 运行回测
    execute_qlib_log = qtde.check_output(
        local_path=str(self.workspace_path),
        entry=f"qrun {qlib_config_name}",
        env=run_env,
    )

    # 第二步：执行 read_exp_res.py 提取结果
    execute_log = qtde.check_output(
        local_path=str(self.workspace_path),
        entry="python read_exp_res.py",
        env=run_env,
    )

    # 第三步：读取结果
    ret_df = pd.read_parquet("ret.parquet")          # 组合收益
    qlib_res = pd.read_csv("qlib_res.csv", index_col=0)  # 指标汇总
```

**回测内部流程**：

```
1. Qlib 初始化
   ├─ 加载 A 股日线数据（OHLCV）
   └─ provider_uri: ~/.qlib/qlib_data/cn_data

2. 数据加载
   ├─ Alpha158DL: 计算 Alpha20 基础因子（RESI5, WVMA5, CORR5 等）
   └─ StaticDataLoader: 加载 combined_factors_df.parquet（新因子）

3. 数据预处理
   ├─ DropnaLabel: 去掉空标签的样本
   └─ CSZScoreNorm: 截面标准化（每个时间截面对因子值做 ZScore）

4. LGBModel 训练
   ├─ Train (2008-2014): 拟合 LightGBM 回归模型
   │   └─ 目标：预测未来2日收益率 Ref($close,-2)/Ref($close,-1) - 1
   ├─ Valid (2015-2016): 验证集早停选参
   └─ Test  (2017-2020): 生成预测值（信号）

5. TopkDropoutStrategy 模拟交易
   ├─ 每日根据模型预测值排序，选前50只股票
   ├─ 每日淘汰末5只，买入新的前5只
   ├─ 考虑涨跌停限制（limit_threshold: 0.095）
   ├─ 以收盘价成交
   └─ 扣除手续费（买0.05% + 卖0.15%）

6. 回测记录（mlflow）
   ├─ SignalRecord: 记录模型预测信号
   ├─ SigAnaRecord: 计算IC、ICIR、Rank IC、Rank ICIR
   └─ PortAnaRecord: 计算组合收益、最大回撤、信息比率等

7. 结果提取（read_exp_res.py）
   ├─ 从 mlflow 读取最新 recorder 的指标 → qlib_res.csv
   └─ 读取组合收益报告 → ret.parquet
```

### 5.7 两次回测对比

| | Baseline 回测 | 新因子回测 |
|---|---|---|
| **YAML 模板** | `conf_baseline.yaml` | `conf_combined_factors.yaml` |
| **数据加载器** | 只有 Alpha158DL | Alpha158DL + StaticDataLoader(parquet) |
| **特征数** | 20个基础因子 | 20个基础因子 + 3个新因子 = 23个 |
| **模型** | LGBModel | LGBModel |
| **策略** | TopkDropoutStrategy (topk=50, n_drop=5) | 相同 |
| **训练期** | 2008-01-01 ~ 2014-12-31 | 相同 |
| **验证期** | 2015-01-01 ~ 2016-12-31 | 相同 |
| **测试期** | 2017-01-01 ~ 2020-08-01 | 相同 |
| **基准** | 沪深300 | 沪深300 |
| **初始资金** | 1亿 | 1亿 |

两者的唯一区别是新因子回测多加载了 `combined_factors_df.parquet` 文件，其中包含3个新因子的每日值。LGBModel 会自动学习这些新特征与未来收益之间的关系，从而决定是否利用这些因子。

### 5.8 回测指标说明

`qlib_res.csv` 中输出的主要指标：

| 指标 | 含义 |
|------|------|
| IC | 因子值与未来收益的相关系数 |
| Rank IC | 因子排名与未来收益排名的相关系数 |
| ICIR | IC 的信息比率（IC 均值 / IC 标准差） |
| Rank ICIR | Rank IC 的信息比率 |
| `1day.excess_return_with_cost.annualized_return` | 扣费后年化超额收益 |
| `1day.excess_return_without_cost.annualized_return` | 未扣费年化超额收益 |
| `1day.excess_return_with_cost.information_ratio` | 扣费后信息比率 |
| `1day.excess_return_without_cost.information_ratio` | 未扣费信息比率 |
| `1day.excess_return_with_cost.max_drawdown` | 扣费后最大回撤 |
| `1day.excess_return_without_cost.max_drawdown` | 未扣费最大回撤 |
| `1day.excess_return_with_cost.mean` | 扣费后日均超额收益 |
| `1day.excess_return_with_cost.std` | 扣费后日超额收益标准差 |
| `1day.ffr` | 超额收益为正的天数占比 |
| `1day.pos` | 持仓占比 |
| `l2.train` | 训练集 L2 损失 |
| `l2.valid` | 验证集 L2 损失 |

---

## 6. RAG 知识管理

### 6.1 知识库的作用

RAG（Retrieval-Augmented Generation）知识库在 CoSTEER 迭代中起两个核心作用：

1. **跳过已通过因子**：成功的因子实现被缓存到 `success_task_to_knowledge_dict`，后续轮次直接复用
2. **避免重复失败**：失败次数过多的因子被记录到 `failed_task_info_set`，避免无限重试

### 6.2 知识自更新

**文件**：`rdagent/core/evolving_agent.py:187-191`

```python
# 每轮迭代后，可选地更新知识库
if self.knowledge_self_gen and self.rag is not None:
    self.rag.load_dumped_knowledge_base()
    self.rag.generate_knowledge(self.evolving_trace)  # 从演进轨迹中提取知识
    self.rag.dump_knowledge_base()                     # 持久化到磁盘
```

知识库会从迭代轨迹中自动提取经验：
- 成功的代码模式 → 可供后续因子参考
- 失败的代码模式 → 避免重复犯错

### 6.3 跨实验知识复用

知识库持久化到磁盘后，在后续的 R&D 循环（处理下一份 PDF 报告）中也可以复用：
- 如果新报告中的因子与已成功的因子相似，直接复用代码
- 如果新因子的特征与已失败的因子相似，避免相同的错误

---

## 7. 相关文件索引

| 文件路径 | 作用 |
|----------|------|
| `rdagent/components/coder/CoSTEER/config.py` | CoSTEER 配置（max_loop 等） |
| `rdagent/components/coder/CoSTEER/__init__.py` | CoSTEER 主流程入口（develop 方法） |
| `rdagent/components/coder/CoSTEER/evolving_strategy.py` | 迭代策略（跳过已通过因子的逻辑） |
| `rdagent/components/coder/CoSTEER/evaluators.py` | 多因子反馈聚合（finished/is_acceptable） |
| `rdagent/core/evolving_agent.py` | 多轮迭代主循环（multistep_evolve） |
| `rdagent/components/coder/factor_coder/evaluators.py` | 因子评估三维度（执行/值/代码审查） |
| `rdagent/components/coder/factor_coder/eva_utils.py` | 评估器实现（FactorValueEvaluator 等） |
| `rdagent/app/qlib_rd_loop/conf.py` | 因子实验配置（max_factors_per_exp 等） |
| `rdagent/components/workflow/rd_loop.py` | R&D Loop 五步流程定义 |
| `rdagent/scenarios/qlib/developer/factor_runner.py` | 因子回测运行器（数据处理、去重、执行回测） |
| `rdagent/scenarios/qlib/experiment/workspace.py` | Qlib 回测执行入口（qrun + read_exp_res.py） |
| `rdagent/scenarios/qlib/experiment/factor_experiment.py` | Qlib 因子实验定义（含 Alpha20 基础因子） |
| `rdagent/scenarios/qlib/experiment/factor_template/conf_baseline.yaml` | Baseline 回测配置模板（Alpha20 + LGBModel） |
| `rdagent/scenarios/qlib/experiment/factor_template/conf_combined_factors.yaml` | 新因子合并回测配置模板（Alpha20 + 新因子 + LGBModel） |
| `rdagent/scenarios/qlib/experiment/factor_template/conf_combined_factors_sota_model.yaml` | SOTA 模型回测配置模板 |
| `rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py` | 从 mlflow 提取回测结果 |

---

## 8. 可调参数汇总

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CoSTEER_max_loop` | 10 | CoSTEER 代码迭代最大轮数 |
| `QLIB_FACTOR_MAX_FACTORS_PER_EXP` | 6 | 每次实验最大因子数 |
| `CoSTEER_fail_task_trial_limit` | 20 | 单因子失败上限 |
| `CoSTEER_v2_query_former_trace_limit` | 3 | RAG 查询历史轨迹数 |
| `CoSTEER_v2_query_similar_success_limit` | 3 | RAG 查询相似成功案例数 |
| `RD_AGENT_SETTINGS_multi_proc_n` | 1 | 并行因子代码生成进程数 |
