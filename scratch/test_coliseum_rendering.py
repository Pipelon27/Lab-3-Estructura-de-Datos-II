import os
import sys
import pygame

# Set up dummy video driver for headless environments
os.environ["SDL_VIDEODRIVER"] = "dummy"

# Add root and src/ to path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, "src"))

from settings import SCREEN_WIDTH, SCREEN_HEIGHT
from src.map import SchoolMap
from src.camera import Camera

def main():
    pygame.init()
    pygame.display.set_mode((1800, 1300))
    # Create a surface that matches the Coliseum bounds: 1800x1300
    screen = pygame.Surface((1800, 1300))
    
    # Initialize the map
    school_map = SchoolMap()
    coliseum_floor = school_map.get_floor(5) # ID 5 is Coliseum Interior
    
    if not coliseum_floor:
        print("Failed to load Coliseum interior floor!")
        return
        
    print(f"Coliseum interior floor loaded: {coliseum_floor.name} ({coliseum_floor.width}x{coliseum_floor.height})")
    
    # Create camera with no offset to render the whole map from (0,0) to (1800, 1300)
    camera = Camera(1800, 1300)
    camera.offset = pygame.math.Vector2(0, 0)
    
    # Draw floor
    coliseum_floor.draw(screen, camera)
    
    print("Tile cache after draw:", list(coliseum_floor._tile_cache.keys()))
    print("Has _court_surface:", hasattr(coliseum_floor, "_court_surface"))
    if hasattr(coliseum_floor, "_court_surface"):
        print("  _court_surface value:", coliseum_floor._court_surface)
    if "baloncesto" in coliseum_floor._tile_cache:
        print("  baloncesto in cache:", coliseum_floor._tile_cache["baloncesto"])
        
    # Save surface
    os.makedirs("artifacts", exist_ok=True)
    out_path = "artifacts/coliseum_horizontal_court_render.png"
    pygame.image.save(screen, out_path)
    print(f"Coliseum interior rendered successfully and saved to: {out_path}")

if __name__ == "__main__":
    main()
