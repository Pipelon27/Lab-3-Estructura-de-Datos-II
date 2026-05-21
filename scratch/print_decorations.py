import sys
import os

# Add the workspace root to sys.path
sys.path.append(os.path.abspath('.'))

import pygame
pygame.init()
pygame.display.set_mode((1, 1))

from src.map import SchoolMap

school_map = SchoolMap()
campus = school_map.get_floor(0)

print("--- Garden Decorations ---")
for i, item in enumerate(campus.garden_decorations):
    # item is ('sprite', x, y, name, ...)
    if len(item) >= 4:
        kind, x, y, name = item[:4]
    else:
        kind, x, y, name = item[0], item[1], item[2], ""
    if "Flowers" in name or "flowers" in name.lower():
        # Print flowers near x=1800, y=2700-2850
        if 1700 < x < 1950 and 2500 < y < 2900:
            print(f"Index {i}: {item}")
