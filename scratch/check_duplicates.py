from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)

frame_w = 32
frame_h = 64

def get_chunk(row, col):
    y = row * frame_h
    x = col * frame_w
    return arr[y:y+frame_h, x:x+frame_w]

print("Comparing pixel differences:")
for row_b in [13, 14, 16, 17]:
    diffs_to_idle = []
    diffs_to_walk = []
    for col in range(24):
        idle_c = get_chunk(1, col)
        walk_c = get_chunk(2, col)
        b_c = get_chunk(row_b, col)
        
        diff_idle = np.sum(np.abs(idle_c.astype(float) - b_c.astype(float)))
        diff_walk = np.sum(np.abs(walk_c.astype(float) - b_c.astype(float)))
        
        diffs_to_idle.append(diff_idle)
        diffs_to_walk.append(diff_walk)
        
    print(f"Row {row_b}:")
    print(f"  Avg absolute pixel diff to Row 1 (Idle): {np.mean(diffs_to_idle):.1f}")
    print(f"  Avg absolute pixel diff to Row 2 (Walk): {np.mean(diffs_to_walk):.1f}")
