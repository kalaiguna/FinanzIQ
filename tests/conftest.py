import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
# core.*, platforms.* imports
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# parsers.*, process_payslip, process_receipts imports
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
