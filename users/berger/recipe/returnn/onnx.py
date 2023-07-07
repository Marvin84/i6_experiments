import shutil
import subprocess as sp
import sys

import optuna

from i6_core import util
from i6_core.returnn.config import ReturnnConfig
from i6_core.returnn.training import PtCheckpoint
from i6_experiments.users.berger.recipe.returnn.optuna_config import OptunaReturnnConfig
from sisyphus import Job, Task, tk


class ExportPyTorchModelToOnnxJob(Job):
    """
    Experimental exporter job

    JUST FOR DEBUGGING, THIS FUNCTIONALITY SHOULD BE IN RETURNN ITSELF
    """

    def __init__(
        self,
        pytorch_checkpoint: PtCheckpoint,
        returnn_config: ReturnnConfig,
        returnn_root: tk.Path,
    ):
        self.pytorch_checkpoint = pytorch_checkpoint
        self.returnn_config = returnn_config
        self.returnn_root = returnn_root

        self.out_onnx_model = self.output_path("model.onnx")

    def tasks(self):
        yield Task("run", mini_task=True)

    def run(self):
        sys.path.insert(0, self.returnn_root.get())
        import torch
        from returnn.config import Config

        config = Config()
        self.returnn_config.write("returnn.config")
        config.load_file("returnn.config")

        model_state = torch.load(str(self.pytorch_checkpoint), map_location=torch.device("cpu"))
        if isinstance(model_state, dict):
            epoch = model_state["epoch"]
            step = model_state["step"]
            model_state = model_state["model"]
        else:
            epoch = 1
            step = 0

        get_model_func = config.typed_value("get_model")
        assert get_model_func, "get_model not defined"
        model = get_model_func(epoch=epoch, step=step)
        assert isinstance(model, torch.nn.Module)

        model.load_state_dict(model_state)

        export_func = config.typed_value("export")
        assert export_func
        export_func(model=model, model_filename=self.out_onnx_model.get())


class ExportPyTorchModelToOnnxJobV2(Job):
    def __init__(
        self,
        pytorch_checkpoint: PtCheckpoint,
        returnn_config: ReturnnConfig,
        returnn_python_exe: tk.Path,
        returnn_root: tk.Path,
        verbostity: int = 4,
    ):
        self.pytorch_checkpoint = pytorch_checkpoint
        self.returnn_python_exe = returnn_python_exe
        self.returnn_config = returnn_config
        self.returnn_root = returnn_root
        self.verbosity = verbostity

        self.out_returnn_config = self.output_path("returnn.config")
        self.out_onnx_model = self.output_path("model.onnx")

    def tasks(self):
        yield Task("run", rqmt={"gpu": 1})

    def run(self):
        if isinstance(self.returnn_config, tk.Path):
            returnn_config_path = self.returnn_config.get_path()
            shutil.copy(returnn_config_path, self.out_returnn_config.get_path())
        elif isinstance(self.returnn_config, ReturnnConfig):
            returnn_config_path = self.out_returnn_config.get_path()
            self.returnn_config.write(returnn_config_path)
        else:
            returnn_config_path = self.returnn_config
            shutil.copy(self.returnn_config, self.out_returnn_config.get_path())

        args = [
            self.returnn_python_exe.get_path(),
            self.returnn_root.join_right("tools/torch_export_to_onnx.py").get_path(),
            returnn_config_path,
            str(self.pytorch_checkpoint),
            self.out_onnx_model.get(),
            f"--verbosity={self.verbosity}",
            "--device=gpu",
        ]

        util.create_executable("run.sh", args)

        sp.check_call(args)


class OptunaExportPyTorchModelToOnnxJob(Job):
    """
    Experimental exporter job

    JUST FOR DEBUGGING, THIS FUNCTIONALITY SHOULD BE IN RETURNN ITSELF
    """

    def __init__(
        self,
        pytorch_checkpoint: PtCheckpoint,
        returnn_config: OptunaReturnnConfig,
        returnn_root: tk.Path,
        trial: tk.Variable,
    ):
        self.pytorch_checkpoint = pytorch_checkpoint
        self.returnn_config = returnn_config
        self.returnn_root = returnn_root
        self.trial = trial

        self.out_onnx_model = self.output_path("model.onnx")

    def tasks(self):
        yield Task("run", mini_task=True)

    def run(self):
        sys.path.insert(0, self.returnn_root.get())
        import torch
        from returnn.config import Config

        config = Config()
        self.returnn_config.generate_config(self.trial.get()).write("returnn.config")
        config.load_file("returnn.config")

        model_state = torch.load(str(self.pytorch_checkpoint), map_location=torch.device("cpu"))
        if isinstance(model_state, dict):
            epoch = model_state["epoch"]
            step = model_state["step"]
            model_state = model_state["model"]
        else:
            epoch = 1
            step = 0

        get_model_func = config.typed_value("get_model")
        assert get_model_func, "get_model not defined"
        model = get_model_func(epoch=epoch, step=step)
        assert isinstance(model, torch.nn.Module)

        model.load_state_dict(model_state)

        export_func = config.typed_value("export")
        assert export_func
        export_func(model=model, model_filename=self.out_onnx_model.get())
