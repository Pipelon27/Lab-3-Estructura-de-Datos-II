from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64
row = 9
y_start = row * frame_h

# Get unique colors in Set A (cols 0-23)
colors_a = set()
for col in range(24):
    chunk = img.crop((col * frame_w, y_start, (col + 1) * frame_w, y_start + frame_h))
    colors_a.update(map(tuple, np.array(chunk).reshape(-1, 4)))

# Get unique colors in Set B (cols 24-47)
colors_b = set()
for col in range(24, 48):
    chunk = img.crop((col * frame_w, y_start, (col + 1) * frame_w, y_start + frame_h))
    colors_b.update(map(tuple, np.array(chunk).reshape(-1, 4)))

# Filter out transparent pixels
colors_a = {c for c in colors_a if c[3] > 0}
colors_b = {c for c in colors_b if c[3] > 0}

only_a = colors_a - colors_b
only_b = colors_b - colors_a

print(f"Colors unique to Set A: {len(only_a)}")
print(f"Colors unique to Set B: {len(only_b)}")

# Print a few unique colors of B
print("Sample unique colors in Set B (first 10):", list(only_b)[:10])
print("Sample unique colors in Set A (first 10):", list(only_a)[:10])
