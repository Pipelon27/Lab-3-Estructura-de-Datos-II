from PIL import Image
import numpy as np

def find_rim():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path).convert("RGBA")
    arr = np.array(img)
    
    # Left Hoop (faces right): cols = 4..91 (width 88), rows = 163..289 (height 127)
    left_hoop = arr[163:290, 4:92]
    
    # Orange color roughly: R > 200, G ~ 100-150, B < 50
    # Let's find pixels where R is dominant and G is medium, B is low.
    mask = (left_hoop[:, :, 0] > 180) & (left_hoop[:, :, 1] < 150) & (left_hoop[:, :, 1] > 50) & (left_hoop[:, :, 2] < 100)
    
    y_coords, x_coords = np.where(mask)
    if len(x_coords) > 0:
        center_x = np.mean(x_coords)
        center_y = np.mean(y_coords)
        print(f"Native Left Hoop rim center (relative to 88x127 sprite): {center_x:.1f}, {center_y:.1f}")
        
        # Scale to 1.5x
        scaled_x = center_x * 1.5
        scaled_y = center_y * 1.5
        print(f"Scaled Left Hoop rim center (relative to 132x190 sprite): {scaled_x:.1f}, {scaled_y:.1f}")
        
        # Absolute world position
        # Left hoop is drawn at: x = 476 - 45 = 431, y = 258 + 252 = 510
        world_x = 431 + scaled_x
        world_y = 510 + scaled_y
        print(f"World Left Rim Center: {world_x:.1f}, {world_y:.1f}")
        
    # Right Hoop (faces left): cols = 4..91, rows = 3..129
    right_hoop = arr[3:130, 4:92]
    mask2 = (right_hoop[:, :, 0] > 180) & (right_hoop[:, :, 1] < 150) & (right_hoop[:, :, 1] > 50) & (right_hoop[:, :, 2] < 100)
    
    y2, x2 = np.where(mask2)
    if len(x2) > 0:
        c_x = np.mean(x2)
        c_y = np.mean(y2)
        print(f"Native Right Hoop rim center: {c_x:.1f}, {c_y:.1f}")
        
        sc_x = c_x * 1.5
        sc_y = c_y * 1.5
        
        # Right hoop is drawn at: x = 476 + 761 = 1237, y = 258 + 252 = 510
        w_x = 1237 + sc_x
        w_y = 510 + sc_y
        print(f"World Right Rim Center: {w_x:.1f}, {w_y:.1f}")

if __name__ == "__main__":
    find_rim()
