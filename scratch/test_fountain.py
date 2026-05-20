import os
import sys
import pygame

# Set up paths
sys.path.append(os.path.abspath("."))

pygame.init()
pygame.display.set_mode((800, 600), pygame.HIDDEN)

from src.map import SchoolMap
from src.camera import Camera

school_map = SchoolMap()
camera = Camera(4000, 3000)
camera.offset = pygame.math.Vector2(2000 - 400, 2225 - 300)

screen = pygame.Surface((800, 600))
screen.fill((0, 0, 0))

# Draw floor 0 (Campus)
floor = school_map.get_floor(0)
floor.draw(screen, camera, draw_furniture=True)

# Save the rendering
os.makedirs("scratch", exist_ok=True)
pygame.image.save(screen, "scratch/fountain.png")
print("Saved fountain render to scratch/fountain.png")
