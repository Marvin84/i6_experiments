
from __future__ import annotations
from typing import Tuple
import _setup_test_env  # noqa
import returnn.frontend as rf
from returnn.tensor import Tensor, Dim, TensorDict, batch_dim, single_step_dim
from rf_utils import run_model

def test_zoneout_lstm_tf_layers_vs_rf_pt():
    # Compare TF-layers ZoneoutLSTM vs RF ZoneoutLSTM with PyTorch backend.
    time_dim = Dim(Tensor("time", [batch_dim], dtype="int32"))
    # Note: Use high dimension because only that triggers some inconsistencies.
    in_dim, out_dim = Dim(7, name="in"), Dim(100, name="out")
    extern_data = TensorDict(
        {
            "data": Tensor("data", [batch_dim, time_dim, in_dim], dtype="float32"),
        }
    )

    zoneout_factor_cell = 0.15
    zoneout_factor_output = 0.05

    tf_net_dict = {
        "lstm": {
            "class": "rec",
            "unit": "ZoneoutLSTM",
            "from": "data",
            "unit_opts": {
                "zoneout_factor_cell": zoneout_factor_cell,
                "zoneout_factor_output": zoneout_factor_output,
                "use_zoneout_output": True,
            },
            "in_dim": in_dim,
            "out_dim": out_dim,
            # Better for the test to not have zeros in weights/bias.
            "forward_weights_init": "random_normal_initializer(mean=0.0, stddev=1.)",
            "recurrent_weights_init": "random_normal_initializer(mean=0.0, stddev=1.)",
            "bias_init": "random_normal_initializer(mean=0.0, stddev=1.)",
        },
        "output": {"class": "copy", "from": "lstm"},
    }

    from returnn.config import Config

    config = Config(
        dict(
            log_verbositiy=5,
            network=tf_net_dict,
            extern_data={
                "data": {"dim_tags": extern_data["data"].dim_tags},
            },
        )
    )

    from returnn.tensor.utils import tensor_dict_fill_random_numpy_
    from returnn.torch.data.tensor_utils import tensor_dict_numpy_to_torch_
    from returnn.tf.network import TFNetwork
    import tensorflow as tf
    import numpy

    print("*** Construct TF graph for TF model")
    extern_data = TensorDict()
    extern_data.update(config.typed_dict["extern_data"], auto_convert=True)
    tensor_dict_fill_random_numpy_(extern_data, dyn_dim_max_sizes={time_dim: 20}, dyn_dim_min_sizes={time_dim: 10})
    extern_data_numpy_raw_dict = extern_data.as_raw_tensor_dict()
    extern_data.reset_content()
    rnd = numpy.random.RandomState(43)

    rf.select_backend_returnn_layers_tf()
    tf1 = tf.compat.v1
    with tf1.Graph().as_default() as graph, tf1.Session(graph=graph).as_default() as session:
        net = TFNetwork(config=config)
        net.construct_from_dict(config.typed_dict["network"])
        print("*** Random init TF model")
        net.initialize_params(session)

        # Overwrite again, such that the bias is also non-zero.
        print("*** Set random weights")
        params = net.get_params_list()
        for param in params:
            print("Param:", param, "shape:", param.shape, "dtype:", param.dtype)
            param.load(rnd.normal(scale=0.1, size=tuple(param.shape)), session=session)

        print("*** Forward")
        extern_data_tf_raw_dict = net.extern_data.as_raw_tensor_dict()
        assert set(extern_data_tf_raw_dict.keys()) == set(extern_data_numpy_raw_dict.keys())
        feed_dict = {extern_data_tf_raw_dict[k]: extern_data_numpy_raw_dict[k] for k in extern_data_numpy_raw_dict}
        fetches = net.get_fetches_dict()
        old_model_outputs_data = {}
        for old_layer_name in ["output"]:
            layer = net.get_layer(old_layer_name)
            out = layer.output
            old_model_outputs_data[old_layer_name] = out
            fetches["layer:" + old_layer_name] = out.placeholder
            for i, tag in enumerate(out.dim_tags):
                if tag.is_batch_dim():
                    fetches[f"layer:{old_layer_name}:size{i}"] = tag.get_dim_value()
                elif tag.dyn_size_ext:
                    old_model_outputs_data[f"{old_layer_name}:size{i}"] = tag.dyn_size_ext
                    fetches[f"layer:{old_layer_name}:size{i}"] = tag.dyn_size_ext.placeholder
        old_model_outputs_fetch = session.run(fetches, feed_dict=feed_dict)
        old_model_params = net.get_params_serialized(session=session)

    # --- Now the PyTorch model
    import torch

    print("*** Create PyTorch model")
    rf.select_backend_torch()

    class _Net(rf.Module):
        def __init__(self):
            super().__init__()
            self.lstm = rf.ZoneoutLSTM(
                in_dim,
                out_dim,
                zoneout_factor_cell=zoneout_factor_cell,
                zoneout_factor_output=zoneout_factor_output,
                forget_bias=1.0,  # RETURNN TF-layers ZoneoutLSTM
                parts_order="icfo",  # RETURNN TF-layers ZoneoutLSTM
            )

        def __call__(self, x: Tensor, *, spatial_dim: Dim) -> Tensor:
            initial_state = self.lstm.default_initial_state(batch_dims=[batch_dim])
            y, _ = self.lstm(x, state=initial_state, spatial_dim=spatial_dim)
            return y

    new_model = _Net()

    print("*** Copy over params")
    tf_lstm_kernel = old_model_params.values_dict["lstm"]["lstm_cell/kernel"]  # (in+out, 4*out)
    tf_lstm_bias = old_model_params.values_dict["lstm"]["lstm_cell/bias"]  # (4*out,)
    tf_lstm_kernel = tf_lstm_kernel.transpose([1, 0])  # (4*out, in+out)
    tf_lstm_ff_kernel = tf_lstm_kernel[:, : in_dim.dimension]
    tf_lstm_rec_kernel = tf_lstm_kernel[:, in_dim.dimension :]
    with torch.no_grad():
        new_model.lstm.ff_weight.raw_tensor.copy_(torch.from_numpy(tf_lstm_ff_kernel))
        new_model.lstm.rec_weight.raw_tensor.copy_(torch.from_numpy(tf_lstm_rec_kernel))
        new_model.lstm.bias.raw_tensor.copy_(torch.from_numpy(tf_lstm_bias))

    print("*** Forward")
    rf.init_train_step_run_ctx(train_flag=False)
    extern_data.reset_content()
    extern_data.assign_from_raw_tensor_dict_(extern_data_numpy_raw_dict)
    tensor_dict_numpy_to_torch_(extern_data)

    out = new_model(extern_data["data"], spatial_dim=time_dim)
    assert out.dims == (time_dim, batch_dim, out_dim) == old_model_outputs_data["output"].dims
    assert out.dtype == "float32" == old_model_outputs_data["output"].dtype

    print("*** Compare")
    import numpy.testing

    tf_out = old_model_outputs_fetch["layer:output"]
    pt_out = out.raw_tensor.detach().cpu().numpy()
    print("out shape:", tf_out.shape)
    assert tf_out.shape == pt_out.shape

    size_v = old_model_outputs_fetch[f"layer:output:size0"]
    print("* sizes:", size_v)
    for b in range(tf_out.shape[1]):
        tf_out[size_v[b] :] = 0
        pt_out[size_v[b] :] = 0

    _pt_out = pt_out
    _tf_out = tf_out

    for t in range(_tf_out.shape[0]):
        print("* t:", t)

        tf_out = _tf_out[t]
        pt_out = _pt_out[t]

        # Using equal_nan=False because we do not want any nan in any of the values.
        if numpy.allclose(tf_out, pt_out, atol=1e-5):
            continue  # done

        print("** not all close!")
        print("close:")
        # Iterate over all indices, and check if the values are close.
        # If not, add the index to the mismatches list.
        remarks = []
        count_mismatches = 0
        for idx in sorted(numpy.ndindex(tf_out.shape), key=sum):
            if numpy.isnan(tf_out[idx]) and numpy.isnan(pt_out[idx]):
                remarks.append("[%s]:? (both are nan)" % ",".join([str(i) for i in idx]))
                count_mismatches += 1
                continue
            close = numpy.allclose(tf_out[idx], pt_out[idx], atol=1e-5)
            if not close:
                count_mismatches += 1
            remarks.append(
                "[%s]:" % ",".join([str(i) for i in idx])
                + ("✓" if close else "✗ (%.5f diff)" % abs(tf_out[idx] - pt_out[idx]))
            )
            if len(remarks) >= 50 and count_mismatches > 0:
                remarks.append("...")
                break
        print("\n".join(remarks))
        numpy.testing.assert_allclose(
            tf_out,
            pt_out,
            rtol=1e-5,
            atol=1e-5,
            equal_nan=False,
            err_msg=f"TF-layers vs RF-PT mismatch",
        )
        raise Exception(f"should not get here, mismatches: {remarks}")

    print("all close!")