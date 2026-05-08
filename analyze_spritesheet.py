"""
Analyze the Aiden Parker spritesheet to detect individual sprite frames.
Scans for non-transparent regions to identify the grid layout.
"""
from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)  # shape: (height, width, 4) RGBA
print(f"Image size: {img.size} (WxH)")
print(f"Array shape: {arr.shape}")

alpha = arr[:, :, 3]  # alpha channel

# Find non-transparent rows
row_has_content = np.any(alpha > 0, axis=1)
# Find non-transparent cols
col_has_content = np.any(alpha > 0, axis=0)

# Detect row groups (sprite rows)
print("\n=== Row groups with content ===")
in_group = False
row_groups = []
start = 0
for y in range(alpha.shape[0]):
    if row_has_content[y] and not in_group:
        start = y
        in_group = True
    elif not row_has_content[y] and in_group:
        row_groups.append((start, y - 1))
        in_group = False
if in_group:
    row_groups.append((start, alpha.shape[0] - 1))

for i, (y1, y2) in enumerate(row_groups):
    height = y2 - y1 + 1
    print(f"  Row {i}: y={y1}-{y2}  height={height}px")

# For each row group, detect column groups (individual sprites)
print("\n=== Sprite frames per row ===")
for i, (y1, y2) in enumerate(row_groups):
    row_alpha = alpha[y1:y2+1, :]
    col_has = np.any(row_alpha > 0, axis=0)
    
    in_group = False
    sprites = []
    for x in range(len(col_has)):
        if col_has[x] and not in_group:
            sx = x
            in_group = True
        elif not col_has[x] and in_group:
            sprites.append((sx, x - 1))
            in_group = False
    if in_group:
        sprites.append((sx, len(col_has) - 1))
    
    # Try to detect uniform frame width
    widths = [x2 - x1 + 1 for x1, x2 in sprites]
    
    print(f"\n  Row {i} (y={y1}-{y2}, h={y2-y1+1}): {len(sprites)} sprites")
    if sprites:
        # Show first few and last few
        for j, (x1, x2) in enumerate(sprites[:5]):
            print(f"    Frame {j}: x={x1}-{x2}, w={x2-x1+1}")
        if len(sprites) > 10:
            print(f"    ... ({len(sprites) - 10} more) ...")
            for j, (x1, x2) in enumerate(sprites[-5:]):
                print(f"    Frame {len(sprites)-5+j}: x={x1}-{x2}, w={x2-x1+1}")
        elif len(sprites) > 5:
            for j, (x1, x2) in enumerate(sprites[5:]):
                print(f"    Frame {5+j}: x={x1}-{x2}, w={x2-x1+1}")
        
        # Analyze common widths
        from collections import Counter
        wc = Counter(widths)
        print(f"    Width distribution: {dict(wc)}")

# Also try fixed grid detection
print("\n=== Fixed grid detection ===")
# Check if 32x32 or other common sizes work
for frame_size in [16, 24, 32, 48, 64]:
    cols = img.width // frame_size
    rows = img.height // frame_size
    # Check how many non-empty frames there are
    non_empty = 0
    for gy in range(rows):
        for gx in range(cols):
            region = alpha[gy*frame_size:(gy+1)*frame_size, gx*frame_size:(gx+1)*frame_size]
            if np.any(region > 0):
                non_empty += 1
    print(f"  {frame_size}x{frame_size} grid: {cols}x{rows} = {cols*rows} cells, {non_empty} non-empty")
