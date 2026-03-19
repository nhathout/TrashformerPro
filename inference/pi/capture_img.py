from pathlib import Path
from datetime import datetime
import subprocess

OUTDIR = Path("runtime/captures")
OUTDIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
outfile = OUTDIR / f"capture_{timestamp}.jpg"

cmd = [
    "rpicam-still",
    "--nopreview",
    "-o", str(outfile),
]

subprocess.run(cmd, check=True)
print(f"Saved image: {outfile}")