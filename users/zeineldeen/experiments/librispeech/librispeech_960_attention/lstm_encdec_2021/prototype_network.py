from typing import Union, Optional, Tuple, List, Dict, Any

from returnn_common.models.base import LayerRef, Module, LayerDictRaw, get_extern_data, get_special_layer
import returnn_common.models._generated_layers as layers
from returnn.util.basic import NotSpecified

from .specaugment_clean import SpecAugmentBlock


class Encoder2DConvBlock(Module):

    def __init__(self, l2=1e-07, dropout=0.5, act='relu', filter_sizes=[(3, 3)],
                 pool_sizes=[(1, 2)], channel_sizes=[32], padding='same'):
        super().__init__()
        self.split_feature_layer = layers.SplitDims(axis="F", dims=(-1, 1))
        self.conv_layers = []
        self.pool_layers = []
        self.dropout_layers = []
        for filter_size, pool_size, channel_size in zip(filter_sizes, pool_sizes, channel_sizes):
            self.conv_layers.append(layers.Conv(
                l2=l2, activation=act, filter_size=filter_size, n_out=channel_size, padding=padding))
            self.pool_layers.append(layers.Pool(pool_size=pool_size, padding='same', mode="max"))
        self.dropout = layers.Dropout(dropout=dropout)

    def forward(self, inp: LayerRef) -> LayerRef:
        x = self.split_feature_layer(inp)
        for conv_layer, pool_layer in zip(self.conv_layers, self.pool_layers):
            x = conv_layer(x)
            x = pool_layer(x)
            x = self.dropout(x)
        return x


class BLSTMPoolBlock(Module):

    def __init__(self, l2=1e-07, lstm_n_out=256, dropout=0.5, pool_size=1, rec_unit='nativelstm2'):
        super().__init__()
        self.lstm_fw = layers.RecUnit(direction=1, n_out=lstm_n_out, unit=rec_unit, l2=l2, dropout=dropout)
        self.lstm_bw = layers.RecUnit(direction=-1, n_out=lstm_n_out, unit=rec_unit, l2=l2, dropout=dropout)

        if pool_size > 1:
            self.pool = layers.Pool(pool_size=(pool_size,), padding="same", mode="max")
        else:
            self.pool = layers.Copy()

    def forward(self, inp: LayerRef) -> LayerRef:
        x_fw = self.lstm_fw(inp)
        x_bw = self.lstm_bw(inp)
        x_out = self.pool([x_fw, x_bw])
        return x_out


class SoftmaxCtcLossLayer(layers.Copy):

    def __init__(self,
                 loss_scale=1.0,
                 **kwargs):
        """
        :param str|None data_key:
        """
        super().__init__(**kwargs)
        self.loss_scale = loss_scale

    def get_opts(self):
        """
        Return all options
        """
        opts = {
            'loss_scale': self.loss_scale
        }
        opts = {key: value for (key, value) in opts.items() if value is not NotSpecified}
        return {**opts, **super().get_opts()}

    def make_layer_dict(self, source: Union[LayerRef, List[LayerRef], Tuple[LayerRef]],
                        target: LayerRef) -> LayerDictRaw:
        """
        Make layer dict
        """
        return {'class': 'softmax',
                'from': source,
                'loss': 'ctc',
                "beam_width": 1, "ctc_opts": {"ignore_longer_outputs_than_inputs": True},
                'target': target,
                **self.get_opts()}


class ConvBLSTMEncoder(Module):

    def __init__(self, l2=1e-07, audio_feature_key="audio_features", target_label_key="bpe_labels",
                 conv_dropout=0.5, conv_filter_sizes=[(3, 3), (3, 3)], conv_pool_sizes=[(1, 2), (1, 2)],
                 conv_channel_sizes=[32, 32], num_lstm_layers=6, lstm_single_dim=512, lstm_dropout=0.5,
                 lstm_pool_sizes=[3, 2]):
        super().__init__()
        self.audio_feauture_key = audio_feature_key
        self.target_label_key = target_label_key
        assert num_lstm_layers >= 2, "Needs two lstm layers as the last layer lstm layer is special"

        self.specaug_block = SpecAugmentBlock()

        self.conv_block = Encoder2DConvBlock(
            l2=l2, dropout=conv_dropout, filter_sizes=conv_filter_sizes,
            pool_sizes=conv_pool_sizes, channel_sizes=conv_channel_sizes
        )

        self.lstm_layers = []
        for i in range(num_lstm_layers - 1):
            pool_size = lstm_pool_sizes[i] if i < len(lstm_pool_sizes) else 1
            self.lstm_layers.append(
                BLSTMPoolBlock(l2=l2, lstm_n_out=lstm_single_dim, dropout=lstm_dropout, pool_size=pool_size)
            )

        self.last_lstm_layer = BLSTMPoolBlock(
            l2=l2, lstm_n_out=lstm_single_dim, dropout=lstm_dropout)

        self.encoder_state_copy_layer = layers.Copy()

        self.ctc_loss_block = SoftmaxCtcLossLayer()

    def forward(self) -> LayerRef:
        x = self.specaug_block(get_special_layer("base:base:data:" + self.audio_feauture_key))
        x = self.conv_block(x)
        for lstm_layer in self.lstm_layers:
            x  = lstm_layer(x)
        lstm_last = self.last_lstm_layer(x, name="final_lstm")
        encoder_state = self.encoder_state_copy_layer(lstm_last, name="encoder_state")
        self.ctc_loss_block(source=encoder_state, target=get_extern_data(self.target_label_key))
        return encoder_state



static_decoder = {
    'output': { 'class': 'rec',
                'from': [],
                'max_seq_len': "max_len_from('base:encoder')",
                'target': 'bpe_labels',
                'unit': { 'accum_att_weights': { 'class': 'eval',
                                                 'eval': 'source(0) + source(1) * source(2) * 0.5',
                                                 'from': ['prev:accum_att_weights', 'att_weights', 'base:inv_fertility'],
                                                 'out_type': {'dim': 1, 'shape': (None, 1)}},
                          'att': {'axes': 'except_batch', 'class': 'merge_dims', 'from': 'att0'},
                          'enc_transformed': {'class': 'linear', 'from': 'base:encoder/encoder_state', 'n_out': 1024},
                          'att0': {'base': 'base:encoder/encoder_state', 'class': 'generic_attention', 'weights': 'att_weights'},
                          'att_weights': {'class': 'dropout', 'dropout': 0.3, 'dropout_noise_shape': {'*': None}, 'from': 'att_weights0'},
                          'att_weights0': {'class': 'softmax_over_spatial', 'from': 'energy'},
                          'end': {'class': 'compare', 'from': 'output', 'kind': 'equal', 'value': 0},
                          'energy': {'activation': None, 'class': 'linear', 'from': 'energy_tanh', 'n_out': 1, 'with_bias': False},
                          'energy_in': {'class': 'combine', 'from': ['enc_transformed', 'weight_feedback', 's_transformed'], 'kind': 'add', 'n_out': 1024},
                          'energy_tanh': {'activation': 'tanh', 'class': 'activation', 'from': 'energy_in'},
                          'exp_energy': {'activation': 'exp', 'class': 'activation', 'from': 'energy'},
                          'output': {'beam_size': 12, 'class': 'choice', 'from': 'output_prob', 'initial_output': 0, 'target': 'bpe_labels'},
                          'output_prob': { 'L2': 0.001,
                                           'class': 'softmax',
                                           'dropout': 0.3,
                                           'from': 'readout',
                                           'loss': 'ce',
                                           'loss_opts': {'label_smoothing': 0.1},
                                           'target': 'classes'},
                          'readout': {'class': 'reduce_out', 'from': 'readout_in', 'mode': 'max', 'num_pieces': 2},
                          'readout_in': { 'activation': None,
                                          'class': 'linear',
                                          'from': ['s', 'prev:target_embed', 'att'],
                                          'n_out': 1000,
                                          'with_bias': True},
                          's': { 'class': 'rnn_cell',
                                 'from': ['prev:target_embed', 'prev:att'],
                                 'n_out': 1000,
                                 'unit': 'zoneoutlstm',
                                 'unit_opts': {'zoneout_factor_cell': 0.15, 'zoneout_factor_output': 0.05}},
                          's_transformed': {'activation': None, 'class': 'linear', 'from': 's', 'n_out': 1024, 'with_bias': False},
                          'target_embed': {'class': 'dropout', 'dropout': 0.3, 'dropout_noise_shape': {'*': None}, 'from': 'target_embed0'},
                          'target_embed0': { 'activation': None,
                                             'class': 'linear',
                                             'from': 'output',
                                             'initial_output': 0,
                                             'n_out': 621,
                                             'with_bias': False},
                          'weight_feedback': { 'activation': None,
                                               'class': 'linear',
                                               'from': 'prev:accum_att_weights',
                                               'n_out': 1024,
                                               'with_bias': False}}},
}