from i6_experiments.users.zeineldeen.modules.network import ReturnnNetwork
from i6_experiments.users.zeineldeen.modules.attention import AttentionMechanism

# adjust attention_asr_config


class CTCDecoder:
    """
    Represents CTC decoder

    """

    def __init__(
        self,
        base_model,
        source="ctc",
        # dropout=0.0,
        # softmax_dropout=0.3,
        # label_smoothing=0.1,
        target="bpe_labels",
        target_w_blank="bpe_labels_w_blank",
        beam_size=1,
        # embed_dim=621,
        # embed_dropout=0.0,
        # lstm_num_units=1024,
        # output_num_units=1024,
        # enc_key_dim=1024,
        # l2=None,
        # att_dropout=None,
        # rec_weight_dropout=None,
        # zoneout=False,
        # ff_init=None,
        add_lstm_lm=False,
        lstm_lm_dim=1024,
        # loc_conv_att_filter_size=None,
        # loc_conv_att_num_channels=None,
        # reduceout=True,
        # att_num_heads=1,
        # embed_weight_init=None,
        # lstm_weights_init=None,
        lstm_lm_proj_dim=1024,
        length_normalization=False,
        # coverage_threshold=None,
        # coverage_scale=None,
        # ce_loss_scale=1.0,
        # use_zoneout_output: bool = False,
    ):
        """
        :param base_model: base/encoder model instance
        :param str source: input to decoder subnetwork
        :param float dropout: dropout applied to the input of LM-like lstm
        :param float softmax_dropout: Dropout applied to the softmax input
        :param float label_smoothing: label smoothing value applied to softmax
        :param str target: target data key name
        :param int beam_size: value of the beam size
        :param int embed_dim: target embedding dimension
        :param float|None embed_dropout: dropout to be applied on the target embedding
        :param int lstm_num_units: the number of hidden units for the decoder LSTM
        :param int output_num_units: the number of hidden dimensions for the last layer before softmax
        :param int enc_key_dim: the number of hidden dimensions for the encoder key
        :param float|None l2: weight decay with l2 norm
        :param float|None att_dropout: dropout applied to attention weights
        :param float|None rec_weight_dropout: dropout applied to weight paramters
        :param bool zoneout: if set, zoneout LSTM cell is used in the decoder instead of nativelstm2
        :param str|None ff_init: feed-forward weights initialization
        :param bool add_lstm_lm: add separate LSTM layer that acts as LM-like model
          same as here: https://arxiv.org/abs/2001.07263
        :param float lstm_lm_dim: LM-like lstm dimension
        :param int|None loc_conv_att_filter_size:
        :param int|None loc_conv_att_num_channels:
        :param bool reduceout: if set to True, maxout layer is used
        :param int att_num_heads: number of attention heads
        :param str|None embed_weight_init: embedding weights initialization
        :param str|None lstm_weights_init: lstm weights initialization
        :param int lstm_lm_proj_dim: LM-like lstm projection dimension
        :param bool length_normalization: if set to True, length normalization is applied
        :param float|None coverage_threshold: threshold for coverage value used in search
        :param float|None coverage_scale: scale for coverage value
        :param float ce_loss_scale: scale for cross-entropy loss
        :param bool use_zoneout_output: if set, return the output h after zoneout
        """

        self.base_model = base_model

        self.source = source

        # self.dropout = dropout
        # self.softmax_dropout = softmax_dropout
        # self.label_smoothing = label_smoothing
        #
        # self.enc_key_dim = enc_key_dim
        # self.enc_value_dim = base_model.enc_value_dim
        # self.att_num_heads = att_num_heads
        #
        self.target_w_blank = target_w_blank
        self.target = target
        #
        self.beam_size = beam_size
        #
        # self.embed_dim = embed_dim
        # self.embed_dropout = embed_dropout
        #
        # self.dec_lstm_num_units = lstm_num_units
        # self.dec_output_num_units = output_num_units
        #
        # self.ff_init = ff_init
        #
        # self.decision_layer_name = None  # this is set in the end-point config
        #
        # self.l2 = l2
        # self.att_dropout = att_dropout
        # self.rec_weight_dropout = rec_weight_dropout
        # self.dec_zoneout = zoneout

        self.add_lstm_lm = add_lstm_lm
        self.lstm_lm_dim = lstm_lm_dim
        self.lstm_lm_proj_dim = lstm_lm_proj_dim

        # self.loc_conv_att_filter_size = loc_conv_att_filter_size
        # self.loc_conv_att_num_channels = loc_conv_att_num_channels
        #
        # self.embed_weight_init = embed_weight_init
        # self.lstm_weights_init = lstm_weights_init
        #
        # self.reduceout = reduceout
        #
        self.length_normalization = length_normalization
        # self.coverage_threshold = coverage_threshold
        # self.coverage_scale = coverage_scale
        #
        # self.ce_loss_scale = ce_loss_scale
        #
        # self.use_zoneout_output = use_zoneout_output

        self.network = ReturnnNetwork()
        self.subnet_unit = ReturnnNetwork()
        self.dec_output = None
        self.output_prob = None

    def add_decoder_subnetwork(self, subnet_unit: ReturnnNetwork):
        # subnet_unit.add_compare_layer("end", source="output", value=0)  # sentence end token
        #
        # # target embedding
        # subnet_unit.add_linear_layer(
        #     "target_embed0",
        #     "output",
        #     n_out=self.embed_dim,
        #     initial_output=0,
        #     with_bias=False,
        #     l2=self.l2,
        #     forward_weights_init=self.embed_weight_init,
        # )
        #
        # subnet_unit.add_dropout_layer(
        #     "target_embed", "target_embed0", dropout=self.embed_dropout, dropout_noise_shape={"*": None}
        # )
        #
        # # attention
        # att = AttentionMechanism(
        #     enc_key_dim=self.enc_key_dim,
        #     att_num_heads=self.att_num_heads,
        #     att_dropout=self.att_dropout,
        #     l2=self.l2,
        #     loc_filter_size=self.loc_conv_att_filter_size,
        #     loc_num_channels=self.loc_conv_att_num_channels,
        # )
        # subnet_unit.update(att.create())
        #
        # # LM-like component same as here https://arxiv.org/pdf/2001.07263.pdf
        # lstm_lm_component_proj = None
        # if self.add_lstm_lm:
        #     lstm_lm_component = subnet_unit.add_rec_layer(
        #         "lm_like_s",
        #         "prev:target_embed",
        #         n_out=self.lstm_lm_dim,
        #         l2=self.l2,
        #         unit="NativeLSTM2",
        #         rec_weight_dropout=self.rec_weight_dropout,
        #         weights_init=self.lstm_weights_init,
        #     )
        #     lstm_lm_component_proj = subnet_unit.add_linear_layer(
        #         "lm_like_s_proj",
        #         lstm_lm_component,
        #         n_out=self.lstm_lm_proj_dim,
        #         l2=self.l2,
        #         with_bias=False,
        #         dropout=self.dropout,
        #     )
        #
        # lstm_inputs = []
        # if lstm_lm_component_proj:
        #     lstm_inputs += [lstm_lm_component_proj]
        # else:
        #     lstm_inputs += ["prev:target_embed"]
        # lstm_inputs += ["prev:att"]
        #
        # if self.add_lstm_lm:
        #     # element-wise addition is applied instead of concat
        #     lstm_inputs = subnet_unit.add_combine_layer(
        #         "add_embed_ctx", lstm_inputs, kind="add", n_out=self.lstm_lm_proj_dim
        #     )
        #
        # # LSTM decoder (or decoder state)
        # if self.dec_zoneout:
        #     zoneout_unit_opts = {"zoneout_factor_cell": 0.15, "zoneout_factor_output": 0.05}
        #     if self.use_zoneout_output:
        #         zoneout_unit_opts["use_zoneout_output"] = True
        #     subnet_unit.add_rnn_cell_layer(
        #         "s",
        #         lstm_inputs,
        #         n_out=self.dec_lstm_num_units,
        #         l2=self.l2,
        #         weights_init=self.lstm_weights_init,
        #         unit="zoneoutlstm",
        #         unit_opts=zoneout_unit_opts,
        #     )
        # else:
        #     subnet_unit.add_rec_layer(
        #         "s",
        #         lstm_inputs,
        #         n_out=self.dec_lstm_num_units,
        #         l2=self.l2,
        #         unit="NativeLSTM2",
        #         rec_weight_dropout=self.rec_weight_dropout,
        #         weights_init=self.lstm_weights_init,
        #     )
        #
        # s_name = "s"
        # if self.add_lstm_lm:
        #     s_name = subnet_unit.add_linear_layer(
        #         "s_proj", "s", n_out=self.lstm_lm_proj_dim, with_bias=False, dropout=self.dropout, l2=self.l2
        #     )
        #
        # if self.add_lstm_lm:
        #     readout_in_src = subnet_unit.add_combine_layer(
        #         "add_s_att", [s_name, "att"], kind="add", n_out=self.lstm_lm_proj_dim
        #     )
        # else:
        #     readout_in_src = [s_name, "prev:target_embed", "att"]
        #
        # subnet_unit.add_linear_layer("readout_in", readout_in_src, n_out=self.dec_output_num_units, l2=self.l2)
        #
        # if self.reduceout:
        #     subnet_unit.add_reduceout_layer("readout", "readout_in")
        # else:
        #     subnet_unit.add_copy_layer("readout", "readout_in")
        #
        # ce_loss_opts = {"label_smoothing": self.label_smoothing}
        # if self.ce_loss_scale and self.ce_loss_scale != 1.0:
        #     ce_loss_opts["scale"] = self.ce_loss_scale
        #
        # self.output_prob = subnet_unit.add_softmax_layer(
        #     "output_prob",
        #     "readout",
        #     l2=self.l2,
        #     loss="ce",
        #     loss_opts=ce_loss_opts,
        #     target=self.target,
        #     dropout=self.softmax_dropout,
        # )
        #
        # if self.coverage_scale and self.coverage_threshold:
        #     assert self.att_num_heads == 1, "Not supported for multi-head attention."  # TODO: just average the heads?
        #     accum_w = self.subnet_unit.add_eval_layer(
        #         "accum_w", source=["prev:att_weights", "att_weights"], eval="source(0) + source(1)"
        #     )  # [B,enc-T,H=1]
        #     merge_accum_w = self.subnet_unit.add_merge_dims_layer(
        #         "merge_accum_w", accum_w, axes="except_batch"
        #     )  # [B,enc-T]
        #     coverage_mask = self.subnet_unit.add_compare_layer(
        #         "coverage_mask", merge_accum_w, kind="greater", value=self.coverage_threshold
        #     )  # [B,enc-T]
        #     float_coverage_mask = self.subnet_unit.add_cast_layer(
        #         "float_coverage_mask", coverage_mask, dtype="float32"
        #     )  # [B,enc-T]
        #     accum_coverage = self.subnet_unit.add_reduce_layer(
        #         "accum_coverage", float_coverage_mask, mode="sum", axes=-1, keep_dims=True
        #     )  # [B,1]
        #
        #     self.output_prob = self.subnet_unit.add_eval_layer(
        #         "output_prob_coverage",
        #         source=[self.output_prob, accum_coverage],
        #         eval=f"source(0) * (source(1) ** {self.coverage_scale})",
        #     )

        if self.length_normalization:
            subnet_unit.add_choice_layer(
                "output", "data:source", target=self.target_w_blank, beam_size=self.beam_size, initial_output=0
            )
        else:
            subnet_unit.add_choice_layer(
                "output",
                "data:source",
                target=self.target_w_blank,
                beam_size=self.beam_size,
                initial_output=0,
            )

        # recurrent subnetwork
        dec_output = self.network.add_subnet_rec_layer(
            "output", unit=subnet_unit.get_net(), target=self.target_w_blank, source=self.source
        )
        self.network["output"].pop("max_seq_len", None)

        return dec_output

    def create_network(self):
        self.dec_output = self.add_decoder_subnetwork(self.subnet_unit)

        # Add to Base/Encoder network

        # if hasattr(self.base_model, "enc_proj_dim") and self.base_model.enc_proj_dim:
        #     self.base_model.network.add_copy_layer("enc_ctx", "encoder_proj")
        #     self.base_model.network.add_split_dim_layer(
        #         "enc_value", "encoder_proj", dims=(self.att_num_heads, self.enc_value_dim // self.att_num_heads)
        #     )
        # else:
        #     self.base_model.network.add_linear_layer(
        #         "enc_ctx", "encoder", with_bias=True, n_out=self.enc_key_dim, l2=self.base_model.l2
        #     )
        #     self.base_model.network.add_split_dim_layer(
        #         "enc_value", "encoder", dims=(self.att_num_heads, self.enc_value_dim // self.att_num_heads)
        #     )
        #
        # self.base_model.network.add_linear_layer(
        #     "inv_fertility", "encoder", activation="sigmoid", n_out=self.att_num_heads, with_bias=False
        # )

        self.add_filter_blank_and_merge_labels_layers(self.base_model.network)
        self.decision_layer_name = "out_best_wo_blank"

        return self.dec_output

    def add_filter_blank_and_merge_labels_layers(self, net):
        """
        Add layers to filter out blank and merge repeated labels of a CTC output sequence.
        :param dict net: network dict
        """

        net["out_best_"] = {"class": "decide", "from": "output", "target": self.target_w_blank}
        net["out_best"] = {
            "class": "reinterpret_data",
            "from": "out_best_",
            "set_sparse_dim": 10025,
        }
        # shift to the right to create a boolean mask later where it is true if the previous label is equal
        net["shift_right"] = {
            "class": "shift_axis",
            "from": "out_best",
            "axis": "T",
            "amount": 1,
            "pad_value": -1,  # to have always True at the first pos
        }
        # reinterpret time axis to work with following layers
        net["out_best_time_reinterpret"] = {
            "class": "reinterpret_data",
            "from": "out_best",
            "size_base": "shift_right",  # [B,T|shift_axis]
        }
        net["unique_mask"] = {
            "class": "compare",
            "kind": "not_equal",
            "from": ["out_best_time_reinterpret", "shift_right"],
        }
        net["non_blank_mask"] = {
            "class": "compare",
            "from": "out_best_time_reinterpret",
            "value": 10025,
            "kind": "not_equal",
        }
        net["out_best_mask"] = {
            "class": "combine",
            "kind": "logical_and",
            "from": ["unique_mask", "non_blank_mask"],
        }
        net["out_best_wo_blank"] = {
            "class": "masked_computation",
            "from": "out_best_time_reinterpret",
            "mask": "out_best_mask",
            "unit": {"class": "copy"},
            "target": self.target,
        }
        net["edit_distance"] = {
            "class": "copy",
            "from": "out_best_wo_blank",
            "only_on_search": True,
            "loss": "edit_distance",
            "target": self.target,
        }