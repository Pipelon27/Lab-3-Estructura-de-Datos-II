import numpy as np
from PIL import Image

def main():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path)
    arr = np.array(img)
    
    # Sub-region for hoops: cols 4..91, rows 0..361
    alpha_sub = arr[:, 4:92, 3]
    h, w = alpha_sub.shape
    
    row_non_empty = np.any(alpha_sub > 10, axis=1)
    
    print("Hoop vertical ranges:")
    in_range = False
    start = 0
    for r in range(h):
        if row_non_empty[r] and not in_range:
            start = r
            in_range = True
        elif not row_non_empty[r] and in_range:
            print(f"  Rows {start} to {r-1}")
            in_range = False
    if in_range:
        print(f"  Rows {start} to {h-1}")

if __name__ == "__main__":
    main()
