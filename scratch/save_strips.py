from PIL import Image
import os

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
frame_w = 32
frame_h = 64

os.makedirs("scratch", exist_ok=True)

rows_to_save = [3, 7, 13, 14, 15, 16, 17, 18, 19]
for r in rows_to_save:
    y_start = r * frame_h
    # Find max columns
    max_cols = 24
    if r == 3: max_cols = 12
    if r == 15: max_cols = 24
    if r == 16: max_cols = 16
    
    strip = Image.new("RGBA", (frame_w * max_cols, frame_h))
    for c in range(max_cols):
        chunk = img.crop((c * frame_w, y_start, (c + 1) * frame_w, y_start + frame_h))
        strip.paste(chunk, (c * frame_w, 0))
    strip.save(f"scratch/row_{r}.png")
    print(f"Saved scratch/row_{r}.png")
