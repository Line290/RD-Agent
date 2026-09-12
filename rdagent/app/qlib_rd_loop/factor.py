"""
Factor workflow with session control
"""

import asyncio
from pathlib import Path
from typing import Any

import fire
from rdagent.app.qlib_rd_loop.conf import FACTOR_PROP_SETTING
from rdagent.components.workflow.rd_loop import RDLoop
from rdagent.core.exception import CoderError, FactorEmptyError
from rdagent.log import rdagent_logger as logger
from rdagent.utils.global_trace import append_to_global_trace


class FactorRDLoop(RDLoop):
    skip_loop_error = (FactorEmptyError, CoderError)
    skip_loop_error_stepname = "feedback"

    global_trace_path: str | None = None

    def running(self, prev_out: dict[str, Any]):
        exp = self.runner.develop(prev_out["coding"])
        if exp is None:
            logger.error("Factor extraction failed.")
            raise FactorEmptyError("Factor extraction failed.")
        logger.log_object(exp, tag="runner result")
        return exp

    def record(self, prev_out: dict[str, Any]):
        super().record(prev_out)
        if self.global_trace_path is not None:
            feedback = prev_out.get("feedback")
            exp = prev_out.get("running") or prev_out.get("coding") or prev_out.get("direct_exp_gen", {}).get("exp_gen")
            if feedback is not None and feedback.decision and exp is not None:
                append_to_global_trace(self.global_trace_path, exp, feedback)
                logger.info(
                    f"Appended successful experiment to global trace: {self.global_trace_path}",
                )


def main(
    path: str | None = None,
    step_n: int | None = None,
    loop_n: int | None = None,
    all_duration: str | None = None,
    checkout: bool = True,
    checkout_path: str | None = None,
    base_features_path: str | None = None,
    trace_path: str | None = None,
    global_trace: str | None = None,
    **kwargs,
):
    """
    Auto R&D Evolving loop for fintech factors.

    You can continue running session by

    .. code-block:: python

        dotenv run -- python rdagent/app/qlib_rd_loop/factor.py $LOG_PATH/__session__/1/0_propose  --step_n 1

    You can seed the trace from a factor_from_report session and then evolve:

    .. code-block:: python

        dotenv run -- python rdagent/app/qlib_rd_loop/factor.py --trace_path $LOG_PATH/__session__/0/4_record --loop_n 5

    You can seed from a global trace library accumulated across batches:

    .. code-block:: python

        dotenv run -- python rdagent/app/qlib_rd_loop/factor.py --global_trace log/global_trace.pkl --loop_n 5
    """
    if checkout_path is not None:
        checkout = Path(checkout_path)

    if path is None:
        factor_loop = FactorRDLoop(FACTOR_PROP_SETTING)
        factor_loop.global_trace_path = global_trace
        if global_trace is not None:
            from rdagent.utils.global_trace import seed_trace_from_global
            count = seed_trace_from_global(factor_loop.trace, global_trace)
            if count > 0:
                logger.info(
                    f"Seeded trace with {count} historical experiments "
                    f"from global trace: {global_trace}",
                )
        elif trace_path is not None:
            from rdagent.utils.workflow.loop import LoopBase
            seed_session = LoopBase.load(trace_path, checkout=checkout)
            factor_loop.trace = seed_session.trace
            factor_loop.plan = seed_session.plan
            logger.info(
                f"Seeded trace with {len(factor_loop.trace.hist)} historical experiments "
                f"from {trace_path}",
            )
    else:
        factor_loop = FactorRDLoop.load(path, checkout=checkout)
        factor_loop.global_trace_path = global_trace

    factor_loop._init_base_features(base_features_path)
    if "user_interaction_queues" in kwargs and kwargs["user_interaction_queues"] is not None:
        factor_loop._set_interactor(*kwargs["user_interaction_queues"])
        factor_loop._interact_init_params()
    asyncio.run(factor_loop.run(step_n=step_n, loop_n=loop_n, all_duration=all_duration))


if __name__ == "__main__":
    fire.Fire(main)
