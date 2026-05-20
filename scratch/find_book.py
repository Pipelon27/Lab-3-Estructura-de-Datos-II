from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64
row = 9
y_start = row * frame_h

# Let's count how many non-transparent pixels differ between set A (col 0) and set B (col 24)
def pixel_diff(col_a, col_b):
    a = np.array(img.crop((col_a * frame_w, y_start, (col_a + 1) * frame_w, y_start + frame_h)))
    b = np.array(img.crop((col_b * frame_w, y_start, (col_b + 1) * frame_w, y_start + frame_h)))
    # Diff non-transparent pixels
    diff = np.sum(np.abs(a.astype(int) - b.astype(int)))
    return diff

print("Comparing corresponding frames of Set A (0-23) and Set B (24-47) in Row 9:")
for i in range(24):
    diff = pixel_diff(i, i + 24)
    print(f"  Frame {i:2d} vs {i+24:2d}: pixel diff sum = {diff}")
