# RD-Agent 回测结果全流程详解

## 总览

命令 `rdagent fin_factor_report --report-folder=...` 触发 `FactorReportLoop`，执行 5 个 step：

```
direct_exp_gen → coding → running → feedback → record
```

每个 step 的输入/输出、调用的文件和函数、存储位置如下。

---

## Step 1: `direct_exp_gen` — 从 PDF 提取因子

### 入口

- **文件**: `rdagent/app/qlib_rd_loop/factor_from_report.py`
- **函数**: `FactorReportLoop.direct_exp_gen()` (async)
- **调用**: `extract_hypothesis_and_exp_from_reports(report_file_path)`

### 1.1 PDF 解析

- **文件**: `rdagent/components/document_reader/document_reader.py`
- **函数**: `load_and_process_pdfs_by_langchain(path)`
  - 内部调用 `PyPDFLoader(path).load()` (langchain) 解析 PDF 为 `Document` 列表
  - 再调用 `process_documents_by_langchain(docs)` 将每页内容拼接，返回 `{文件路径: 文本内容}` dict
- **函数**: `extract_first_page_screenshot_from_pdf(pdf_path)`
  - 用 `fitz` (PyMuPDF) 打开 PDF 第 1 页，渲染为 PIL Image（截图）
- **输出存储**: `log/<run_id>/Loop_0/direct_exp_gen/docs/<pid>/<timestamp>.pkl`（文本内容）, `log/<run_id>/Loop_0/direct_exp_gen/load_pdf_screenshot/<pid>/<timestamp>.pkl`（截图）

### 1.2 因子提取（多轮 LLM 调用）

- **文件**: `rdagent/scenarios/qlib/factor_experiment_loader/pdf_loader.py`
- **类**: `FactorExperimentLoaderFromPDFfiles.load(file_or_folder_path)`

流程：

1. **`classify_report_from_dict(docs_dict)`** — LLM 分类报告是否包含因子（返回 `{"class": 0|1}`）
   - 系统 prompt: `pdf_loader/prompts/classify_system`
   - LLM 调用: `APIBackend().build_messages_and_create_chat_completion(json_mode=True)`

2. **`extract_factors_from_report_dict(docs_dict, selected_report_dict)`** — 多进程提取因子名称和描述
   - 内部调用 **`__extract_factor_and_formulation_from_one_report(content)`**:
     - **`__extract_factors_name_and_desc_from_content(content)`**:
       - 构建 LLM session: `APIBackend().build_chat_session(session_system_prompt=...)`
       - 循环最多 10 次，每次调用 `session.build_chat_completion(json_mode=True)`
       - 系统 prompt: `prompts/extract_factors_system`
       - 返回 `{factor_name: factor_description}` dict
     - **`__extract_factors_formulation_from_content(content, factor_dict)`**:
       - 同样构建 LLM session，循环最多 10 次
       - 系统 prompt: `prompts/extract_factor_formulation_system`
       - 返回 `{factor_name: {formulation, variables, description}}` dict

3. **`merge_file_to_factor_dict_to_factor_dict(file_to_factor_dict)`** — 合并多报告中的同名因子，取描述最长的

4. **`check_factor_viability(factor_dict)`** — LLM 判断因子是否可实现
   - 系统 prompt: `prompts/factor_viability_system`
   - 返回 `(viability_dict, filtered_factor_dict)`

- **输出存储**:
  - `log/<run_id>/Loop_0/direct_exp_gen/file_to_factor_result/...` — 因子提取中间结果
  - `log/<run_id>/Loop_0/direct_exp_gen/factor_dict/<pid>/<timestamp>.pkl` — 合并后的因子字典
  - `log/<run_id>/Loop_0/direct_exp_gen/filtered_factor_dict/<pid>/<timestamp>.pkl` — 过滤后的因子

### 1.3 生成假设（Hypothesis）

- **文件**: `rdagent/app/qlib_rd_loop/factor_from_report.py`
- **函数**: `generate_hypothesis(factor_result, report_content)`
  - 系统 prompt: `factor_from_report/prompts/hypothesis_generation.system`
  - 用户 prompt: `factor_from_report/prompts/hypothesis_generation.user`（包含因子描述 JSON + 报告全文）
  - LLM 调用: `APIBackend().build_messages_and_create_chat_completion(json_mode=True, json_target_type=Dict[str, str])`
  - 返回 `Hypothesis(hypothesis=..., reason=..., concise_reason=..., ...)`
- **输出存储**: `log/<run_id>/Loop_0/direct_exp_gen/hypothesis generation/<pid>/<timestamp>.pkl`

### 1.4 构建实验对象

- **文件**: `rdagent/scenarios/qlib/factor_experiment_loader/json_loader.py`
- **类**: `FactorExperimentLoaderFromDict().load(filtered_factor_dict)`
  - 遍历因子字典，为每个因子创建 `FactorTask(factor_name, factor_description, factor_formulation, variables)`
  - 返回 `QlibFactorExperiment(sub_tasks=task_l)`

然后在 `direct_exp_gen` 中：
- `exp.based_experiments` 设为 `[空实验] + [之前成功的实验]`（作为 SOTA baseline 参考）
- `exp.sub_tasks` 和 `exp.sub_workspace_list` 截断为 `max_factors_per_exp`（你配置的 1）
- `exp.base_features` 设为 Alpha20（20 个内置因子表达式）

### 输出

返回 `QlibFactorExperiment` 对象，包含：
- `sub_tasks`: 因子任务列表（`[FactorTask]`）
- `hypothesis`: Hypothesis 对象
- `based_experiments`: 历史成功实验列表
- `base_features`: Alpha20 因子表达式字典

### 日志存储

```
log/<run_id>/Loop_0/direct_exp_gen/
├── docs/                    # PDF 解析文本
├── load_pdf_screenshot/     # PDF 首页截图
├── file_to_factor_result/   # 因子提取中间结果（含 LLM 对话）
│   ├── session_xxx/debug_llm/  # 每轮 LLM 交互记录
├── factor_dict/             # 合并后的因子字典
├── filtered_factor_dict/    # 可行性过滤后的因子
├── hypothesis generation/   # 最终假设
├── experiment generation/   # 最终实验对象
├── LITELLM_SETTINGS/        # LLM 配置快照
├── debug_llm/               # LLM 交互原始记录
└── debug_tpl/               # 模板渲染记录
```

---

## Step 2: `coding` — LLM 生成因子代码

### 入口

- **文件**: `rdagent/app/qlib_rd_loop/factor.py`
- **函数**: `FactorRDLoop.coding(prev_out)`
- **调用**: `self.coder.develop(prev_out["direct_exp_gen"])` → `FactorCoSTEER.develop(exp)`

### 2.1 CoSTEER 框架

- **文件**: `rdagent/components/coder/factor_coder/__init__.py`
- **类**: `FactorCoSTEER(CoSTEER)` — 只是 `CoSTEER` 的别名
  - 初始化时设置：
    - `eva = CoSTEERMultiEvaluator(FactorEvaluatorForCoder(scen=scen))` — 评估器
    - `es = FactorMultiProcessEvolvingStrategy(scen=scen)` — 进化策略
    - `evolving_version = 2`

### 2.2 CoSTEER.develop(exp) 主流程

- **文件**: `rdagent/components/coder/CoSTEER/__init__.py`
- **函数**: `CoSTEER.develop(exp)`

1. 将 `exp` 转为 `EvolvingItem.from_experiment(exp)`
2. 创建 `RAGEvoAgent`（多轮进化代理）
3. 循环调用 `self.evolve_agent.multistep_evolve(evo_exp, self.evaluator)`:
   - 每轮：生成代码 → 执行 → 评估 → 反馈 → 选择最优
   - 保留 `fallback_evo_exp`（最优解）
4. 最终返回更新后的 `exp`（`exp.sub_workspace_list` 和 `exp.experiment_workspace` 被更新）

### 2.3 代码生成（核心 LLM 调用）

- **文件**: `rdagent/components/coder/factor_coder/evolving_strategy.py`
- **类**: `FactorMultiProcessEvolvingStrategy(MultiProcessEvolvingStrategy)`
- **函数**: `implement_one_task(target_task, queried_knowledge, workspace, prev_task_feedback)`

流程：
1. 获取因子信息: `target_task.get_task_information()` → `"factor_name: ...\nfactor_description: ...\nfactor_formulation: ...\nvariables: ..."`
2. 从知识库查询：
   - `queried_similar_successful_knowledge` — 类似成功因子实现
   - `queried_similar_error_knowledge` — 类似错误及修复
   - `queried_former_failed_knowledge` — 之前的失败尝试
3. 渲染 prompt：
   - 系统 prompt: `evolving_strategy/prompts/evolving_strategy_factor_implementation_v1_system`（包含 scenario 描述 + 失败历史）
   - 用户 prompt: `evolving_strategy/prompts/evolving_strategy_factor_implementation_v2_user`（包含因子信息 + 知识库参考 + 错误总结）
4. LLM 调用: `APIBackend(use_chat_cache=...).build_messages_and_create_chat_completion(json_mode=True, json_target_type=Dict[str, str])`
5. 解析返回: `json.loads(response)["code"]` → 因子 Python 代码字符串
6. 如果 JSON 解析失败，尝试从 ` ```python ... ``` ` 代码块提取

### 2.4 代码注入到 workspace

- **函数**: `assign_code_list_to_evo(code_list, evo)`
  - 为每个因子创建 `FactorFBWorkspace(target_task=evo.sub_tasks[index])`
  - 调用 `evo.sub_workspace_list[index].inject_files(**{"factor.py": code})` — 将代码写入 workspace

### 2.5 代码评估

- **文件**: `rdagent/components/coder/factor_coder/evaluators.py`
- **类**: `FactorEvaluatorForCoder(CoSTEEREvaluator)`
- **函数**: `evaluate(target_task, implementation, ...)`

评估链：
1. **执行因子代码**: `implementation.execute()` → 返回 `(execution_feedback, gen_df)`
   - 文件: `rdagent/components/coder/factor_coder/factor.py` → `FactorFBWorkspace.execute()`
   - 详见 Step 3 的因子执行部分
2. **因子值评估**: `FactorValueEvaluator.evaluate(implementation, gt_implementation)`
   - 文件: `rdagent/components/coder/factor_coder/eva_utils.py`
   - 调用多个子评估器：
     - `FactorSingleColumnEvaluator` — 检查输出是否单列
     - `FactorInfEvaluator` — 检查无穷值
     - `FactorOutputFormatEvaluator` — LLM 检查输出格式
     - `FactorDatetimeDailyEvaluator` — 检查是否日频数据
     - （如果有 gt）`FactorRowCountEvaluator`, `FactorIndexEvaluator`, `FactorMissingValuesEvaluator`, `FactorEqualValueRatioEvaluator`, `FactorCorrelationEvaluator`
3. **代码评估**: `FactorCodeEvaluator.evaluate(target_task, implementation, execution_feedback, value_feedback)`
   - 系统 prompt: `prompts/evaluator_code_feedback_v1_system`
   - LLM 分析代码质量
4. **最终决策**: `FactorFinalDecisionEvaluator.evaluate(target_task, execution_feedback, value_feedback, code_feedback)`
   - 系统 prompt: `prompts/evaluator_final_decision_v1_system`
   - LLM 返回 `{final_decision: bool, final_feedback: str}`

### 因子代码执行（评估中的执行）

- **文件**: `rdagent/components/coder/factor_coder/factor.py`
- **类**: `FactorFBWorkspace.execute(data_type="Debug")`

1. `self.before_execute()` — 创建 workspace 目录，写入 `factor.py`
2. `self.link_all_files_in_folder_to_workspace(source_data_path, workspace_path)` — 软链接行情数据
   - `source_data_path` = `git_ignore_folder/factor_implementation_source_data_debug/`（Debug 模式）
   - 包含 `daily_pv.h5`（1.3MB，100 只股票 2018-2019 数据）和 `README.md`
3. 执行: `subprocess.check_output(f"python factor.py", cwd=workspace_path, ...)`
4. 读取输出: `pd.read_hdf(workspace_path / "result.h5")` → 因子值 DataFrame

### 输出

- `exp.sub_workspace_list` — 每个 factor 的 `FactorFBWorkspace`（含 `factor.py` 代码 + workspace 路径）
- `exp.prop_dev_feedback` — CoSTEER 评估反馈

### 日志存储

```
log/<run_id>/Loop_0/coding/
├── coder result/            # 最终代码 workspace 列表
├── evo_loop_0/
│   ├── evolving code/       # 每轮进化的代码
│   ├── evolving feedback/   # 每轮进化的反馈
│   ├── debug_llm/           # LLM 交互记录
│   └── token_cost/          # token 消耗
├── time_info/
└── debug_tpl/
```

### workspace 存储

```
git_ignore_folder/RD-Agent_workspace/<uuid>/
├── factor.py                # LLM 生成的因子代码
├── daily_pv.h5 → ../factor_implementation_source_data_debug/daily_pv.h5  # 软链接
├── README.md → ...
├── result.h5                # 因子执行输出（因子的 DataFrame 值）
└── execution.lock           # 文件锁
```

---

## Step 3: `running` — 因子处理 + Qlib 回测

### 入口

- **文件**: `rdagent/app/qlib_rd_loop/factor.py`
- **函数**: `FactorRDLoop.running(prev_out)`
- **调用**: `self.runner.develop(prev_out["coding"])` → `QlibFactorRunner.develop(exp)`

### 3.1 Baseline 实验（如果需要）

- **文件**: `rdagent/scenarios/qlib/developer/factor_runner.py`
- **函数**: `QlibFactorRunner.develop(exp)` (带 `@cache_with_pickle` 装饰器)

首先检查 `exp.based_experiments[-1].result` 是否为 None（baseline 未执行）：
- 如果 None，递归调用 `self.develop(exp.based_experiments[-1])` — 先执行 baseline 回测

### 3.2 环境变量准备

```python
env_to_use = {
    "PYTHONPATH": "./",
    "train_start": "2008-01-01",
    "train_end": "2014-12-31",
    "valid_start": "2015-01-01",
    "valid_end": "2016-12-31",
    "test_start": "2017-01-01",
    "test_end": "2020-08-01",
    "feature_names": str(list(exp.base_features.keys())),   # Alpha20 因子名
    "feature_expressions": str(list(exp.base_features.values())),  # Alpha20 因子表达式
}
```

### 3.3 因子数据处理

- **文件**: `rdagent/scenarios/qlib/developer/utils.py`
- **函数**: `process_factor_data(exp_or_list)`

1. **构建执行调用列表** `_build_execute_calls(exp, base_feature_workspaces)`:
   - 为每个 `exp.sub_workspace_list` 中的 workspace 调用 `implementation.execute("All")`
   - 为 `exp.base_feature_codes` 中的代码创建 `FactorFBWorkspace` 并加入执行列表

2. **多进程执行** `multiprocessing_wrapper(execute_calls, n=RD_AGENT_SETTINGS.multi_proc_n)`:
   - 每个因子 workspace 执行 `FactorFBWorkspace.execute("All")`:
     - `before_execute()` — 创建目录，写入 `factor.py`
     - `link_all_files_in_folder_to_workspace(source_data_path, workspace_path)` — 链接 `daily_pv.h5`
       - "All" 模式 → `git_ignore_folder/factor_implementation_source_data/daily_pv.h5`（203MB，全部数据）
     - `subprocess.check_output(f"python factor.py", cwd=workspace_path)` — 执行因子代码
     - `pd.read_hdf("result.h5")` — 读取因子值 DataFrame

3. **规范化索引** `_normalize_factor_index(df)`:
   - 确保 MultiIndex 为 `(datetime, instrument)`
   - 检查时间间隔是否为日频

4. **合并因子** `pd.concat(factor_dfs, axis=1)` — 拼接所有因子值

### 3.4 SOTA 因子处理

如果有多个历史成功实验（`sota_factor_experiments_list`）：
- `SOTA_factor = process_factor_data(sota_factor_experiments_list)` — 获取之前成功的因子值

### 3.5 因子去重

- **函数**: `QlibFactorRunner.deduplicate_new_factors(SOTA_factor, new_factors)`
  - `pd.concat([SOTA_factor, new_factors], axis=1)` 合并
  - 按 datetime 分组，计算每个 SOTA 因子和新因子之间的 IC（Pearson 相关）
  - 移除 IC > 0.99 的新因子（与已有因子高度相关）
  - 返回去重后的新因子

### 3.6 合并因子矩阵

```python
combined_factors = pd.concat([SOTA_factor, new_factors], axis=1).dropna()
combined_factors = combined_factors.sort_index()
combined_factors = combined_factors.loc[:, ~combined_factors.columns.duplicated(keep="last")]
# 添加 MultiIndex 列名
new_columns = pd.MultiIndex.from_product([["feature"], combined_factors.columns])
combined_factors.columns = new_columns
```

### 3.7 保存合并因子

```python
target_path = exp.experiment_workspace.workspace_path / "combined_factors_df.parquet"
combined_factors.to_parquet(target_path, engine="pyarrow")
```
- **存储位置**: `git_ignore_folder/RD-Agent_workspace/<uuid>/combined_factors_df.parquet`（你的 51MB 文件）

### 3.8 Qlib 回测执行

- **文件**: `rdagent/scenarios/qlib/experiment/workspace.py`
- **类**: `QlibFBWorkspace.execute(qlib_config_name="conf_combined_factors.yaml", run_env=env_to_use)`

1. **创建 conda 环境**:
   - **文件**: `rdagent/utils/env.py`
   - `QlibCondaEnv(conf=QlibCondaConf())` — conda 环境名 `rdagent4qlib`
   - `qtde.prepare()` — 检查环境是否存在，不存在则创建（Python 3.10 + qlib + catboost + xgboost + tables + torch）

2. **渲染 YAML 配置**:
   - `QlibFBWorkspace` 在初始化时调用 `inject_code_from_folder(template_folder_path)` 加载模板
   - 模板文件夹: `rdagent/scenarios/qlib/experiment/factor_template/`
   - 模板包含 3 个 YAML：
     - `conf_baseline.yaml` — 仅 Alpha20 baseline
     - `conf_combined_factors.yaml` — Alpha20 + 新因子 + LGBM（你的回测用的这个）
     - `conf_combined_factors_sota_model.yaml` — Alpha20 + 新因子 + 自定义模型
   - YAML 中用 Jinja2 模板变量 `{{ train_start }}`, `{{ test_end }}` 等，由 `env_to_use` 渲染

3. **执行 Qlib 回测**:
   ```python
   execute_qlib_log = qtde.check_output(
       local_path=str(self.workspace_path),  # workspace 目录
       entry=f"qrun {qlib_config_name}",     # qrun conf_combined_factors.yaml
       env=run_env,
   )
   ```
   - **文件**: `rdagent/utils/env.py` → `LocalEnv._run()`
   - 实际执行: `subprocess.Popen("conda run -n rdagent4qlib --no-capture-output qrun conf_combined_factors.yaml", cwd=workspace_path, env=...)`
   - **Qlib 内部流程**:
     - `qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")` — 加载行情数据
     - `DataHandlerLP` 加载因子数据:
       - `Alpha158DL` — 加载 Alpha20 因子表达式（SOTA baseline）
       - `StaticDataLoader` — 加载 `combined_factors_df.parquet`（新因子）
     - `DatasetH` 分割数据集:
       - train: 2008-01-01 ~ 2014-12-31
       - valid: 2015-01-01 ~ 2016-12-31
       - test:  2017-01-01 ~ 2020-08-01
     - `LGBModel` (LightGBM) 训练:
       - 模型参数: `loss=mse, learning_rate=0.2, max_depth=8, num_leaves=210, lambda_l1=205.7, lambda_l2=580.98, ...`
       - 特征: Alpha20 因子 + 新生成因子
       - 标签: `Ref($close, -2)/Ref($close, -1) - 1`（未来 1 天收益率）
       - 训练过程用 train 集拟合，valid 集早停
     - `SignalRecord` — 记录模型预测信号
     - `SigAnaRecord` — 计算 IC, Rank IC, ICIR
     - `PortAnaRecord` — 组合回测:
       - `TopkDropoutStrategy(topk=50, n_drop=5)` — 选前 50 只，每天淘汰 5 只
       - 初始资金 1 亿，基准 SH000300
       - 交易成本: 买入 0.05%, 卖出 0.15%, 最低 5 元
       - 涨跌停限制 9.5%
     - 所有结果存入 MLflow（`mlruns/` 目录）

   - **执行日志存储**: `log/<run_id>/Loop_0/running/Qlib_execute_log/<pid>/<timestamp>.pkl`

4. **读取回测结果**:
   ```python
   execute_log = qtde.check_output(
       local_path=str(self.workspace_path),
       entry="python read_exp_res.py",
       env=run_env,
   )
   ```
   - **文件**: `rdagent/scenarios/qlib/experiment/factor_template/read_exp_res.py`
   - 流程:
     - `qlib.init()` — 初始化 Qlib
     - `R.list_experiments()` — 列出 MLflow 中的所有实验
     - 遍历所有 experiment 和 recorder，找到 `end_time` 最新的 recorder
     - `latest_recorder.list_metrics()` — 获取所有指标 → 写入 `qlib_res.csv`
     - `latest_recorder.load_object("portfolio_analysis/report_normal_1day.pkl")` — 加载净值曲线 → 写入 `ret.parquet`

### 3.9 输出

- `exp.result` — `pd.Series`，回测指标（即 `qlib_res.csv` 内容）
- `exp.stdout` — 训练日志摘要（epoch loss 等）

### 日志存储

```
log/<run_id>/Loop_0/running/
├── Qlib_execute_log/                # qrun 执行日志
├── Quantitative Backtesting Chart/  # 净值曲线 DataFrame
├── runner result/                    # 最终回测结果 Series
├── debug_tpl/                        # 模板渲染记录
└── time_info/
```

### workspace 存储

```
git_ignore_folder/RD-Agent_workspace/<uuid>/
├── conf_combined_factors.yaml        # 渲染后的 Qlib 配置
├── conf_baseline.yaml                # baseline 配置
├── combined_factors_df.parquet       # 合并因子矩阵（51MB）
├── read_exp_res.py                   # 结果读取脚本
├── qlib_res.csv                      # 回测指标
├── ret.parquet                       # 净值曲线
├── mlruns/                           # MLflow 实验记录
│   └── <experiment_id>/
│       └── <run_id>/
│           ├── metrics/              # IC, annualized_return, max_drawdown 等
│           ├── params/               # 模型参数
│           ├── tags/                 # 实验标签
│           └── artifacts/
│               ├── portfolio_analysis/  # 组合分析报告
│               └── sig_analysis/        # 信号分析
└── README.md
```

---

## Step 4: `feedback` — LLM 分析回测结果

### 入口

- **文件**: `rdagent/components/workflow/rd_loop.py`
- **函数**: `RDLoop.feedback(prev_out)`
- **调用**: `self.summarizer.generate_feedback(prev_out["running"], self.trace)`

### 4.1 结果对比

- **文件**: `rdagent/scenarios/qlib/developer/feedback.py`
- **类**: `QlibFactorExperiment2Feedback(Experiment2Feedback)`
- **函数**: `generate_feedback(exp, trace)`

1. 提取数据:
   - `hypothesis = exp.hypothesis` — 因子假设
   - `current_result = exp.result` — 当前回测结果（Series）
   - `sota_result = exp.based_experiments[-1].result` — SOTA baseline 回测结果
   - `tasks_factors = [task.get_task_information_and_implementation_result() for task in exp.sub_tasks]` — 因子信息

2. **`process_results(current_result, sota_result)`**:
   - 将两个 Series 转为 DataFrame
   - 筛选关键指标（`IMPORTANT_METRICS`）:
     ```python
     IMPORTANT_METRICS = [
         "IC",
         "1day.excess_return_with_cost.annualized_return",
         "1day.excess_return_with_cost.max_drawdown",
     ]
     ```
   - 格式化为对比字符串: `"IC of Current Result is 0.030940, of SOTA Result is 0.041000; ..."`

### 4.2 LLM 反馈生成

1. 系统 prompt: `scenarios/qlib/prompts/factor_feedback_generation.system`（包含 scenario 全描述）
2. 用户 prompt: `scenarios/qlib/prompts/factor_feedback_generation.user`，包含:
   - `hypothesis_text` — 因子假设
   - `task_details` — 因子信息（名称、描述、公式、变量、实现结果）
   - `combined_result` — 回测结果对比
3. LLM 调用: `APIBackend().build_messages_and_create_chat_completion(json_mode=True, json_target_type=Dict[str, str | bool | int])`
4. 解析 JSON 返回:
   ```python
   {
       "Observations": "...",        # 对回测结果的观察
       "Feedback for Hypothesis": "...", # 对假设的评价
       "New Hypothesis": "...",      # 新的改进假设
       "Reasoning": "...",           # 推理过程
       "Replace Best Result": "no"   # 是否替换最佳结果
   }
   ```
5. 返回 `HypothesisFeedback(observations=..., hypothesis_evaluation=..., new_hypothesis=..., reason=..., decision=...)`

### 日志存储

```
log/<run_id>/Loop_0/feedback/
├── feedback/        # HypothesisFeedback 对象
├── debug_llm/        # LLM 交互原始记录
├── token_cost/       # token 消耗
├── debug_tpl/        # 模板渲染
└── time_info/
```

---

## Step 5: `record` — 记录到 Trace

### 入口

- **文件**: `rdagent/components/workflow/rd_loop.py`
- **函数**: `RDLoop.record(prev_out)`

### 流程

```python
feedback = prev_out["feedback"]
exp = prev_out.get("running") or prev_out.get("coding") or ...
self.trace.sync_dag_parent_and_hist((exp, feedback), prev_out[self.LOOP_IDX_KEY])
```

- 将 `(experiment, feedback)` 对存入 `self.trace.hist`
- `trace.hist` 是一个列表: `[(exp1, feedback1), (exp2, feedback2), ...]`
- 后续 loop 的 `direct_exp_gen` 会读取 `trace.hist` 作为 `based_experiments` 上下文

### 日志存储

```
log/<run_id>/Loop_0/record/
└── time_info/
```

### Session 快照

每个 step 完成后都会保存 session 快照:
```
log/<run_id>/__session__/0/
├── 0_direct_exp_gen    # pickle 序列化的 LoopBase 对象
├── 1_coding
├── 2_running
├── 3_feedback
└── 4_record
```
可通过 `FactorReportLoop.load(path)` 恢复 session 继续运行。

---

## 完整数据流图

```
PDF 研报
  │
  ▼ langchain PyPDFLoader
PDF 文本内容
  │
  ▼ LLM: classify → extract factors → extract formulation → check viability
因子字典 {name: {description, formulation, variables}}
  │
  ▼ LLM: generate_hypothesis
Hypothesis + QlibFactorExperiment(sub_tasks=[FactorTask])
  │
  ▼ CoSTEER: LLM generate code → execute factor.py → evaluate
FactorFBWorkspace (factor.py + result.h5)
  │
  ▼ process_factor_data: execute all factors → normalize → concat
因子值 DataFrame (datetime, instrument) → factor columns
  │
  ▼ deduplicate_new_factors: IC < 0.99
去重后的新因子
  │
  ▼ pd.concat([SOTA_factor, new_factors]) → parquet
combined_factors_df.parquet (51MB)
  │
  ▼ qrun conf_combined_factors.yaml (conda: rdagent4qlib)
  │   ├─ Alpha158DL loads Alpha20 expressions
  │   ├─ StaticDataLoader loads combined_factors_df.parquet
  │   ├─ LGBModel trains on train set (2008-2014)
  │   ├─ TopkDropoutStrategy backtests on test set (2017-2020)
  │   └─ MLflow records all metrics
MLflow mlruns/
  │
  ▼ read_exp_res.py: R.list_experiments → latest_recorder.list_metrics
qlib_res.csv (IC=0.031, 年化=0.4%, 最大回撤=-18.9%)
ret.parquet (净值曲线)
  │
  ▼ LLM: compare current vs SOTA → generate feedback
HypothesisFeedback (observations, new_hypothesis, decision)
  │
  ▼ trace.sync_dag_parent_and_hist
trace.hist (供下一个 loop 参考)
```
