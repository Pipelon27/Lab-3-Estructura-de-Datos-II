import os
from PIL import Image
import numpy as np

base_dir = "."
protags = [
    r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png",
    r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Lena Parker.png",
]
npc_paths = []
# Find a few npc images to test
for root, dirs, files in os.walk(r"assets\Characters BEHIND THE SMILE"):
    for file in files:
        if file.endswith(".png") and not any(p in file for p in ["Aiden", "Lena", "director", "el gastroo"]):
            npc_paths.append(os.path.join(root, file))
            if len(npc_paths) >= 3:
                break
    if len(npc_paths) >= 3:
        break

frame_w, frame_h = 32, 64

def check_knockout_zone(path):
    if not os.path.exists(path):
        print(f"Path does not exist: {path}")
        return
    img = Image.open(path)
    arr = np.array(img)
    alpha = arr[:, :, 3]
    
    # We want to check where the knocked out/dead frame is. Let's scan all rows (0-19) for columns 14-23.
    found_ko = []
    for r in range(20):
        y_start = r * frame_h
        ko_count = 0
        for c in range(14, min(img.width // frame_w, 24)):
            chunk = alpha[y_start:y_start+frame_h, c*frame_w:(c+1)*frame_w]
            if np.any(chunk > 0):
                rows_with = np.where(np.any(chunk > 0, axis=1))[0]
                h = rows_with[-1] - rows_with[0] + 1
                if h < 25: # Very short height, indicating lying down
                    ko_count += 1
        if ko_count >= 2:
            found_ko.append((r, ko_count))
            
    print(f"File {os.path.basename(path)}: found KO candidates at rows {found_ko}")

print("Checking Protagonists:")
for p in protags:
    check_knockout_zone(p)

print("\nChecking NPCs:")
for p in npc_paths:
    check_knockout_zone(p)
