import numpy as np
from PIL import Image

def analyze_lines():
    img = Image.open("scratch/court_crop.png").convert("RGBA")
    arr = np.array(img)
    
    # Cream color line mask
    # R > 190, G > 180, B > 150
    mask = (arr[:, :, 0] > 190) & (arr[:, :, 1] > 180) & (arr[:, :, 2] > 150)
    
    # Let's find the left-most line pixel and right-most line pixel for the 3-point arcs
    # We can just sum the mask vertically to find the X profile
    x_profile = np.sum(mask, axis=0)
    
    # Print the x profile to see where lines are
    lines_x = np.where(x_profile > 10)[0]
    print(f"Court lines X coordinates (columns with >10 line pixels):")
    print(lines_x)
    
    # The court has a main rectangle. The 3-point arc extends outside or inside the paint?
    # Let's find the left-most edge of the court lines and the right-most edge.
    min_x = np.min(lines_x)
    max_x = np.max(lines_x)
    print(f"Court bounds X: {min_x} to {max_x} (Width: {max_x - min_x})")
    
    # To find the 3-point arc, we need to know its shape. Usually it's an arc that extends towards the center.
    # In a typical court, there is a baseline, a paint area, and a 3-point arc further out.
    # We can look at the horizontal center row (y=173) and see where the lines cross it.
    center_y = 173
    row_profile = mask[center_y, :]
    crossings = np.where(row_profile)[0]
    print(f"Line crossings at center Y ({center_y}): {crossings}")

if __name__ == "__main__":
    analyze_lines()
