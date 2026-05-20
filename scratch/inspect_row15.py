import os
from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64
row = 15
y_start = row * frame_h

# Let's save each frame of Row 15 as an individual image in a debug folder to see them or print their pixel signatures
os.makedirs("scratch/row15_frames", exist_ok=True)
for col in range(img.width // frame_w):
    frame = img.crop((col * frame_w, y_start, (col + 1) * frame_w, y_start + frame_h))
    # Check if frame is non-empty
    arr = np.array(frame)
    alpha = arr[:, :, 3]
    if np.any(alpha > 0):
        frame.save(f"scratch/row15_frames/frame_{col}.png")

print("Saved non-empty frames of Row 15 to scratch/row15_frames/")
