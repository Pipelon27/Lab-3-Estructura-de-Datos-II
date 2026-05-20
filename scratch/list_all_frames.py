from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

frame_w = 32
frame_h = 64

print(f"Aiden Parker Image size: {img.size}")
for row in range(20):
    y_start = row * frame_h
    cols = []
    for col in range(img.width // frame_w):
        chunk = alpha[y_start:y_start+frame_h, col*frame_w:(col+1)*frame_w]
        if np.any(chunk > 0):
            cols.append(col)
    if cols:
        print(f"Row {row:2d}: {len(cols):2d} frames at columns {cols}")
