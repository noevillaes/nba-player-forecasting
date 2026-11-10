"""Los módulos de src/ se importan por nombre (python src/x.py corre desde la raíz del repo)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
