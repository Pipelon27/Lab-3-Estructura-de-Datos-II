from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

frame_w = 32
frame_h = 64

# Let's print the bounding box of Row 7, cols 0-11 to see how they differ from Idle
print("Row 7 Cols 0-11 bounding boxes:")
for c in range(12):
    y_start = 7 * frame_h
    chunk = alpha[y_start:y_start+frame_h, c*frame_w:(c+1)*frame_w]
    if np.any(chunk > 0):
        rows_with = np.where(np.any(chunk > 0, axis=1))[0]
        cols_with = np.where(np.any(chunk > 0, axis=0))[0]
        r_min, r_max = rows_with[0], rows_with[-1]
        c_min, c_max = cols_with[0], cols_with[-1]
        print(f"  Col {c:2d}: size={c_max-c_min+1}x{r_max-r_min+1}, y={r_min}-{r_max}, x={c_min}-{c_max}")
