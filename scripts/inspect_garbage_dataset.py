from pathlib import Path
from collections import Counter

root = Path("data/raw/garbage_v2")

image_exts = {".jpg", ".jpeg", ".png", ".webp"}

all_images = [p for p in root.rglob("*") if p.suffix.lower() in image_exts]
print(f"Total images found: {len(all_images)}")

# Count by parent folder name
counts = Counter(p.parent.name for p in all_images)

print("\nImages by folder:")
for cls, n in sorted(counts.items()):
    print(f"{cls}: {n}")