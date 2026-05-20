from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64
arr = np.array(img)
alpha = arr[:, :, 3]

grid = []
for r in range(20):
    row_heights = []
    y_start = r * frame_h
    for c in range(img.width // frame_w):
        chunk = alpha[y_start:y_start+frame_h, c*frame_w:(c+1)*frame_w]
        nonzero = np.argwhere(chunk > 0)
        if len(nonzero) > 0:
            ymin, xmin = nonzero.min(axis=0)
            ymax, xmax = nonzero.max(axis=0)
            h = ymax - ymin + 1
            row_heights.append(h)
        else:
            row_heights.append(0)
    grid.append(row_heights)

print("GRID HEIGHTS MAP:")
for r in range(20):
    line = " ".join(f"{h:2d}" if h > 0 else " ." for h in grid[r])
    print(f"Row {r:2d}: {line}")
