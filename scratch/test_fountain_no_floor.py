import os
import sys
import pygame

# Set up paths
sys.path.append(os.path.abspath("."))

pygame.init()
pygame.display.set_mode((800, 600), pygame.HIDDEN)

from src.map import SchoolMap
from src.camera import Camera

class ModifiedSchoolMap(SchoolMap):
    def __init__(self):
        super().__init__()
        # Skip drawing c_fountain floor
        # We can mock/monkeypatch the Floor.draw method to skip drawing c_fountain
        original_draw = self.floors[0].draw
        def new_draw(screen, camera, player=None, npcs=None, draw_furniture=True):
            # Temporarily save original rooms
            c_fountain = self.floors[0].rooms.get("c_fountain")
            if c_fountain:
                # We can temporarily remove it or set its color to transparent
                # For this test, let's temporarily remove it from rooms for the draw call
                del self.floors[0].rooms["c_fountain"]
            
            original_draw(screen, camera, player, npcs, draw_furniture)
            
            if c_fountain:
                self.floors[0].rooms["c_fountain"] = c_fountain
        
        self.floors[0].draw = new_draw

school_map = ModifiedSchoolMap()
camera = Camera(4000, 3000)
camera.offset = pygame.math.Vector2(2000 - 400, 2225 - 300)

screen = pygame.Surface((800, 600))
screen.fill((0, 0, 0))

# Draw floor 0 (Campus)
floor = school_map.floors[0]
floor.draw(screen, camera, draw_furniture=True)

# Save the rendering
os.makedirs("scratch", exist_ok=True)
pygame.image.save(screen, "scratch/fountain_no_floor.png")
print("Saved fountain no-floor render to scratch/fountain_no_floor.png")
