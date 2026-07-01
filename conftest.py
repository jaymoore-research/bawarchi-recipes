import sys
import pathlib

# Make build_site.py (project root) importable from tests/.
sys.path.insert(0, str(pathlib.Path(__file__).parent))
