"""
These are intended to be used for setups where you do not want the hash to change
when you update the corresponding tool (e.g. RASR, RETURNN, etc).
The assumption is that you would use the latest version of the tool,
and the behavior would not change.

Thus, we define a fixed hash_overwrite here, which is supposed to never change anymore,
and reflect such global versions.

Currently, we get the binaries via the Sisyphus global settings,
but we might extend that mechanism.

Also see i6_experiments/common/baselines/librispeech/default_tools.py.
"""

from sisyphus import tk, gs


def get_rasr_binary_path() -> tk.Path:
    """
    RASR binary path

    RASR_ROOT example (set via gs): "/work/tools/asr/rasr/20220603_github_default/"
    RASR binary path example: '{RASR_ROOT}/arch/{RASR_ARCH}'
    """
    assert getattr(gs, "RASR_ROOT", None), "RASR_ROOT not set"
    rasr_root = getattr(gs, "RASR_ROOT")
    rasr_arch = get_rasr_arch()
    rasr_binary_path = tk.Path(f"{rasr_root}/arch/{rasr_arch}")
    rasr_binary_path.hash_overwrite = "DEFAULT_RASR_BINARY_PATH"
    return rasr_binary_path


def get_rasr_arch() -> str:
    """RASR arch"""
    return getattr(gs, "RASR_ARCH", None) or "linux-x86_64-standard"


def get_sctk_binary_path() -> tk.Path:
    """SCTK binary path"""
    # If it is common to have sclite in the PATH env, we could also check for that here...
    assert getattr(gs, "SCTK_PATH", None), "SCTK_PATH not set"
    sctk_binary_path = tk.Path(getattr(gs, "SCTK_PATH"))
    sctk_binary_path.hash_overwrite = "DEFAULT_SCTK_BINARY_PATH"
    return sctk_binary_path


def get_returnn_python_exe() -> tk.Path:
    """
    RETURNN Python executable
    """
    assert getattr(gs, "RETURNN_PYTHON_EXE", None), "RETURNN_PYTHON_EXE not set"
    returnn_python_exe = tk.Path(getattr(gs, "RETURNN_PYTHON_EXE"))
    returnn_python_exe.hash_overwrite = "DEFAULT_RETURNN_PYTHON_EXE"
    return returnn_python_exe


def get_returnn_root() -> tk.Path:
    """
    RETURNN root
    """
    assert getattr(gs, "RETURNN_ROOT", None), "RETURNN_ROOT not set"
    returnn_root = tk.Path(getattr(gs, "RETURNN_ROOT"))
    returnn_root.hash_overwrite = "DEFAULT_RETURNN_ROOT"
    return returnn_root
