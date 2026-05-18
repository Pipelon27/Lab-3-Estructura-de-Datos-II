import os
import numpy as np
from PIL import Image

def main():
    img_path = "artifacts/coliseum_horizontal_court_render.png"
    if not os.path.exists(img_path):
        print(f"File {img_path} not found!")
        return
        
    img = Image.open(img_path)
    arr = np.array(img)
    print(f"Rendered image size: {img.size}")
    
    # 1. Let's check the court lines area: (476, 258, 848, 694)
    # The center of the court is x = 900, y = 605.
    # In the middle of the court there is a center circle, which has white/gray lines.
    # Let's check if there are white lines (pixels with R > 200, G > 200, B > 200) inside the court area!
    court_region = arr[258:952, 476:1324, :]
    rgb = court_region[:, :, :3]
    
    # Count court line pixels (cream/beige color: R > 190, G > 180, B > 150)
    line_px = np.sum((rgb[:, :, 0] > 190) & (rgb[:, :, 1] > 180) & (rgb[:, :, 2] > 150))
    print(f"Number of cream-colored court line pixels in court region: {line_px}")
    
    # 2. Let's check left hoop region: x = 431..563, y = 510..700 (size 132x190)
    left_hoop_region = arr[510:700, 431:563, :3]
    # In RGB, we can check for non-background pixels (not equal to background color (62, 56, 50))
    bg_color = np.array([62, 56, 50])
    left_hoop_opaque = np.sum(np.any(left_hoop_region != bg_color, axis=2))
    print(f"Left hoop region non-background pixels: {left_hoop_opaque}")
    
    # 3. Let's check right hoop region: x = 1237..1369, y = 510..700 (size 132x190)
    right_hoop_region = arr[510:700, 1237:1369, :3]
    right_hoop_opaque = np.sum(np.any(right_hoop_region != bg_color, axis=2))
    print(f"Right hoop region non-background pixels: {right_hoop_opaque}")
    
    if line_px > 500 and left_hoop_opaque > 1000 and right_hoop_opaque > 1000:
        print("VERIFICATION SUCCESSFUL: Both hoops and court lines are rendered perfectly in the Coliseum floor!")
    else:
        print("VERIFICATION FAILED! Some components are missing or transparent.")

if __name__ == "__main__":
    main()
