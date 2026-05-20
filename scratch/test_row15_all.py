import os
from PIL import Image
import numpy as np

base_dir = "."
protags = [
    r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png",
    r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Lena Parker.png",
]
npc_paths = []
for root, dirs, files in os.walk(r"assets\Characters BEHIND THE SMILE"):
    for file in files:
        if file.endswith(".png"):
            npc_paths.append(os.path.join(root, file))

frame_w, frame_h = 32, 64

print("Checking Row 15 existence in all spritesheets:")
for p in npc_paths:
    if not os.path.exists(p):
        continue
    img = Image.open(p)
    # Check if height is at least 16 * frame_h
    has_row15 = img.height >= 16 * frame_h
    print(f"File {os.path.basename(p):35s}: height={img.height}, has_row15={has_row15}")
