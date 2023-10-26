import copy
import os
from typing import Dict, Tuple

import i6_core.rasr as rasr
from i6_core.returnn.config import ReturnnConfig
from i6_experiments.users.berger.args.experiments import transducer as exp_args
from i6_experiments.users.berger.args.returnn.config import get_returnn_config
from i6_experiments.users.berger.args.returnn.learning_rates import (
    LearningRateSchedules,
)
from i6_experiments.users.berger.corpus.sms_wsj.viterbi_transducer_data import (
    get_wsj_data,
)
import i6_experiments.users.berger.network.models.context_1_transducer_raw_samples as transducer_model
from i6_experiments.users.berger.recipe.summary.report import SummaryReport
from i6_experiments.users.berger.systems.returnn_seq2seq_system import (
    ReturnnSeq2SeqSystem,
)
from i6_experiments.users.berger.systems.dataclasses import ReturnnConfigs
from i6_experiments.users.berger.util import default_tools
from i6_private.users.vieting.helpers.returnn import serialize_dim_tags
from i6_experiments.users.berger.recipe.returnn.training import (
    GetBestCheckpointJob,
)
from i6_experiments.users.berger.systems.dataclasses import AlignmentData
from .config_01a_ctc_blstm import py as py_ctc
from sisyphus import gs, tk

tools = copy.deepcopy(default_tools)

# ********** Settings **********

rasr.flow.FlowNetwork.default_flags = {"cache_mode": "task_dependent"}


num_classes = 87


# ********** Return Config **********


def generate_returnn_config(
    train: bool,
    *,
    train_data_config: dict,
    dev_data_config: dict,
    **kwargs,
) -> ReturnnConfig:
    if train:
        (network_dict, extra_python,) = transducer_model.make_context_1_blstm_transducer(
            num_outputs=num_classes,
            gt_args={
                "sample_rate": 16000,
                "specaug_v2": False,
                "specaug_args": {
                    "max_time_num": 1,
                    "max_time": 15,
                    "max_feature_num": 5,
                    "max_feature": 5,
                },
            },
            blstm_args={
                "num_layers": 6,
                "max_pool": [1, 2, 2],
                "size": 400,
                "dropout": 0.1,
                "l2": 1e-04,
            },
            decoder_args={
                "dec_mlp_args": {
                    "num_layers": 2,
                    "size": 640,
                    "activation": "tanh",
                    "dropout": 0.1,
                    "l2": 5e-06,
                },
                "combination_mode": "concat",
                "joint_mlp_args": {
                    "num_layers": 1,
                    "size": 1024,
                    "dropout": 0.1,
                    "l2": 5e-06,
                    "activation": "tanh",
                },
            },
            output_args={
                "label_smoothing": 0.2,
            },
        )
    else:
        network_dict, extra_python = transducer_model.make_context_1_blstm_transducer_recog(
            num_outputs=num_classes,
            gt_args={
                "sample_rate": 16000,
                "specaug_after_dct": False,
            },
            blstm_args={
                "num_layers": 6,
                "max_pool": [1, 2, 2],
                "size": 400,
            },
            decoder_args={
                "dec_mlp_args": {
                    "num_layers": 2,
                    "size": 640,
                    "activation": "tanh",
                },
                "combination_mode": "concat",
                "joint_mlp_args": {
                    "num_layers": 1,
                    "size": 1024,
                    "activation": "tanh",
                },
            },
        )

    returnn_config = get_returnn_config(
        network=network_dict,
        target="classes",
        num_epochs=60,
        python_prolog=[
            "import sys",
            "sys.setrecursionlimit(10 ** 6)",
        ],
        extra_python=extra_python,
        num_inputs=1,
        num_outputs=num_classes,
        extern_data_kwargs={"dtype": "int16" if train else "float32"},
        extern_target_kwargs={"dtype": "int8" if train else "int32"},
        extern_data_config=True,
        grad_noise=0.0,
        grad_clip=20.0,
        schedule=LearningRateSchedules.OCLR,
        initial_lr=8e-05,
        peak_lr=kwargs.get("peak_lr", 4e-04),
        final_lr=1e-06,
        n_steps_per_epoch=2460,
        batch_size=2_400_000,
        extra_config={
            "train": train_data_config,
            "dev": dev_data_config,
            "chunking": (
                {
                    "data": 256 * 160 + 1039,
                    "classes": 64,
                },
                {
                    "data": 128 * 160,
                    "classes": 32,
                },
            ),
            "min_chunk_size": {"data": 1039 + 1, "classes": 1},
        },
    )
    returnn_config = serialize_dim_tags(returnn_config)

    return returnn_config


def run_exp(alignments: Dict[str, AlignmentData]) -> Tuple[SummaryReport, tk.Path]:
    assert tools.returnn_root is not None
    assert tools.returnn_python_exe is not None

    data = get_wsj_data(
        tools.returnn_root,
        tools.returnn_python_exe,
        alignments=alignments,
        train_key="train_si284",
        cv_key="cv_dev93",
        dev_keys=["cv_dev93"],
        test_keys=["test_eval92"],
        freq_kHz=16,
    )

    # ********** Step args **********

    train_args = exp_args.get_transducer_train_step_args(
        num_epochs=60,
        gpu_mem_rqmt=24,
    )

    recog_args = exp_args.get_transducer_recog_step_args(
        num_classes,
        lm_scales=[0.9],
        epochs=[40, 60],
        lookahead_options={"scale": 0.5},
        search_parameters={"label-pruning": 12.0},
    )

    # ********** System **********

    system = ReturnnSeq2SeqSystem(tools)

    # ********** Returnn Configs **********

    train_config = generate_returnn_config(
        train=True,
        train_data_config=data.train_data_config,
        dev_data_config=data.cv_data_config,
    )
    recog_config = generate_returnn_config(
        train=False,
        train_data_config=data.train_data_config,
        dev_data_config=data.cv_data_config,
    )

    returnn_configs = ReturnnConfigs(
        train_config=train_config,
        recog_configs={"recog": recog_config},
    )

    system.add_experiment_configs(f"BLSTM_Transducer_Viterbi", returnn_configs)

    system.init_corpora(
        dev_keys=data.dev_keys,
        test_keys=data.test_keys,
        align_keys=data.align_keys,
        corpus_data=data.data_inputs,
        am_args=exp_args.transducer_recog_am_args,
    )
    system.setup_scoring()

    system.run_train_step(**train_args)

    # system.run_dev_recog_step(**recog_args)
    system.run_test_recog_step(**recog_args)

    train_job = system.get_train_job()
    model = GetBestCheckpointJob(
        model_dir=train_job.out_model_dir, learning_rates=train_job.out_learning_rates
    ).out_checkpoint

    assert system.summary_report
    return system.summary_report, model


def py() -> Tuple[SummaryReport, tk.Path]:
    _, alignments = py_ctc()

    filename_handle = os.path.splitext(os.path.basename(__file__))[0][len("config_") :]
    gs.ALIAS_AND_OUTPUT_SUBDIR = f"{filename_handle}/"

    summary_report, model = run_exp(alignments)

    tk.register_report(f"{gs.ALIAS_AND_OUTPUT_SUBDIR}/summary.report", summary_report)

    return summary_report, model
