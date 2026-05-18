import numpy as np
from PIL import Image

def find_bounding_boxes():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path)
    arr = np.array(img)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    # Let's find connected components of non-transparent pixels
    # We can do a simple BFS/DFS or use scipy/cv2 if available, but since we are writing standard python,
    # let's do a simple labeling algorithm or box finder.
    # Since it's a standard sprite sheet, let's find the bounding box of the whole non-transparent areas.
    # Actually, let's scan column by column and row by row to find bounding boxes of separate sprites.
    # Let's find horizontal spans of transparency to separate columns, and vertical spans to separate rows!
    
    # Check which rows are completely transparent:
    row_non_empty = np.any(alpha > 10, axis=1)
    # Check which columns are completely transparent:
    col_non_empty = np.any(alpha > 10, axis=0)
    
    print("Non-empty row ranges:")
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
        
    print("Non-empty col ranges:")
    in_range = False
    start = 0
    for c in range(w):
        if col_non_empty[c] and not in_range:
            start = c
            in_range = True
        elif not col_non_empty[c] and in_range:
            print(f"  Cols {start} to {c-1}")
            in_range = False
    if in_range:
        print(f"  Cols {start} to {w-1}")

if __name__ == "__main__":
    find_bounding_boxes()
