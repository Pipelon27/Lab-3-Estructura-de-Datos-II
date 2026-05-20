from PIL import Image
import os

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64
row = 9
y_start = row * frame_h

os.makedirs("scratch", exist_ok=True)

# Save Cols 0-23 (sitting set A)
strip_a = img.crop((0, y_start, 24 * frame_w, y_start + frame_h))
strip_a.save("scratch/row9_cols_0_23.png")

# Save Cols 24-47 (sitting set B)
strip_b = img.crop((24 * frame_w, y_start, 48 * frame_w, y_start + frame_h))
strip_b.save("scratch/row9_cols_24_47.png")

print("Saved Row 9 strips for visual inspection!")
