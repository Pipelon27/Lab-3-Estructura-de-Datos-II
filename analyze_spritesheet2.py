"""
Deeper analysis of Aiden Parker spritesheet.
Check if sprites are packed in a regular grid (e.g. 32x32, 48x48, 64x64).
Extract and display individual frames from the first rows.
"""
from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

# Let's look at the first row more carefully - y=18-63 is 46px tall, width 128
# That's 4 frames of 32x48? or 2 frames of 64x48? Let's check
print("=== Detailed first rows analysis ===")

# Row 0: y=18-63, w=128 -> looks like it could be 4 frames of 32px wide
# Let's check stride by looking at where each sprite starts/ends in first few rows
print("\n--- Row 0: y=18-63 (idle down?) ---")
row_alpha = alpha[18:64, 0:128]
for x_start in range(0, 128, 32):
    chunk = row_alpha[:, x_start:x_start+32]
    has_content = np.any(chunk > 0)
    if has_content:
        # Find bounding box
        rows_with = np.any(chunk > 0, axis=1)
        cols_with = np.any(chunk > 0, axis=0)
        r_min, r_max = np.where(rows_with)[0][[0, -1]]
        c_min, c_max = np.where(cols_with)[0][[0, -1]]
        print(f"  Chunk x={x_start}-{x_start+31}: content at ({c_min+x_start},{r_min+18})-({c_max+x_start},{r_max+18}), size={c_max-c_min+1}x{r_max-r_min+1}")

# Let's try with a 64x64 grid
print("\n--- Trying 64x64 grid on first chunk ---")
for gy in range(3):
    for gx in range(4):
        chunk = alpha[gy*64:(gy+1)*64, gx*64:(gx+1)*64]
        if np.any(chunk > 0):
            rows_with = np.any(chunk > 0, axis=1)
            cols_with = np.any(chunk > 0, axis=0)
            r_min, r_max = np.where(rows_with)[0][[0, -1]]
            c_min, c_max = np.where(cols_with)[0][[0, -1]]
            print(f"  Grid ({gx},{gy}): content at local ({c_min},{r_min})-({c_max},{r_max}), size={c_max-c_min+1}x{r_max-r_min+1}")

# The continuous row widths suggest the sprites are packed without separators
# Let's see if we can detect a standard frame width
# Row 1 (y=80-127): 768px wide, 48px tall
# 768 / 24 = 32 frames, 768 / 32 = 24 frames
# Row 3 (y=272-317): 384px wide, 46px tall
# 384 / 12 = 32 frames, 384 / 16 = 24

# Let's manually extract a narrow vertical slice to see if there's obvious sprite boundaries
print("\n=== Checking for vertical gaps in row 1 (y=80-127) ===")
row1_alpha = alpha[80:128, :]
col_sums = np.sum(row1_alpha > 0, axis=0)
# Find columns with zero alpha
zero_cols = np.where(col_sums == 0)[0]
if len(zero_cols) > 0:
    # Group consecutive zero columns
    gaps = []
    start = zero_cols[0]
    for i in range(1, len(zero_cols)):
        if zero_cols[i] != zero_cols[i-1] + 1:
            gaps.append((start, zero_cols[i-1]))
            start = zero_cols[i]
    gaps.append((start, zero_cols[-1]))
    print(f"  Found {len(gaps)} gaps (empty column ranges):")
    for g1, g2 in gaps[:30]:
        print(f"    x={g1}-{g2} (width={g2-g1+1})")
else:
    print("  No vertical gaps found - sprites are tightly packed")

# Let's also check for sprite boundaries by looking for repeating pattern widths
# Check stride by looking at content boundaries in row 1
print("\n=== Content boundaries in row 1 (y=80-127, 768px) ===")
row1_alpha = alpha[80:128, :768]
# For each column, check if it's the START of a new sprite (has content, previous column empty OR is column 0)
starts = []
for x in range(768):
    col = row1_alpha[:, x]
    has = np.any(col > 0)
    prev_has = np.any(row1_alpha[:, x-1] > 0) if x > 0 else False
    if has and not prev_has:
        starts.append(x)

print(f"  Sprite starts at columns: {starts}")
if len(starts) > 1:
    diffs = [starts[i+1] - starts[i] for i in range(len(starts)-1)]
    print(f"  Gaps between starts: {diffs}")

# Now check all rows for their "stride"
print("\n=== Stride analysis per row ===")
row_groups = []
in_group = False
row_has_content = np.any(alpha > 0, axis=1)
for y in range(alpha.shape[0]):
    if row_has_content[y] and not in_group:
        start = y
        in_group = True
    elif not row_has_content[y] and in_group:
        row_groups.append((start, y - 1))
        in_group = False
if in_group:
    row_groups.append((start, alpha.shape[0] - 1))

for i, (y1, y2) in enumerate(row_groups[:10]):
    row_alpha = alpha[y1:y2+1, :]
    col_sums = np.sum(row_alpha > 0, axis=0)
    
    # Find all gap positions
    zero_cols = np.where(col_sums == 0)[0]
    if len(zero_cols) > 0:
        gaps = []
        start = zero_cols[0]
        for j in range(1, len(zero_cols)):
            if zero_cols[j] != zero_cols[j-1] + 1:
                gaps.append((start, zero_cols[j-1]))
                start = zero_cols[j]
        gaps.append((start, zero_cols[-1]))
        
        # Get the sprite regions (between gaps)
        sprite_regions = []
        prev_end = 0
        for g1, g2 in gaps:
            if g1 > prev_end:
                sprite_regions.append((prev_end, g1 - 1))
            prev_end = g2 + 1
        # Add last region
        last_col = len(col_sums) - 1
        while last_col >= 0 and col_sums[last_col] == 0:
            last_col -= 1
        if prev_end <= last_col:
            sprite_regions.append((prev_end, last_col))
        
        widths = [x2 - x1 + 1 for x1, x2 in sprite_regions]
        print(f"  Row {i} (y={y1}-{y2}): {len(sprite_regions)} separated regions, widths={widths[:15]}")
    else:
        # Find width of content
        content_end = len(col_sums) - 1
        while content_end >= 0 and col_sums[content_end] == 0:
            content_end -= 1
        content_start = 0
        while content_start < len(col_sums) and col_sums[content_start] == 0:
            content_start += 1
        print(f"  Row {i} (y={y1}-{y2}): NO gaps, continuous content x={content_start}-{content_end} (w={content_end-content_start+1})")
