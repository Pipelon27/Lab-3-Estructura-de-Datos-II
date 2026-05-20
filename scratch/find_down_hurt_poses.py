from PIL import Image
import numpy as np

img = Image.open(r"assets\Characters BEHIND THE SMILE\PROTAGONISTS\Aiden Parker.png")
arr = np.array(img)
alpha = arr[:, :, 3]

frame_w = 32
frame_h = 64

print("Analyzing rows for special poses...")
for row in range(20):
    y_start = row * frame_h
    frames_info = []
    for col in range(img.width // frame_w):
        chunk = alpha[y_start:y_start+frame_h, col*frame_w:(col+1)*frame_w]
        if np.any(chunk > 0):
            rows_with = np.where(np.any(chunk > 0, axis=1))[0]
            cols_with = np.where(np.any(chunk > 0, axis=0))[0]
            r_min, r_max = rows_with[0], rows_with[-1]
            c_min, c_max = cols_with[0], cols_with[-1]
            w = c_max - c_min + 1
            h = r_max - r_min + 1
            frames_info.append((col, w, h, r_min, r_max))
            
    if not frames_info:
        continue
        
    avg_w = sum(x[1] for x in frames_info) / len(frames_info)
    avg_h = sum(x[2] for x in frames_info) / len(frames_info)
    avg_y_min = sum(x[3] for x in frames_info) / len(frames_info)
    avg_y_max = sum(x[4] for x in frames_info) / len(frames_info)
    
    print(f"Row {row:2d}: {len(frames_info):2d} frames | Avg size={avg_w:.1f}x{avg_h:.1f} | Avg y_range={avg_y_min:.1f}-{avg_y_max:.1f}")
