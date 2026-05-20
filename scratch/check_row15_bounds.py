from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64

row = 15
y_start = row * frame_h

print("Row 15 frame vertical bounds:")
for col in range(24):
    chunk = img.crop((col * frame_w, y_start, (col + 1) * frame_w, y_start + frame_h))
    arr = np.array(chunk)
    alpha = arr[:, :, 3]
    nonzero = np.argwhere(alpha > 0)
    if len(nonzero) > 0:
        ymin, xmin = nonzero.min(axis=0)
        ymax, xmax = nonzero.max(axis=0)
        h = ymax - ymin + 1
        print(f"  Col {col:2d}: height={h}, y={ymin}-{ymax}")
    else:
        print(f"  Col {col:2d}: empty")
