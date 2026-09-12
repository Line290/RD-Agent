"""
Global Trace 内容嗅探脚本

加载 log/global_trace.pkl，逐条解析其中存储的实验信息：
- 反馈层 (ExperimentFeedback)
- 实验层 (Experiment)
- 因子定义层 (FactorTask)
- 代码层 (Workspace)

用法:
    python scripts/inspect_global_trace.py [--path log/global_trace.pkl] [--show-code]
"""

import argparse

import pandas as pd
from rdagent.core.serialization import loads


def inspect_entry(i: int, exp, fb, show_code: bool = False) -> None:
    print(f"\n{'=' * 80}")
    print(f"Entry {i}")
    print(f"{'=' * 80}")

    # ── Feedback ──
    print("\n[Feedback]")
    print(f"  decision: {fb.decision}")
    print(f"  reason (first 300 chars): {fb.reason[:300]}")
    if hasattr(fb, "code_change_summary") and fb.code_change_summary:
        print(f"  code_change_summary: {fb.code_change_summary[:200]}")
    if hasattr(fb, "eda_improvement") and fb.eda_improvement:
        print(f"  eda_improvement: {fb.eda_improvement[:200]}")

    # ── Hypothesis ──
    print("\n[Hypothesis]")
    print(f"  {exp.hypothesis}")

    # ── Experiment overview ──
    print("\n[Experiment]")
    print(f"  sub_tasks count: {len(exp.sub_tasks)}")
    print(f"  based_experiments count: {len(exp.based_experiments)}")
    print(f"  base_features count: {len(exp.base_features)}")
    if exp.base_features:
        print(f"  base_features (first 5): {dict(list(exp.base_features.items())[:5])}")

    # sub_results
    if exp.sub_results:
        print(f"  sub_results: {exp.sub_results}")

    # running_info
    if hasattr(exp, "running_info") and exp.running_info:
        ri = exp.running_info
        if hasattr(ri, "result"):
            r = ri.result
            if isinstance(r, pd.DataFrame):
                print(f"  running_info.result (DataFrame {r.shape}):")
                print(f"  {r.to_string()}")
            elif isinstance(r, dict):
                print(f"  running_info.result keys: {list(r.keys())}")

    # ── FactorTask detail ──
    print(f"\n[FactorTask × {len(exp.sub_tasks)}]")
    for j, task in enumerate(exp.sub_tasks):
        print(f"\n  Task {j}:")
        print(f"    factor_name: {task.factor_name}")
        print(f"    formulation: {task.factor_formulation}")
        print(f"    variables: {task.variables}")
        desc = task.factor_description[:200] if task.factor_description else None
        print(f"    description: {desc}")
        print(f"    implementation: {task.factor_implementation}")
        if hasattr(task, "resource") and task.resource:
            print(f"    resource: {str(task.resource)[:300]}")

    # ── Workspace code ──
    if show_code:
        print(f"\n[Workspace Code × {len(exp.sub_workspace_list)}]")
        for j, ws in enumerate(exp.sub_workspace_list):
            if ws is None:
                continue
            print(f"\n  Workspace {j} (factor: {exp.sub_tasks[j].factor_name}):")
            ws_attrs = [
                a for a in dir(ws)
                if not a.startswith("_") and not callable(getattr(ws, a, None))
            ]
            print(f"    attributes: {ws_attrs}")

            if hasattr(ws, "file_dict") and ws.file_dict:
                print(f"    file_dict keys: {list(ws.file_dict.keys())}")
                for fn, fc in ws.file_dict.items():
                    fc_str = str(fc)
                    print(f"    --- {fn} ({len(fc_str)} chars) ---")
                    print(f"    {fc_str}")

            if hasattr(ws, "running_info") and ws.running_info:
                ri = ws.running_info
                if hasattr(ri, "result"):
                    r = ri.result
                    if isinstance(r, pd.DataFrame):
                        print(f"    running_info.result (DataFrame {r.shape}):")
                        print(f"    {r.to_string()}")
                    elif isinstance(r, dict):
                        print(f"    running_info.result keys: {list(r.keys())}")

            if hasattr(ws, "feedback") and ws.feedback:
                print(f"    workspace feedback: {str(ws.feedback)[:300]}")
    else:
        print("\n[Workspace] (use --show-code to see factor Python source)")
        for j, ws in enumerate(exp.sub_workspace_list):
            if ws is None:
                continue
            print(f"  Workspace {j}: {exp.sub_tasks[j].factor_name}")
            if hasattr(ws, "file_dict") and ws.file_dict:
                for fn, fc in ws.file_dict.items():
                    print(f"    {fn}: {len(str(fc))} chars")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Global Trace contents")
    parser.add_argument(
        "--path", default="log/global_trace.pkl", help="Path to global trace file",
    )
    parser.add_argument(
        "--show-code", action="store_true", help="Print full factor Python source",
    )
    args = parser.parse_args()

    with open(args.path, "rb") as f:
        entries = loads(f.read())

    print(f"Total entries in Global Trace: {len(entries)}")
    for i, (exp, fb) in enumerate(entries):
        inspect_entry(i, exp, fb, show_code=args.show_code)


if __name__ == "__main__":
    main()
