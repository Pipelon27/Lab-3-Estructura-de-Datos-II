from PIL import Image
import numpy as np
import os

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

frame_w = 32
frame_h = 64

print(f"Image size: {img.size}")

# Analyze each grid row (0 to 19)
for row in range(20):
    y_start = row * frame_h
    y_end = y_start + frame_h
    
    # We want to check for content in each frame (up to 56 columns)
    frames_bbox = []
    for col in range(56):
        x_start = col * frame_w
        x_end = x_start + frame_w
        chunk = alpha[y_start:y_end, x_start:x_end]
        if np.any(chunk > 0):
            # Find bounding box in local coords
            rows_with = np.where(np.any(chunk > 0, axis=1))[0]
            cols_with = np.where(np.any(chunk > 0, axis=0))[0]
            r_min, r_max = rows_with[0], rows_with[-1]
            c_min, c_max = cols_with[0], cols_with[-1]
            w = c_max - c_min + 1
            h = r_max - r_min + 1
            # Check vertical position (is it lying down? i.e. r_max is close to bottom, but r_min is also large/low down, or height is small)
            frames_bbox.append((col, w, h, r_min, r_max))
            
    if frames_bbox:
        print(f"Row {row}: {len(frames_bbox)} frames")
        # Print first few frames bounding boxes
        for col, w, h, r_min, r_max in frames_bbox[:8]:
            print(f"  Col {col:2d}: size={w}x{h}, y_range={r_min}-{r_max}")
        if len(frames_bbox) > 8:
            print(f"  ...")
