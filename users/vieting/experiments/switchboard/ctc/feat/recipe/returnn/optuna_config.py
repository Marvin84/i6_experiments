from i6_core import returnn
from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class OptunaReturnnConfig:
    config_generator: Callable[..., returnn.ReturnnConfig]
    config_kwargs: Dict[str, Any]

    def generate_config(self, trial) -> returnn.ReturnnConfig:
        return self.config_generator(trial, **self.config_kwargs)