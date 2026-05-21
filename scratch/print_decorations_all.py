import sys
import os

sys.path.append(os.path.abspath('.'))

import pygame
pygame.init()
pygame.display.set_mode((1, 1))

from src.map import SchoolMap

school_map = SchoolMap()
campus = school_map.get_floor(0)

print("--- All Decorations near bottom-left tree ---")
for i, item in enumerate(campus.garden_decorations):
    kind, x, y, name = item[:4]
    if 1800 < x < 1950 and 2700 < y < 2870:
        print(f"Index {i}: {item}")
