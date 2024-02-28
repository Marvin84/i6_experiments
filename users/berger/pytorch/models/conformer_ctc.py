from dataclasses import dataclass
from typing import Optional
from i6_experiments.users.berger.systems.dataclasses import ConfigVariant

import torch
from i6_experiments.common.setups.returnn_pytorch.serialization import Collection
from i6_experiments.common.setups.serialization import Import, PartialImport
from i6_experiments.users.berger.pytorch.serializers.basic import (
    get_basic_pt_network_serializer,
)
from i6_models.primitives.feature_extraction import LogMelFeatureExtractionV1, LogMelFeatureExtractionV1Config
from i6_models.parts.frontend.generic_frontend import (
    GenericFrontendV1,
    GenericFrontendV1Config,
    FrontendLayerType,
)
import i6_models.parts.conformer as conformer_parts_i6
import i6_models.assemblies.conformer as conformer_i6
import i6_experiments.users.berger.pytorch.custom_parts as custom_parts
from i6_models.config import ModelConfiguration, ModuleFactoryV1
from i6_models.parts.conformer.norm import LayerNormNC
from .util import lengths_to_padding_mask

from ..custom_parts.specaugment import (
    SpecaugmentConfigV1,
    SpecaugmentModuleV1,
    SpecaugmentByLengthConfigV1,
    SpecaugmentByLengthModuleV1,
)


@dataclass
class ConformerCTCConfig(ModelConfiguration):
    feature_extraction: Optional[ModuleFactoryV1]
    specaugment: ModuleFactoryV1
    conformer: ModuleFactoryV1
    dim: int
    target_size: int
    dropout: float


class ConformerCTCModel(torch.nn.Module):
    def __init__(self, step: int, cfg: ConformerCTCConfig, **kwargs):
        super().__init__()
        if cfg.feature_extraction is None:
            self.feature_extraction = None
        else:
            self.feature_extraction = cfg.feature_extraction()
        self.specaugment = cfg.specaugment()
        self.conformer = cfg.conformer()
        self.dropout = torch.nn.Dropout(cfg.dropout)
        self.final_linear = torch.nn.Linear(cfg.dim, cfg.target_size)

    def forward(
        self,
        audio_features: torch.Tensor,
        audio_features_len: Optional[torch.Tensor] = None,
    ):
        with torch.no_grad():
            if self.feature_extraction is None:
                assert audio_features_len is not None
                x = audio_features
                input_len = audio_features_len
            else:
                x, input_len = self.feature_extraction(audio_features)

            sequence_mask = lengths_to_padding_mask(input_len)

            x = self.specaugment(x)  # [B, T, F]

        x, sequence_mask = self.conformer(x, sequence_mask)  # [B, T, F]
        x = self.dropout(x)
        logits = self.final_linear(x)  # [B, T, F]
        log_probs = torch.log_softmax(logits, dim=2)

        return log_probs, torch.sum(sequence_mask, dim=1).type(torch.int32)


def get_train_serializer(
    model_config: ConformerCTCConfig,
) -> Collection:
    pytorch_package = __package__.rpartition(".")[0]
    return get_basic_pt_network_serializer(
        module_import_path=f"{__name__}.{ConformerCTCModel.__name__}",
        model_config=model_config,
        additional_serializer_objects=[
            Import(f"{pytorch_package}.train_steps.ctc.train_step"),
        ],
    )


def get_prior_serializer(
    model_config: ConformerCTCConfig,
) -> Collection:
    pytorch_package = __package__.rpartition(".")[0]
    return get_basic_pt_network_serializer(
        module_import_path=f"{__name__}.{ConformerCTCModel.__name__}",
        model_config=model_config,
        additional_serializer_objects=[
            Import(f"{pytorch_package}.forward.basic.forward_step"),
            Import(f"{pytorch_package}.forward.prior_callback.ComputePriorCallback", import_as="forward_callback"),
        ],
    )


def get_recog_serializer(
    model_config: ConformerCTCConfig,
) -> Collection:
    pytorch_package = __package__.rpartition(".")[0]
    return get_basic_pt_network_serializer(
        module_import_path=f"{__name__}.{ConformerCTCModel.__name__}",
        model_config=model_config,
        additional_serializer_objects=[Import(f"{pytorch_package}.forward.basic.forward_step")],
    )


def get_serializer(model_config: ConformerCTCConfig, variant: ConfigVariant) -> Collection:
    if variant == ConfigVariant.TRAIN:
        return get_train_serializer(model_config)
    if variant == ConfigVariant.PRIOR:
        return get_prior_serializer(model_config)
    if variant == ConfigVariant.ALIGN:
        return get_recog_serializer(model_config)
    if variant == ConfigVariant.RECOG:
        return get_recog_serializer(model_config)
    raise NotImplementedError


def get_default_config_v1(num_inputs: int, num_outputs: int) -> ConformerCTCConfig:
    specaugment = ModuleFactoryV1(
        module_class=SpecaugmentModuleV1,
        cfg=SpecaugmentConfigV1(
            time_min_num_masks=1,
            time_max_num_masks=1,
            time_mask_max_size=15,
            freq_min_num_masks=1,
            freq_max_num_masks=num_inputs // 10,
            freq_mask_max_size=5,
        ),
    )

    frontend_cfg = VGG4LayerActFrontendV1Config(
        in_features=num_inputs,
        conv1_channels=32,
        conv2_channels=32,
        conv3_channels=64,
        conv4_channels=64,
        conv_kernel_size=(3, 3),
        conv_padding=None,
        pool1_kernel_size=(2, 2),
        pool1_stride=None,
        pool1_padding=None,
        pool2_kernel_size=(2, 1),
        pool2_stride=None,
        pool2_padding=None,
        activation=torch.nn.SiLU(),
        out_features=512,
    )

    frontend = ModuleFactoryV1(VGG4LayerActFrontendV1, frontend_cfg)

    ff_cfg = conformer_parts_i6.ConformerPositionwiseFeedForwardV1Config(
        input_dim=512,
        hidden_dim=2048,
        dropout=0.1,
        activation=torch.nn.SiLU(),
    )

    mhsa_cfg = conformer_parts_i6.ConformerMHSAV1Config(
        input_dim=512,
        num_att_heads=8,
        att_weights_dropout=0.1,
        dropout=0.1,
    )

    conv_cfg = conformer_parts_i6.ConformerConvolutionV1Config(
        channels=512,
        kernel_size=31,
        dropout=0.1,
        activation=torch.nn.SiLU(),
        norm=torch.nn.BatchNorm1d(num_features=512, affine=False),
    )

    block_cfg = conformer_i6.ConformerBlockV1Config(
        ff_cfg=ff_cfg,
        mhsa_cfg=mhsa_cfg,
        conv_cfg=conv_cfg,
    )

    conformer_cfg = conformer_i6.ConformerEncoderV1Config(
        num_layers=12,
        frontend=frontend,
        block_cfg=block_cfg,
    )

    return ConformerCTCConfig(
        feature_extraction=None,
        specaugment=specaugment,
        conformer=ModuleFactoryV1(module_class=conformer_i6.ConformerEncoderV1, cfg=conformer_cfg),
        dim=512,
        target_size=num_outputs,
        dropout=0.1,
    )


def get_default_config_v2(num_inputs: int, num_outputs: int) -> ConformerCTCConfig:
    specaugment = ModuleFactoryV1(
        module_class=SpecaugmentByLengthModuleV1,
        cfg=SpecaugmentByLengthConfigV1(
            time_min_num_masks=1,
            time_max_mask_per_n_frames=30,
            time_mask_max_size=20,
            freq_min_num_masks=0,
            freq_max_num_masks=9,
            freq_mask_max_size=5,
        ),
    )

    frontend_cfg = custom_parts.GenericVGGFrontendV1Config(
        in_features=num_inputs,
        out_features=384,
        conv_channels=[32, 64, 64, 32],
        conv_kernel_sizes=[(3, 3), (3, 3), (3, 3), (3, 3)],
        conv_strides=[(1, 1), (1, 1), (1, 1), (1, 1)],
        pool_sizes=[None, (2, 1), None, (2, 1)],
        activations=[None, None, None, torch.nn.SiLU()],
    )

    frontend = ModuleFactoryV1(custom_parts.GenericVGGFrontendV1, frontend_cfg)

    ff_cfg = conformer_parts_i6.ConformerPositionwiseFeedForwardV1Config(
        input_dim=384,
        hidden_dim=1536,
        dropout=0.1,
        activation=torch.nn.SiLU(),
    )

    mhsa_cfg = conformer_parts_i6.ConformerMHSAV1Config(
        input_dim=384,
        num_att_heads=6,
        att_weights_dropout=0.1,
        dropout=0.1,
    )

    conv_cfg = conformer_parts_i6.ConformerConvolutionV1Config(
        channels=384,
        kernel_size=31,
        dropout=0.1,
        activation=torch.nn.SiLU(),
        norm=LayerNormNC(384),
    )

    block_cfg = conformer_i6.ConformerBlockV1Config(
        ff_cfg=ff_cfg,
        mhsa_cfg=mhsa_cfg,
        conv_cfg=conv_cfg,
    )

    conformer_cfg = conformer_i6.ConformerEncoderV1Config(
        num_layers=12,
        frontend=frontend,
        block_cfg=block_cfg,
    )

    return ConformerCTCConfig(
        feature_extraction=None,
        specaugment=specaugment,
        conformer=ModuleFactoryV1(conformer_i6.ConformerEncoderV1, cfg=conformer_cfg),
        dim=384,
        target_size=num_outputs,
        dropout=0.1,
    )


def get_default_config_v3(num_outputs: int) -> ConformerCTCConfig:
    feature_extraction = ModuleFactoryV1(
        module_class=LogMelFeatureExtractionV1,
        cfg=LogMelFeatureExtractionV1Config(
            sample_rate=16000,
            win_size=0.025,
            hop_size=0.01,
            f_min=60,
            f_max=7600,
            min_amp=1e-10,
            num_filters=80,
            center=False,
        ),
    )
    specaugment = ModuleFactoryV1(
        module_class=SpecaugmentByLengthModuleV1,
        cfg=SpecaugmentByLengthConfigV1(
            time_min_num_masks=2,
            time_max_mask_per_n_frames=25,
            time_mask_max_size=20,
            freq_min_num_masks=2,
            freq_max_num_masks=16,
            freq_mask_max_size=5,
        ),
    )

    frontend = ModuleFactoryV1(
        GenericFrontendV1,
        GenericFrontendV1Config(
            in_features=80,
            layer_ordering=[
                FrontendLayerType.Conv2d,
                FrontendLayerType.Conv2d,
                FrontendLayerType.Pool2d,
                FrontendLayerType.Conv2d,
                FrontendLayerType.Conv2d,
                FrontendLayerType.Pool2d,
                FrontendLayerType.Activation,
            ],
            conv_kernel_sizes=[(3, 3), (3, 3), (3, 3), (3, 3)],
            conv_paddings=None,
            conv_out_dims=[32, 64, 64, 32],
            conv_strides=[(1, 1), (1, 1), (1, 1), (1, 1)],
            pool_kernel_sizes=[(2, 1), (2, 1)],
            pool_strides=None,
            pool_paddings=None,
            activations=[torch.nn.ReLU()],
            out_features=384,
        ),
    )

    ff_cfg = conformer_parts_i6.ConformerPositionwiseFeedForwardV1Config(
        input_dim=384,
        hidden_dim=1536,
        dropout=0.2,
        activation=torch.nn.SiLU(),
    )

    mhsa_cfg = conformer_parts_i6.ConformerMHSAV1Config(
        input_dim=384,
        num_att_heads=4,
        att_weights_dropout=0.2,
        dropout=0.2,
    )

    conv_cfg = conformer_parts_i6.ConformerConvolutionV1Config(
        channels=384,
        kernel_size=31,
        dropout=0.2,
        activation=torch.nn.SiLU(),
        norm=LayerNormNC(384),
    )

    block_cfg = conformer_i6.ConformerBlockV1Config(
        ff_cfg=ff_cfg,
        mhsa_cfg=mhsa_cfg,
        conv_cfg=conv_cfg,
    )

    conformer_cfg = conformer_i6.ConformerEncoderV1Config(
        num_layers=12,
        frontend=frontend,
        block_cfg=block_cfg,
    )

    return ConformerCTCConfig(
        feature_extraction=feature_extraction,
        specaugment=specaugment,
        conformer=ModuleFactoryV1(conformer_i6.ConformerEncoderV1, cfg=conformer_cfg),
        dim=384,
        target_size=num_outputs,
        dropout=0.2,
    )
