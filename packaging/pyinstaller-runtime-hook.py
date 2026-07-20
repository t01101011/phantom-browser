"""Configure bundled Camoufox assets before Phantom imports its engine modules."""
import os
from pathlib import Path

bundle = Path(os.environ.get("PHANTOM_BUNDLE_ROOT", Path(__file__).resolve().parent))
camoufox_dir = Path(os.environ.get("PHANTOM_CAMOUFOX_DIR", bundle / "camoufox"))
os.environ.setdefault("PHANTOM_CAMOUFOX_DIR", str(camoufox_dir))

# Camoufox currently resolves its browser cache at import time. Point that
# constant at release-owned assets without changing LOCALAPPDATA or user data.
try:
    import camoufox.pkgman as pkgman
    pkgman.INSTALL_DIR = camoufox_dir
    import camoufox.addons as addons
    addons.ADDONS_DIR = camoufox_dir / "addons"
except Exception:
    # Let the normal import produce the actionable error; never print paths or
    # environment values from this early hook (they can contain user data).
    pass
