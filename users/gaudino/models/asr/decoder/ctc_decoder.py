from i6_core.returnn.config import CodeWrapper
from i6_experiments.users.zeineldeen.modules.network import ReturnnNetwork
from i6_experiments.users.zeineldeen.modules.attention import AttentionMechanism

attention_decoder_dict = {
    # reinterpreted for target_embed
    "output_reinterpret": {
        "class": "reinterpret_data",
        "from": "output",
        "set_sparse": True,
        "set_sparse_dim": 10025,  # V
        "initial_output": 0,
    },
    "prev_output_reinterpret": {
        "class": "copy",
        "from": "prev:output_reinterpret",
    },
    "trigg_att": {
        "class": "subnetwork",
        "from": [],
        "n_out": 10025,
        "name_scope": "",
        "subnetwork": {
            "target_embed0": {
                "class": "linear",
                "activation": None,
                "with_bias": False,
                "from": "base:output_reinterpret",
                "n_out": 640,
                "L2": 0.0001,
                "initial_output": 0,
            },
            "_target_embed": {
                "class": "dropout",
                "from": "target_embed0",
                "dropout": 0.1,
                "dropout_noise_shape": {"*": None},
            },
            "target_embed": {
                "class": "switch",
                "condition": "base:curr_mask",
                "true_from": "_target_embed",
                "false_from": "prev:target_embed",
            },
            "s_transformed": {
                "class": "linear",
                "activation": None,
                "with_bias": False,
                "from": "s",
                "n_out": 1024,
                "L2": 0.0001,
            },
            "_accum_att_weights": {
                "class": "eval",
                "eval": "source(0) + source(1) * source(2) * 0.5",
                "from": [
                    "prev:accum_att_weights",
                    "att_weights",
                    "base:base:inv_fertility",
                ],
                "out_type": {"dim": 1, "shape": (None, 1)},
            },
            "accum_att_weights": {
                "class": "switch",
                "condition": "base:prev_mask",
                "true_from": "_accum_att_weights",
                "false_from": "prev:accum_att_weights",
                "out_type": {"dim": 1, "shape": (None, 1)},
            },
            "weight_feedback": {
                "class": "linear",
                "activation": None,
                "with_bias": False,
                "from": "prev:accum_att_weights",
                "n_out": 1024,
            },
            "energy_in": {
                "class": "combine",
                "kind": "add",
                "from": [
                    "base:base:enc_ctx",
                    "weight_feedback",
                    "s_transformed",
                ],
                "n_out": 1024,
            },
            "energy_tanh": {
                "class": "activation",
                "activation": "tanh",
                "from": "energy_in",
            },
            "energy": {
                "class": "linear",
                "activation": None,
                "with_bias": False,
                "from": "energy_tanh",
                "n_out": 1,
                "L2": 0.0001,
            },
            "att_weights": {"class": "softmax_over_spatial", "from": "energy"},
            "att0": {
                "class": "generic_attention",
                "weights": "att_weights",
                "base": "base:base:enc_value",
            },
            "att": {
                "class": "merge_dims",
                "from": "att0",
                "axes": "except_batch",
            },
            "_s": {
                "class": "rnn_cell",
                "unit": "zoneoutlstm",
                "n_out": 1024,
                "from": ["prev:target_embed", "prev:att"],
                "L2": 0.0001,
                "unit_opts": {
                    "zoneout_factor_cell": 0.15,
                    "zoneout_factor_output": 0.05,
                },
                "name_scope": "s/rec",  # compatibility with old models
                "state": CodeWrapper("tf_v1.nn.rnn_cell.LSTMStateTuple('prev:s_c', 'prev:s_h')"),
            },
            "s": {
                "class": "switch",
                "condition": "base:prev_mask",
                "true_from": "_s",
                "false_from": "prev:s",
            },
            "_s_c": {
                "class": "get_last_hidden_state",
                "from": "_s",
                "key": "c",
                "n_out": 1024,
            },
            "s_c": {
                "class": "switch",
                "condition": "base:prev_mask",
                "true_from": "_s_c",
                "false_from": "prev:s_c",
            },
            "_s_h": {
                "class": "get_last_hidden_state",
                "from": "_s",
                "key": "h",
                "n_out": 1024,
            },
            "s_h": {
                "class": "switch",
                "condition": "base:prev_mask",
                "true_from": "_s_h",
                "false_from": "prev:s_h",
            },
            "readout_in": {
                "class": "linear",
                "activation": None,
                "with_bias": True,
                "from": ["s", "prev:target_embed", "att"],
                "n_out": 1024,
                "L2": 0.0001,
            },
            "readout": {
                "class": "reduce_out",
                "from": "readout_in",
                "num_pieces": 2,
                "mode": "max",
            },
            "output_prob": {
                "class": "softmax",
                "from": "readout",
                "target": "bpe_labels",
            },
            "output": {"class": "copy", "from": "output_prob"},
        },
    },
    # "att_log_scores": {
    #     "class": "activation",
    #     "activation": "safe_log",
    #     "from": "trigg_att",
    # },
}


class CTCDecoder:
    """
    Represents CTC decoder

    """

    def __init__(
        self,
        base_model,
        ctc_source="ctc",
        # dropout=0.0,
        # softmax_dropout=0.3,
        # label_smoothing=0.1,
        target="bpe_labels",
        target_w_blank="bpe_labels_w_blank",
        beam_size=12,
        # embed_dim=621,
        # embed_dropout=0.0,
        # lstm_num_units=1024,
        # output_num_units=1024,
        enc_key_dim=1024,
        # l2=None,
        # att_dropout=None,
        # rec_weight_dropout=None,
        # zoneout=False,
        # ff_init=None,
        add_ext_lm=False,
        lm_type=None,
        ext_lm_opts=None,
        lm_scale=0.3,
        add_att_dec=False,
        att_scale=0.3,
        use_ts_discount=False,
        ctc_scale=1.0,
        blank_prob_scale=0.0,  # in log space
        repeat_prob_scale=0.0,  # in log space
        ctc_prior_correction=False,
        prior_scale=1.0,
        # loc_conv_att_filter_size=None,
        # loc_conv_att_num_channels=None,
        # reduceout=True,
        att_num_heads=1,
        # embed_weight_init=None,
        # lstm_weights_init=None,
        length_normalization=False,
        # coverage_threshold=None,
        # coverage_scale=None,
        # ce_loss_scale=1.0,
        # use_zoneout_output: bool = False,
        logits=False,
        remove_eos=False,
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

        self.ctc_source = ctc_source

        # self.dropout = dropout
        # self.softmax_dropout = softmax_dropout
        # self.label_smoothing = label_smoothing
        #
        self.enc_key_dim = enc_key_dim
        self.enc_value_dim = base_model.enc_value_dim
        self.att_num_heads = att_num_heads
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

        self.add_ext_lm = add_ext_lm
        self.lm_scale = lm_scale
        self.lm_type = lm_type
        self.ext_lm_opts = ext_lm_opts

        self.add_att_dec = add_att_dec
        self.att_scale = att_scale
        self.use_ts_discount = use_ts_discount

        self.ctc_scale = ctc_scale
        self.blank_prob_scale = blank_prob_scale
        self.repeat_prob_scale = repeat_prob_scale
        self.ctc_prior_correction = ctc_prior_correction
        self.prior_scale = prior_scale
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

        self.logits = logits
        self.remove_eos = remove_eos

        self.network = ReturnnNetwork()
        self.subnet_unit = ReturnnNetwork()
        self.dec_output = None
        self.output_prob = None

    def add_norm_layer(self, subnet_unit: ReturnnNetwork, name: str):
        """Add layer norm layer"""
        subnet_unit.update(
            {
                f"{name}_norm": {
                    "class": "reduce",
                    "mode": "logsumexp",
                    "from": name,
                    "axis": "f",
                },
                f"{name}_renorm": {
                    "class": "combine",
                    "kind": "sub",
                    "from": [name, f"{name}_norm"],
                },
            }
        )
        return f"{name}_renorm"

    def add_masks(self, subnet_unit: ReturnnNetwork):
        subnet_unit.update(
            {
                "not_repeat_mask": {
                    "class": "compare",
                    "from": ["output", "prev:output"],
                    "kind": "not_equal",
                    "initial_output": True,
                },
                "is_curr_out_not_blank_mask": {
                    "class": "compare",
                    "kind": "not_equal",
                    "from": "output",
                    "value": 10025,
                },
                "is_prev_out_not_blank_mask": {
                    "class": "compare",
                    "kind": "not_equal",
                    "from": "prev:output",
                    "value": 10025,
                },
                "curr_mask": {
                    "class": "combine",
                    "kind": "logical_and",
                    "from": ["is_curr_out_not_blank_mask", "not_repeat_mask"],
                    "initial_output": True,
                },
                "prev_mask": {
                    "class": "copy",
                    "from": "prev:curr_mask",
                },
            }
        )

    def add_ctc_scores(self, subnet_unit: ReturnnNetwork):
        if self.ctc_prior_correction:
            subnet_unit.update(
                {
                    "ctc_log_scores_no_prior": {
                        "class": "activation",
                        "activation": "safe_log",
                        "from": "data:source",
                    },
                    "scaled_ctc_log_prior": {
                        "class": "eval",
                        "from": "base:ctc_log_prior",
                        "eval": f"source(0) * {self.prior_scale}",
                    },
                    "ctc_log_scores_w_prior": {
                        "class": "combine",
                        "from": ["ctc_log_scores_no_prior", "scaled_ctc_log_prior"],
                        "kind": "sub",
                    },
                }
            )
            self.add_norm_layer(subnet_unit, "ctc_log_scores_w_prior")
            subnet_unit.update(
                {
                    "ctc_log_scores": {
                        "class": "copy",
                        "from": "ctc_log_scores_w_prior_renorm",
                    },
                }
            )
        else:
            subnet_unit.update(
                {
                    "ctc_log_scores": {
                        "class": "activation",
                        "activation": "safe_log",
                        "from": "data:source",
                    },  # [B,V+1]
                }
            )

        subnet_unit.update(
            {
                "blank_log_prob": {
                    "class": "gather",
                    "from": "ctc_log_scores",
                    "position": 10025,
                    "axis": "f",
                },  # [B]
                "blank_log_prob_expand": {
                    "class": "expand_dims",
                    "from": "blank_log_prob",
                    "axis": "f",
                },  # [B,1]
                "blank_prob": {
                    "class": "gather",
                    "from": "data:source",
                    "position": 10025,
                    "axis": "f",
                },
            }
        )

    def add_score_combination(self, subnet_unit: ReturnnNetwork, att_layer: str = None, lm_layer: str = None):
        one_minus_term_scale = 1
        combine_list = []
        if self.ctc_scale > 0:
            combine_list.append("scaled_ctc_log_scores")
        if self.add_att_dec:
            subnet_unit.update(
                {
                    "att_log_scores": {
                        "class": "activation",
                        "activation": "safe_log",
                        "from": att_layer,
                    },
                    "scaled_att_log_scores": {
                        "class": "eval",
                        "from": "att_log_scores",
                        "eval": f"{self.att_scale} * source(0)",
                    },
                }
            )
            combine_list.append("scaled_att_log_scores")

        if self.add_ext_lm:
            subnet_unit.update(
                {
                    "lm_log_scores": {
                        "class": "activation",
                        "activation": "safe_log",
                        "from": lm_layer,
                    },
                    "scaled_lm_log_scores": {
                        "class": "eval",
                        "from": "lm_log_scores",
                        "eval": f"{self.lm_scale} * source(0)",
                    },
                }
            )
            combine_list.append("scaled_lm_log_scores")

        if self.use_ts_discount:
            # not working yet
            subnet_unit.update(
                {
                    "const1": {"class": "constant", "value": 1, "dtype": "int32"},
                    "prev_n_att_contrib_plus_1": {
                        "class": "add",
                        "from": ["prev:n_att_contrib", "const1"],
                    },
                    "n_att_contrib": {
                        "class": "switch",
                        "condition": "curr_mask",
                        "true_from": "prev_n_att_contrib_plus_1",
                        "false_from": "prev:n_att_contrib",
                        "initial_output": 0,
                    },
                    "n_att_contrib_plus_1": {
                        "class": "add",
                        "from": ["n_att_contrib", "const1"],
                    },
                    # TODO: how to access all hypothesis in beam?
                    "max_n_att_contrib": {
                        "class": "reduce",
                        "mode": "max",
                        "from": "n_att_contrib",
                    },
                    "log_ts_discount": {
                        "class": "eval",
                        "from": ["n_att_contrib", "max_n_att_contrib"],
                        "eval": "source(0)/source(1)",
                        "initial_output": 0,
                    },
                }
            )

        subnet_unit.update(
            {
                # log p_comb_sigma = log p_att_sigma + log p_ctc_sigma (using only labels without blank)
                "ctc_log_scores_slice": {
                    "class": "slice",
                    "from": "ctc_log_scores",
                    "axis": "f",
                    "slice_start": 0,
                    "slice_end": 10025,  # excluding blank
                },  # [B,V]
                "ctc_log_scores_norm": {
                    "class": "reduce",
                    "mode": "logsumexp",
                    "from": "ctc_log_scores_slice",
                    "axis": "f",
                },
                # renormalize label probs without blank
                "ctc_log_scores_renorm": {
                    "class": "combine",
                    "kind": "sub",
                    "from": ["ctc_log_scores_slice", "ctc_log_scores_norm"],
                },
                "scaled_ctc_log_scores": {
                    "class": "eval",
                    "from": "ctc_log_scores_renorm",
                    "eval": f"{self.ctc_scale} * source(0)",
                },
                "combined_att_ctc_scores": {
                    "class": "combine",
                    "kind": "add",
                    "from": combine_list,
                },  # [B,V]
                # log p_ctc_sigma' (blank | ...)
                # ----------------------------- #
                "vocab_range": {"class": "range", "limit": 10025},
                "prev_output_reinterpret": {
                    "class": "reinterpret_data",
                    "from": "prev:output",
                    "set_sparse": True,
                    "set_sparse_dim": 10025,
                },
                "prev_repeat_mask": {
                    "class": "compare",
                    "from": ["prev_output_reinterpret", "vocab_range"],
                    "kind": "equal",  # always False for blank
                },
                # ----------------------------- #
                # p_ctc_sigma' (blank | ...)
                "scaled_blank_prob": {
                    "class": "eval",
                    "from": "blank_prob",
                    "eval": f"source(0) ** {one_minus_term_scale}",
                },
                "scaled_blank_log_prob": {
                    "class": "eval",
                    "from": "blank_log_prob",
                    "eval": f"source(0) - {self.blank_prob_scale} ",
                },
                "scaled_blank_log_prob_expand": {
                    "class": "expand_dims",
                    "from": "scaled_blank_log_prob",
                    "axis": "f",
                },  # [B,1]
                "one": {"class": "constant", "value": 1.0},
                "prev_ctc_log_scores": {
                    "class": "gather",
                    "from": "ctc_log_scores",
                    "position": "prev:output",
                    "axis": "f",
                },
                "scaled_prev_ctc_log_scores": {
                    "class": "eval",
                    "from": "prev_ctc_log_scores",
                    "eval": f"{one_minus_term_scale} * source(0)",
                },
                "scaled_prev_ctc_scores": {
                    "class": "activation",
                    "activation": "safe_exp",
                    "from": "scaled_prev_ctc_log_scores",
                },
                "repeat_prob_term": {
                    "class": "switch",
                    "condition": "is_prev_out_not_blank_mask",
                    "true_from": "scaled_prev_ctc_scores",  # p(label:=prev:label|...)
                    "false_from": 0.0,
                },
                "1_minus_term_": {
                    "class": "combine",
                    "kind": "sub",
                    "from": ["one", "scaled_blank_prob"],
                },
                "1_minus_term": {
                    "class": "combine",
                    "kind": "sub",
                    "from": ["1_minus_term_", "repeat_prob_term"],
                },
                "1_minus_term_log": {
                    "class": "activation",
                    "activation": "safe_log",
                    "from": "1_minus_term",
                },
                # [1 - P_ctc(blank|...) - P_ctc(label:=prev:label|...)] * P_att(label|...)  # prev:label != blank
                "p_comb_sigma_prime_label": {
                    "class": "combine",
                    "kind": "add",
                    "from": ["1_minus_term_log", "combined_att_ctc_scores"],
                },
                # ----------------------------- #
                "scaled_ctc_log_scores_slice": {
                    "class": "eval",
                    "from": "ctc_log_scores_slice",
                    "eval": f"source(0) - {self.repeat_prob_scale}",
                },
                "scaled_label_score": {
                    "class": "switch",
                    "condition": "prev_repeat_mask",
                    "true_from": "scaled_ctc_log_scores_slice",
                    # log P_ctc(label|...) in case label (not blank) is repeated
                    "false_from": "p_comb_sigma_prime_label",  # [1 - ...] * p_comb_sigma
                },
                "p_comb_sigma_prime": {
                    "class": "concat",
                    "from": [("scaled_label_score", "f"), ("scaled_blank_log_prob_expand", "f")],
                },  # [B,V+1]
                "output": {
                    "class": "choice",
                    "target": "bpe_labels_w_blank",
                    "beam_size": self.beam_size,
                    "from": "p_comb_sigma_prime" if not self.remove_eos else "p_comb_sigma_prime_w_eos",
                    "input_type": "logits" if self.logits else "log_prob",
                    "initial_output": 0,
                    "length_normalization": self.length_normalization,
                },
            }
        )

        if self.remove_eos:
            subnet_unit.update({
                "combined_ts_log_scores": {
                    "class": "combine",
                    "kind": "add",
                    "from": ["scaled_att_log_scores", "scaled_lm_log_scores"],
                },
                "combined_ts_scores": {
                    "class": "activation",
                    "activation": "safe_exp",
                    "from": "combined_ts_log_scores",
                },
            })
            if self.add_ext_lm and not self.add_att_dec:
                ts_score = lm_layer
            elif self.add_att_dec and not self.add_ext_lm:
                ts_score = att_layer
            else:
                ts_score = "combined_ts_scores"

            subnet_unit.update(
                {
                    "t": {"class": "copy", "from": ":i", "debug_print_layer_output": True},
                    "last_frame": {
                        "class": "eval",
                        "from": ["t", "base:enc_seq_len"],
                        "eval": "tf.equal(source(0)+1, source(1))",  # [B] (bool)
                        "out_type": {"dtype": "bool"},
                    },
                    "ts_eos_prob": {
                        "class": "gather",
                        "from": ts_score,
                        "position": 0,
                        "axis": "f",
                    },
                    "ts_eos_prob_expand": {
                        "class": "expand_dims",
                        "from": "ts_eos_prob",
                        "axis": "f",
                    },
                    "zeros": {"class": "constant", "value": 0.0, "shape": (10025,), "with_batch_dim": True},
                    "last_frame_prob": {
                        "class": "concat",
                        "from": [
                            ("ts_eos_prob_expand", "f"),
                            ("zeros", "f"),
                        ],
                        "allow_broadcast": True,
                    },
                    "last_frame_log_prob": {
                        "class": "activation",
                        "activation": "safe_log",
                        "from": "last_frame_prob",
                    },
                    "p_comb_sigma_prime_w_eos": {
                        "class": "switch",
                        "condition": "last_frame",
                        "true_from": "last_frame_log_prob",
                        "false_from": "p_comb_sigma_prime",
                    },
                }
            )

    def add_greedy_decoder(self, subnet_unit: ReturnnNetwork):
        source = "data:source"
        input_type = None
        if self.blank_prob_scale > 0.0:
            subnet_unit.update(
                {
                    "ctc_log_scores": {
                        "class": "activation",
                        "activation": "safe_log",
                        "from": "data:source",
                    },
                    "ctc_log_scores_slice": {
                        "class": "slice",
                        "from": "ctc_log_scores",
                        "axis": "f",
                        "slice_start": 0,
                        "slice_end": 10025,
                    },
                    "blank_log_prob": {
                        "class": "gather",
                        "from": "ctc_log_scores",
                        "position": 10025,
                        "axis": "f",
                    },
                    "scaled_blank_log_prob": {
                        "class": "eval",
                        "from": "blank_log_prob",
                        "eval": f"source(0) - {self.blank_prob_scale}",
                    },
                    "scaled_blank_log_prob_expand": {
                        "class": "expand_dims",
                        "from": "scaled_blank_log_prob",
                        "axis": "f",
                    },
                    "ctc_w_blank_scale": {
                        "class": "concat",
                        "from": [
                            ("ctc_log_scores_slice", "f"),
                            ("scaled_blank_log_prob_expand", "f"),
                        ],
                    },
                }
            )
            source = "ctc_w_blank_scale"
            input_type = "log_prob"

        elif self.ctc_prior_correction:
            subnet_unit.update(
                {
                    "scaled_ctc_log_prior": {
                        "class": "eval",
                        "from": "base:ctc_log_prior",
                        "eval": f"source(0) * {self.prior_scale}",
                    },
                    "ctc_log_scores": {
                        "class": "activation",
                        "activation": "safe_log",
                        "from": "data:source",
                    },
                    "ctc_log_scores_w_prior": {
                        "class": "combine",
                        "kind": "sub",
                        "from": ["ctc_log_scores", "scaled_ctc_log_prior"],
                    },
                }
            )
            source = "ctc_log_scores_w_prior"

        if self.length_normalization:
            subnet_unit.add_choice_layer(
                "output", source, target=self.target_w_blank, beam_size=1, input_type=input_type, initial_output=0
            )
        else:
            subnet_unit.add_choice_layer(
                "output",
                source,
                target=self.target_w_blank,
                beam_size=2,
                input_type=input_type,
                initial_output=0,
            )

        # recurrent subnetwork
        dec_output = self.network.add_subnet_rec_layer(
            "output", unit=subnet_unit.get_net(), target=self.target_w_blank, source=self.ctc_source
        )
        self.network["output"].pop("max_seq_len", None)

        return dec_output

    def get_lm_subnet_unit(self):
        lm_net_out = ReturnnNetwork()

        ext_lm_subnet = self.ext_lm_opts["lm_subnet"]

        # masked computaiton specific
        if self.lm_type == "lstm":
            ext_lm_subnet["input"]["from"] = "base:prev_output_reinterpret"
        elif self.lm_type == "trafo":
            ext_lm_subnet["target_embed_raw"]["from"] = "base:prev_output_reinterpret"

        assert isinstance(ext_lm_subnet, dict)

        ext_lm_model = self.ext_lm_opts.get("lm_model", None)
        if ext_lm_model:
            load_on_init = ext_lm_model
        else:
            assert (
                "load_on_init_opts" in self.ext_lm_opts
            ), "load_on_init opts or lm_model are missing for loading subnet."
            assert "filename" in self.ext_lm_opts["load_on_init_opts"], "Checkpoint missing for loading subnet."
            load_on_init = self.ext_lm_opts["load_on_init_opts"]
        lm_net_out.add_subnetwork("lm_output", [], subnetwork_net=ext_lm_subnet, load_on_init=load_on_init)

        return lm_net_out.get_net()["lm_output"]

    def add_greedy_with_ext_lm_decoder(self, subnet_unit: ReturnnNetwork):
        self.add_ctc_scores(subnet_unit)
        # add masks
        self.add_masks(subnet_unit)
        # add lstm lm
        subnet_unit.update(
            {
                "prev_output_reinterpret": {
                    "class": "reinterpret_data",
                    "from": "prev:output",
                    "set_sparse": True,
                    "set_sparse_dim": 10025,
                },
                # lm
                "lm_output": {
                    "class": "masked_computation",
                    "mask": "prev_mask",
                    "from": [],
                    "unit": self.get_lm_subnet_unit(),
                },
                "lm_output_prob": {
                    "class": "activation",
                    "activation": "softmax",
                    "from": "lm_output",
                    "target": "bpe_labels",
                },
            }
        )

        self.add_score_combination(subnet_unit, lm_layer="lm_output_prob")

        # recurrent subnetwork
        dec_output = self.network.add_subnet_rec_layer(
            "output", unit=subnet_unit.get_net(), target=self.target_w_blank, source=self.ctc_source
        )
        self.network["output"].pop("max_seq_len", None)

        return dec_output

    def add_greedy_decoder_with_att(self, subnet_unit: ReturnnNetwork):
        self.add_ctc_scores(subnet_unit)
        # add masks
        self.add_masks(subnet_unit)
        # add attention decoder
        subnet_unit.update(attention_decoder_dict)

        self.add_score_combination(subnet_unit, att_layer="trigg_att")

        # recurrent subnetwork
        dec_output = self.network.add_subnet_rec_layer(
            "output", unit=subnet_unit.get_net(), target=self.target_w_blank, source=self.ctc_source
        )
        self.network["output"].pop("max_seq_len", None)

        return dec_output

    def add_greedy_decoder_with_lm_and_att(self, subnet_unit):
        self.add_ctc_scores(subnet_unit)
        # add masks
        self.add_masks(subnet_unit)
        # add attention decoder
        subnet_unit.update(attention_decoder_dict)
        # add lstm lm
        subnet_unit.update(
            {
                # lm
                "lm_output": {
                    "class": "masked_computation",
                    "mask": "prev_mask",
                    "from": [],
                    "unit": self.get_lm_subnet_unit(),
                },
                "lm_output_prob": {
                    "class": "activation",
                    "activation": "softmax",
                    "from": "lm_output",
                    "target": "bpe_labels",
                },
            }
        )

        self.add_score_combination(subnet_unit, att_layer="trigg_att", lm_layer="lm_output_prob")

        # recurrent subnetwork
        dec_output = self.network.add_subnet_rec_layer(
            "output", unit=subnet_unit.get_net(), target=self.target_w_blank, source=self.ctc_source
        )
        self.network["output"].pop("max_seq_len", None)

        return dec_output

    def remove_eos_from_ctc_logits(self):
        """Remove eos from ctc logits and set ctc_source to the new logits."""
        self.base_model.network.add_slice_layer(
            "ctc_no_eos_no_blank_slice", self.ctc_source, axis="f", slice_start=1, slice_end=10025
        )
        self.base_model.network.add_slice_layer("ctc_eos_slice", self.ctc_source, axis="f", slice_start=0, slice_end=1)
        self.base_model.network.add_slice_layer("ctc_blank_slice", self.ctc_source, axis="f", slice_start=10025, slice_end=10026)
        self.base_model.network.add_eval_layer("zeros", "ctc_eos_slice", eval="source(0)*0.0")
        self.base_model.network.update(
            {
                "ctc_blank_plus_eos": {
                    "class": "combine",
                    "kind": "add",
                    "from": ["ctc_blank_slice", "ctc_eos_slice"],
                },
                "ctc_no_eos": {
                    "class": "concat",
                    "from": [
                        ("zeros", "f"),
                        ("ctc_no_eos_no_blank_slice", "f"),
                        ("ctc_blank_plus_eos", "f"),
                    ],
                },
            }
        )
        self.ctc_source = "ctc_no_eos"
        if self.add_att_dec or self.add_ext_lm:
            self.base_model.network.update(
                {
                    "ctc_no_eos_postfix_in_time": {
                        "class": "postfix_in_time",
                        "from": "ctc_no_eos",
                    },
                }
            )
            self.ctc_source = "ctc_no_eos_postfix_in_time"

    def create_network(self):
        if self.remove_eos:
            self.remove_eos_from_ctc_logits()
        if self.add_ext_lm and not self.add_att_dec:
            self.base_model.network.add_length_layer("enc_seq_len", "encoder", sparse=False)
            self.dec_output = self.add_greedy_with_ext_lm_decoder(self.subnet_unit)
        elif self.add_att_dec and not self.add_ext_lm:
            self.add_enc_output_for_att()
            self.dec_output = self.add_greedy_decoder_with_att(self.subnet_unit)
        elif self.add_att_dec and self.add_ext_lm:
            self.add_enc_output_for_att()
            self.dec_output = self.add_greedy_decoder_with_lm_and_att(self.subnet_unit)
        else:
            self.dec_output = self.add_greedy_decoder(self.subnet_unit)

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

    def add_enc_output_for_att(self):
        # add to base model
        self.base_model.network.add_linear_layer(
            "enc_ctx", "encoder", with_bias=True, n_out=self.enc_key_dim, l2=self.base_model.l2
        )
        self.base_model.network.add_split_dim_layer(
            "enc_value", "encoder", dims=(self.att_num_heads, self.enc_value_dim // self.att_num_heads)
        )
        self.base_model.network.add_linear_layer(
            "inv_fertility", "encoder", activation="sigmoid", n_out=self.att_num_heads, with_bias=False
        )
        self.base_model.network.add_length_layer("enc_seq_len", "encoder", sparse=False)
