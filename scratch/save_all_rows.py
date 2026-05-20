from PIL import Image
import os

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64

os.makedirs("scratch/rows", exist_ok=True)

for r in range(20):
    y_start = r * frame_h
    strip = img.crop((0, y_start, img.width, y_start + frame_h))
    strip.save(f"scratch/rows/row_{r}.png")
    print(f"Saved scratch/rows/row_{r}.png")
