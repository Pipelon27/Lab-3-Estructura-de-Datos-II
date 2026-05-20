from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

frame_w = 32
frame_h = 64

def get_bbox(row, col):
    y = row * frame_h
    x = col * frame_w
    chunk = alpha[y:y+frame_h, x:x+frame_w]
    if not np.any(chunk > 0):
        return None
    rows_with = np.where(np.any(chunk > 0, axis=1))[0]
    cols_with = np.where(np.any(chunk > 0, axis=0))[0]
    return (cols_with[0], rows_with[0], cols_with[-1] - cols_with[0] + 1, rows_with[-1] - rows_with[0] + 1)

print("Comparing Row 13 and Row 14 with Row 1 (Idle):")
for col in [0, 6, 12, 18]: # first frame of Right, Up, Left, Down
    bbox_idle = get_bbox(1, col)
    bbox_r13 = get_bbox(13, col)
    bbox_r14 = get_bbox(14, col)
    print(f"Col {col:2d}:")
    print(f"  Idle: {bbox_idle}")
    print(f"  Row 13: {bbox_r13}")
    print(f"  Row 14: {bbox_r14}")
