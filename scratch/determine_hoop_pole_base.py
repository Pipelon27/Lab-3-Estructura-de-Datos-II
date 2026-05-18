import numpy as np
from PIL import Image

def find_pole_base(crop_img, name):
    arr = np.array(crop_img)
    h, w, c = arr.shape
    print(f"--- Pole base analysis for {name} ({w}x{h}) ---")
    
    # The pole base is in the bottom section of the hoop sprite.
    # Let's inspect the bottom 30 rows of the sprite.
    bottom_section = arr[h-30:, :, :]
    
    # A pixel is part of the hoop/pole if it's not transparent (if there's an alpha channel)
    # or if it's not the background color (62, 56, 50).
    # Since the original asset Baloncesto.png has alpha/transparency, we can check for alpha > 0.
    # Let's check if the image has an alpha channel.
    if c == 4:
        alpha = arr[:, :, 3]
    else:
        # If no alpha, check if not equal to background (e.g. black or another color)
        # Let's see if there is alpha.
        alpha = np.ones((h, w)) * 255
        
    # Let's print the opacity grid of the bottom 25 rows
    for r in range(h-25, h):
        row_str = ""
        for col in range(w):
            val = arr[r, col]
            # If it's not transparent/background, mark as '#'
            if c == 4 and val[3] > 50:
                row_str += "#"
            elif c == 3 and not np.array_equal(val, [0, 0, 0]) and not np.array_equal(val, [62, 56, 50]):
                row_str += "#"
            else:
                row_str += "."
        # If the row has any '#' characters, print it
        if "#" in row_str:
            print(f"Row {r:03d}: {row_str}")

def main():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path)
    print(f"Original image size: {img.size}, mode: {img.mode}")
    
    # 1. Left Hoop Crop: cols = 4..91 (width 88), rows = 163..289 (height 127)
    left_hoop = img.crop((4, 163, 92, 290))
    find_pole_base(left_hoop, "Left Hoop")
    
    # 2. Right Hoop Crop: cols = 4..91 (width 88), rows = 3..129 (height 127)
    right_hoop = img.crop((4, 3, 92, 130))
    find_pole_base(right_hoop, "Right Hoop")

if __name__ == "__main__":
    main()
