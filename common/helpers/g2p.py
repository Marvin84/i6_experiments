__all__ = ["G2PBasedOovAugmenter"]

import os
from typing import Optional

from sisyphus import tk
Path = tk.setup_path(__package__)

from i6_core.corpus.stats import ExtractOovWordsFromCorpusJob
from i6_core.g2p.apply import ApplyG2PModelJob
from i6_core.g2p.convert import BlissLexiconToG2PLexiconJob, G2POutputToBlissLexiconJob
from i6_core.g2p.train import TrainG2PModelJob


class G2PBasedOovAugmenter():
    def __init__(self,
                 original_bliss_lexicon,
                 g2p_model_path:Optional[str] = None,
                 train_args:Optional[dict] = None,
                 apply_args:Optional[dict] = None,
                 ):
        """
        :param original_bliss_lexicon: path to the original lexicon with OOV
        :param g2p_model_path: path to the g2p model, if none a g2p model is trained
        #######################################
        :param train_args = {
        "num_ramp_ups"   :4,
        "min_iter"       :1,
        "max_iter"       :60,
        "devel"          :"5%",
        "size_constrains":"0,1,0,1"
        }
        #######################################
        :param apply_args = {
        "variants_mass"  :1.0,
        "variants_number":1
        }
        """
        super().__init__()
        self.original_bliss_lexicon = original_bliss_lexicon
        self.g2p_model_path = g2p_model_path
        self.train_args = {}
        self.apply_args = {}

        if train_args is not None:
            self.train_args.update(train_args)

        if apply_args is not None:
            self.apply_args.update(apply_args)


    def train_and_set_g2p_model(self, train_lexicon:str, alias_path:str):
        g2p_lexicon_job = BlissLexiconToG2PLexiconJob(bliss_lexicon=train_lexicon)

        g2p_train_job = TrainG2PModelJob(
            g2p_lexicon=g2p_lexicon_job.out_g2p_lexicon,
            **self.train_args)
        g2p_train_job.add_alias(os.path.join(alias_path, "train_g2p_model"))
        self.g2p_model_path = g2p_train_job.out_best_model


    def get_g2p_augmented_bliss_lexicon(
            self,
            bliss_corpus:Path,
            corpus_name: str,
            alias_path:str,
            train_lexicon:Optional[str] = None,
    ):
        if train_lexicon is None:
            train_lexicon = self.original_bliss_lexicon

        extract_oov_job = ExtractOovWordsFromCorpusJob(
            bliss_corpus=bliss_corpus,
            bliss_lexicon=self.original_bliss_lexicon
        )
        extract_oov_job.add_alias(os.path.join(alias_path, "extract-oov-from-{}".format(corpus_name)))

        if self.g2p_model_path is None:
            self.train_and_set_g2p_model(train_lexicon, alias_path)

        g2p_apply_job = ApplyG2PModelJob(
            g2p_model=self.g2p_model_path,
            word_list_file=extract_oov_job.out_oov_words,
            **self.apply_args
        )
        g2p_apply_job.add_alias(os.path.join(alias_path, "apply-g2p-for-{}".format(corpus_name)))

        g2p_final_lex_job = G2POutputToBlissLexiconJob(
            iv_bliss_lexicon=self.original_bliss_lexicon,
            g2p_lexicon=g2p_apply_job.out_g2p_lexicon
        )
        g2p_final_lex_job.add_alias(os.path.join(alias_path, "g2p-output-to-bliss-{}".format(corpus_name)))

        return g2p_final_lex_job.out_oov_lexicon








