"""
Sisyphus config for i6 cluster
"""


def py():
    """run via Sisyphus"""
    from . import conformer_import_moh_att_2023_06_30

    conformer_import_moh_att_2023_06_30.py()

    from . import chunked_aed_import

    chunked_aed_import.py()