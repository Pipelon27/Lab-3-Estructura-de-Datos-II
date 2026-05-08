"""
Final analysis: extract individual 32px-wide frames from the Aiden spritesheet.
Identify the walk/idle animations per direction.
Also save extracted frames for visual verification.
"""
from PIL import Image
import numpy as np
import os

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

# Row groups detected earlier
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

# Based on analysis, frames are 32px wide
# The row heights vary from 46 to 48px, suggesting a consistent cell height of ~64px
# Let's use 64px rows (standard RPG character height)

# Let's try an approach: use 32x64 grid with offset
# The first content starts at y=18, second row at y=80
# 80-18 = 62, very close to 64
# Adjusted: first row top = 0 (sprites y offset of ~18px within 64px cell)

print("=== 32px frame analysis ===")
print("Image: 1792x1280 = 56 columns x 20 rows at 32x64")

# Let's check if a 32x64 grid is correct
os.makedirs("debug_frames", exist_ok=True)

# Extract first 8 rows at 32x64 to see what we get
frame_w = 32
frame_h = 64

print("\n--- Extracting 32x64 frames ---")
for row in range(20):
    y = row * frame_h
    if y + frame_h > img.height:
        break
    non_empty = 0
    for col in range(56):
        x = col * frame_w
        if x + frame_w > img.width:
            break
        chunk = alpha[y:y+frame_h, x:x+frame_w]
        if np.any(chunk > 0):
            non_empty += 1
    if non_empty > 0:
        print(f"  Grid row {row} (y={y}-{y+frame_h-1}): {non_empty} non-empty frames")

# Save first few rows' frames for visual inspection
print("\n--- Saving debug frames ---")
for row in range(6):
    y = row * frame_h
    for col in range(24):
        x = col * frame_w
        chunk_arr = arr[y:y+frame_h, x:x+frame_w]
        if np.any(chunk_arr[:,:,3] > 0):
            frame_img = Image.fromarray(chunk_arr)
            frame_img.save(f"debug_frames/row{row}_col{col}.png")

print("Debug frames saved to debug_frames/")

# Now let's look at the first rows more carefully to identify animation types
# Row 0 (y=0-63): 4 non-empty at x=0,32,64,96 - idle down (4 frames)
# Row 1 (y=64-127): 768px = 24 frames at 32px - could be walk cycle
# Row 2 (y=128-191): extends to y=255, but in 64px grid it's rows 2-3
# Let's check the 128-255 area more carefully

print("\n=== Row 2 detailed (y=128-255, which is 2 grid rows) ===")
# This is a complex area - check both 64px sub-rows
for sub_row in range(2):
    y_start = 128 + sub_row * 64
    y_end = y_start + 64
    row_alpha = alpha[y_start:y_end, :]
    non_empty = 0
    frames_info = []
    for col in range(56):
        x = col * 32
        chunk = row_alpha[:, x:x+32]
        if np.any(chunk > 0):
            non_empty += 1
            frames_info.append(col)
    print(f"  Sub-row {sub_row} (y={y_start}-{y_end-1}): {non_empty} frames at cols {frames_info[:20]}")

# Let's check which rows correspond to directional movement
# Standard RPG pattern: down, left, right, up
# Row 0: 4 frames - idle (likely down-facing)
# Row 1: 24 frames - walk down? or all directions walk?

# Check if row 1 (y=64-127) could be 6 frames x 4 directions
print("\n=== Checking if rows contain multi-direction cycles ===")
# For Row 1 at 32x64
y = 64
row_alpha = alpha[y:y+64, :]
for group_start in range(0, 768, 192):  # Try 6 frames per direction
    group_alpha = row_alpha[:, group_start:group_start+192]
    has = np.any(group_alpha > 0)
    if has:
        cols_with = np.any(group_alpha > 0, axis=0)
        c_min, c_max = np.where(cols_with)[0][[0, -1]]
        print(f"  Group x={group_start}-{group_start+191}: content width={c_max-c_min+1}")

# Also check if perhaps the row cell height isn't 64 - maybe it's variable
# Let me check what happens with different y-offsets
print("\n=== Checking row y-positions with actual content ===")
for i, (y1, y2) in enumerate(row_groups):
    h = y2 - y1 + 1
    w_content = 0
    # Find total content width
    row_alpha = alpha[y1:y2+1, :]
    col_has = np.any(row_alpha > 0, axis=0)
    if np.any(col_has):
        cols = np.where(col_has)[0]
        w_content = cols[-1] + 1
    num_frames_32 = w_content // 32
    remainder = w_content % 32
    print(f"  Row {i:2d}: y={y1:4d}-{y2:4d} h={h:3d}  w_content={w_content:5d}  "
          f"@32px={num_frames_32:3d} frames (rem={remainder})")
