from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

frame_w = 32
frame_h = 64

print("Analyzing row frame heights to identify sitting pose:")
for row in range(20):
    y_start = row * frame_h
    heights = []
    widths = []
    y_min_list = []
    y_max_list = []
    for col in range(img.width // frame_w):
        chunk = alpha[y_start:y_start+frame_h, col*frame_w:(col+1)*frame_w]
        nonzero = np.argwhere(chunk > 0)
        if len(nonzero) > 0:
            ymin, xmin = nonzero.min(axis=0)
            ymax, xmax = nonzero.max(axis=0)
            h = ymax - ymin + 1
            w = xmax - xmin + 1
            heights.append(h)
            widths.append(w)
            y_min_list.append(ymin)
            y_max_list.append(ymax)
    if heights:
        avg_h = sum(heights) / len(heights)
        avg_w = sum(widths) / len(widths)
        avg_ymin = sum(y_min_list) / len(y_min_list)
        avg_ymax = sum(y_max_list) / len(y_max_list)
        print(f"Row {row:2d}: count={len(heights)}, avg_h={avg_h:.1f}, avg_w={avg_w:.1f}, avg_ymin={avg_ymin:.1f}, avg_ymax={avg_ymax:.1f}")
