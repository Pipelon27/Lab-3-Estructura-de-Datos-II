import numpy as np
from PIL import Image

def main():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path)
    arr = np.array(img)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    # Let's segment the image into connected components or simple grids to find where things are.
    # First, let's write a grid scanner that checks 32x32 blocks to see if they are occupied.
    grid_size = 32
    print(f"Scanning grid of size {grid_size}x{grid_size}:")
    for r in range(h // grid_size + 1):
        line = ""
        for c in range(w // grid_size + 1):
            block = alpha[r*grid_size:(r+1)*grid_size, c*grid_size:(c+1)*grid_size]
            if block.size > 0 and np.max(block) > 50:
                line += "#"
            else:
                line += " "
        print(f"Row {r:02d}: {line}")

if __name__ == "__main__":
    main()
