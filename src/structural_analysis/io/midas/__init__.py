"""Public MIDAS adapter exports with canonical load normalization."""

from structural_analysis.io.midas import loader as _raw_loader
from structural_analysis.io.midas.canonical import load_midas_mgt

# Compatibility: existing callers importing ``io.midas.loader.load_midas_mgt``
# receive the normalized public adapter after package initialization. Raw parser
# helpers remain available inside ``loader`` for focused adapter development.
_raw_loader.load_midas_mgt = load_midas_mgt

__all__ = ["load_midas_mgt"]
