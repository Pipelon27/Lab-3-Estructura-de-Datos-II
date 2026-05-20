from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64
arr = np.array(img)
alpha = arr[:, :, 3]

print("Scanning for seated posture frames (height 32-42, ymax 58-63):")
candidates = []
for row in range(20):
    y_start = row * frame_h
    for col in range(img.width // frame_w):
        chunk = alpha[y_start:y_start+frame_h, col*frame_w:(col+1)*frame_w]
        nonzero = np.argwhere(chunk > 0)
        if len(nonzero) > 0:
            ymin, xmin = nonzero.min(axis=0)
            ymax, xmax = nonzero.max(axis=0)
            h = ymax - ymin + 1
            w = xmax - xmin + 1
            if 30 <= h <= 42 and 55 <= ymax <= 63:
                candidates.append((row, col, h, ymin, ymax))

# Group candidates by row
from collections import defaultdict
grouped = defaultdict(list)
for row, col, h, ymin, ymax in candidates:
    grouped[row].append(col)

for r, cols in sorted(grouped.items()):
    print(f"Row {r:2d}: matches in columns {cols}")
