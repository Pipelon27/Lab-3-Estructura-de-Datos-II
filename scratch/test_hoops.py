import pygame
import sys
import math

def check_hoops():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    from src.map import SchoolMap
    
    # Load assets
    school_map = SchoolMap()
    floor = school_map.get_floor(5) # Coliseum
    
    # Draw floor to surface
    surf = pygame.Surface((3000, 3000))
    
    # We need a dummy camera
    class DummyCam:
        def __init__(self):
            self.offset = pygame.math.Vector2(0, 0)
            self.zoom = 1.0
        def apply_rect(self, r):
            return r
        def apply_pos(self, x, y):
            return x, y
    
    cam = DummyCam()
    
    class DummyPlayer:
        rect = pygame.Rect(0,0,0,0)
    
    floor.draw(surf, cam, DummyPlayer(), [])
    floor.draw_foreground(surf, cam, DummyPlayer())
    floor.draw_roofs(surf, cam, DummyPlayer())
    floor.draw_top_layer(surf, cam)
    
    # Now court is rendered. Court is at 476, 258. Size 848x694
    # Center is 900, 605
    # Let's crop the court out to save it
    court_crop = surf.subsurface(pygame.Rect(400, 200, 1000, 800)).copy()
    
    # Let's draw dots where we think the rims are
    # Left rim was 541, 605
    # Right rim was 1259, 605
    
    left_rim = (541 - 400, 605 - 200)
    right_rim = (1259 - 400, 605 - 200)
    
    pygame.draw.circle(court_crop, (255, 0, 0), left_rim, 10)
    pygame.draw.circle(court_crop, (0, 255, 0), right_rim, 10)
    
    # Draw 3-point arcs
    three_point_radius = 209
    pygame.draw.circle(court_crop, (255, 0, 0), left_rim, three_point_radius, 2)
    pygame.draw.circle(court_crop, (0, 255, 0), right_rim, three_point_radius, 2)
    
    pygame.image.save(court_crop, "scratch/hoop_diagnostic.png")
    print("Saved scratch/hoop_diagnostic.png")
    pygame.quit()

if __name__ == "__main__":
    check_hoops()
