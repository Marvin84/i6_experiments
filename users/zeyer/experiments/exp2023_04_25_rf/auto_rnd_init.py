"""
Inspired from recent Twitter discussion:
https://twitter.com/francoisfleuret/status/1747150719969321294
https://twitter.com/ducha_aiki/status/1747176379009896838

Where the following paper were mentioned:

- Layer-sequential unit-variance (LSUV), All you need is a good init, https://arxiv.org/abs/1511.06422, ICLR 2016
    - code: https://github.com/ducha-aiki/LSUV-pytorch
- Data-dependent Initializations of Convolutional Neural Networks, https://arxiv.org/abs/1511.06856, ICLR 2016
- Self-Normalizing Neural Networks, https://arxiv.org/abs/1706.02515, NeurIPS 2017
- Steering Deep Feature Learning with Backward Aligned Feature Updates, https://arxiv.org/abs/2311.18718

"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict
import time

from .aed import from_scratch_model_def, Model, from_scratch_training

if TYPE_CHECKING:
    import torch
    from returnn.tensor import Dim


def test():
    import torch
    import returnn.__main__
    from returnn.util import better_exchook
    from returnn.util import basic as util
    from returnn.config import get_global_config
    from returnn.datasets.util.vocabulary import Vocabulary
    import returnn.frontend as rf
    from returnn.tensor import Tensor, Dim, batch_dim
    from returnn.torch.frontend.bridge import rf_module_to_pt_module

    better_exchook.install()
    config = get_global_config(auto_create=True)
    config.update({"behavior_version": 20, "backend": "torch", "use_lovely_tensors": True})
    util.BehaviorVersion.set(config.int("behavior_version", 0))
    returnn.__main__.config = config
    returnn.__main__.init_backend_engine()

    rf.select_backend_torch()
    target_dim = Dim(1000, name="targets")
    target_dim.vocab = Vocabulary.create_vocab_from_labels([str(i) for i in range(target_dim.dimension)], eos_label=0)
    model: Model = from_scratch_model_def(epoch=1, in_dim=Dim(1, name="in"), target_dim=target_dim)
    print("Num model parameters:", util.human_size(sum(p.num_elements() for p in model.parameters())))

    pt_model = rf_module_to_pt_module(model)
    dev = torch.device("cuda")
    pt_model.to(dev)
    rf.set_default_device("cuda")
    print(f"GPU memory usage (allocated model): {util.human_bytes_size(torch.cuda.memory_allocated(dev))}")

    train_input_kwargs = _generate_dummy_train_input_kwargs(dev=dev, target_dim=target_dim)

    # TODO how to setup hooks?

    start_time = time.time()
    rf.init_train_step_run_ctx(train_flag=False)
    pt_model.eval()
    with torch.no_grad():
        from_scratch_training(model=model, **train_input_kwargs)
    print("One train forward step, duration:", util.hms_fraction(time.time() - start_time), "sec")
    print(f"GPU peak memory allocated: {util.human_bytes_size(torch.cuda.max_memory_allocated(dev))}")

    for name, loss in rf.get_run_ctx().losses.items():
        print(f"Loss {name}: {loss.get_mean_loss().raw_tensor.item()}")


def _generate_dummy_train_input_kwargs(*, dev: torch.device, target_dim: Dim) -> Dict[str, Any]:
    import torch
    from returnn.tensor import Tensor, Dim, batch_dim
    from i6_experiments.users.zeyer.audio.torch.random_speech_like import generate_random_speech_like_audio

    batch_size = 20
    batch_dim.dyn_size_ext = Tensor("batch", [], dtype="int32", raw_tensor=torch.tensor(batch_size, dtype=torch.int32))
    sample_rate = 16_000
    duration = 10.0
    num_frames = int(duration * sample_rate)
    print(
        f"Using dummy batch of size {batch_size * num_frames} raw frames"
        f" ({batch_size * num_frames * 100 // sample_rate} 10ms frames)"
    )
    audio_raw = generate_random_speech_like_audio(batch_size, num_frames, samples_per_sec=sample_rate)
    audio_raw = audio_raw.to(dev)
    audio_lens_raw = torch.tensor([num_frames] * batch_size, dtype=torch.int32)
    audio_spatial_dim = Dim(Tensor("time", [batch_dim], dtype="int32", raw_tensor=audio_lens_raw))
    audio = Tensor("audio", [batch_dim, audio_spatial_dim], dtype="float32", raw_tensor=audio_raw)

    targets_len = int(duration * 3)
    targets_lens_raw = torch.tensor([targets_len] * batch_size, dtype=torch.int32)
    targets_spatial_dim = Dim(Tensor("targets_len", [batch_dim], dtype="int32", raw_tensor=targets_lens_raw))
    targets_raw = torch.randint(0, target_dim.dimension, size=(batch_size, targets_len), dtype=torch.int32, device=dev)
    targets = Tensor(
        "targets", [batch_dim, targets_spatial_dim], dtype="int32", sparse_dim=target_dim, raw_tensor=targets_raw
    )

    return dict(
        data=audio, data_spatial_dim=audio_spatial_dim, targets=targets, targets_spatial_dim=targets_spatial_dim
    )
