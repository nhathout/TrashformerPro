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

"""output:
Total images found: 36777

Images by folder:
battery: 2268
biological: 2097
cardboard: 4233
clothes: 5676
glass: 5208
metal: 2790
paper: 4008
plastic: 4791
shoes: 4347
trash: 1359
"""