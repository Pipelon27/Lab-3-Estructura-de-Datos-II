"""Rooftop Party System for Day 3 event.

Handles rendering and management of the fiesta in the rooftop terrace.
"""
import pygame
import os
from settings import SCREEN_WIDTH, SCREEN_HEIGHT, FLOOR_ROOFTOP


class RooftopParty:
    """Manages the Day 3 fiesta on the rooftop with DJ, lights, and dancers."""
    
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.is_active = False
        self.day_number = 1
        self.sprites = {}
        self.animation_timers = {}
        self.load_sprites()
    
    def load_sprites(self):
        """Load all party sprites from assets folder."""
        asset_dir = "assets"
        sprite_files = {
            "dj": "Beach_Concert_DJ_32x32.gif",
            "laser_machine_1": "Beach_Concert_Laser_Machine_32x32.gif",
            "laser_machine_2": "Beach_Concert_Laser_Machine_2_32x32.gif",
            "laser_light_1": "Beach_Concert_Laser_Machine_White_Light_32x32.gif",
            "laser_light_2": "Beach_Concert_Laser_Machine_White_Light_2_32x32.gif",
            "stage_laser": "Beach_Stage_Laser_Machine_32x32.gif",
            "singer_1": "Beach_Concert_Singer_32x32.gif",
            "singer_2": "Beach_Concert_Singer_2_32x32.gif",
            "singer_3": "Beach_Concert_Singer_3_32x32.gif",
            "spotlight_base": "Spotlight_1_32x32.gif",
            "spotlight_head": "Spotlight_1_Head_Only_32x32.gif",
            "spotlight_light": "Spotlight_1_Light_32x32.gif",
            "spotlight_light_head": "Spotlight_1_Head_Only_Light_32x32.gif",
        }
        
        for key, filename in sprite_files.items():
            filepath = os.path.join(asset_dir, filename)
            if os.path.exists(filepath):
                try:
                    self.sprites[key] = pygame.image.load(filepath).convert_alpha()
                    self.animation_timers[key] = 0.0
                except Exception as e:
                    print(f"[RooftopParty] Failed to load {key}: {e}")
    
    def update(self, dt: float, day_number: int):
        """Update party state and animations."""
        self.day_number = day_number
        self.is_active = (day_number >= 3)
        
        if self.is_active:
            # Update animation timers
            for key in self.animation_timers:
                self.animation_timers[key] += dt
    
    def draw_on_rooftop(self, surface: pygame.Surface, camera, current_floor: int):
        """Draw party elements on the rooftop terrace if active."""
        if not self.is_active or current_floor != FLOOR_ROOFTOP:
            return
        
        # 1. Main DJ Setup - Centered horizontally at the north of the terrace, safely inside (y >= 500)
        # DJ is 32x32. Top-left is x = 1784, y = 560 (spans 1784..1816, y: 560..592)
        dj_x, dj_y = 1784, 560
        self._draw_sprite_at_world_pos(surface, camera, "dj", dj_x, dj_y)
        
        # 2. Laser Machines - Flanking the DJ booth nicely and safely inside
        # Spread further apart for a wider stage feel, but perfectly balanced between DJ and tables
        left_laser_x, left_laser_y = 1530, 560
        right_laser_x, right_laser_y = 2038, 560
        self._draw_sprite_at_world_pos(surface, camera, "laser_machine_1", left_laser_x, left_laser_y)
        self._draw_sprite_at_world_pos(surface, camera, "laser_machine_2", right_laser_x, right_laser_y)
            
        # 3. Stage Laser - Placed neatly in front of the DJ
        self._draw_sprite_at_world_pos(surface, camera, "stage_laser", 1784, 610)
        
        # 4. Live Band (Singers) - Symmetrically placed in the gaps between DJ and laser machines
        singer_positions = [
            ("singer_1", 1684, 590),
            ("singer_2", 1884, 590),
        ]
        for singer_key, sx, sy in singer_positions:
            self._draw_sprite_at_world_pos(surface, camera, singer_key, sx, sy)
        
        # 5. Spotlights - Placed strictly in the 4 corners of the terrace
        # Bottom spotlights moved up (y=1560) to stay away from the walls
        spotlight_positions = [
            (1240, 550),   # Top-Left corner
            (2328, 550),   # Top-Right corner
            (1240, 1560),  # Bottom-Left corner
            (2328, 1560),  # Bottom-Right corner
        ]
        for spx, spy in spotlight_positions:
            self._draw_sprite_at_world_pos(surface, camera, "spotlight_base", spx, spy)
    
    def get_collisions(self) -> list[pygame.Rect]:
        """Return invisible collision boxes for all party sprites to block the player."""
        if not self.is_active:
            return []
        
        return [
            pygame.Rect(1784, 560, 32, 32),  # DJ
            pygame.Rect(1530, 560, 32, 32),  # Left Laser
            pygame.Rect(2038, 560, 32, 32),  # Right Laser
            pygame.Rect(1784, 610, 32, 32),  # Stage Laser
            pygame.Rect(1684, 590, 32, 32),  # Singer 1
            pygame.Rect(1884, 590, 32, 32),  # Singer 2
            pygame.Rect(1240, 550, 32, 32),  # Spotlight TL
            pygame.Rect(2328, 550, 32, 32),  # Spotlight TR
            pygame.Rect(1240, 1560, 32, 32), # Spotlight BL
            pygame.Rect(2328, 1560, 32, 32), # Spotlight BR
        ]

    def _draw_sprite_at_world_pos(self, surface: pygame.Surface, camera, sprite_key: str, world_x: int, world_y: int):
        """Draw a sprite at world coordinates, applying camera offset."""
        if sprite_key not in self.sprites:
            return
        
        sprite = self.sprites[sprite_key]
        
        # Apply camera transform
        screen_x = world_x - camera.offset.x
        screen_y = world_y - camera.offset.y
        
        # Pygame's blit handles off-screen clipping natively.
        # Manual clipping based on SCREEN_WIDTH caused sprites to disappear early when the camera zoomed out.
        surface.blit(sprite, (screen_x, screen_y))
    
    def is_party_active_on_floor(self, current_floor: int, day_number: int) -> bool:
        """Check if party is active on a given floor."""
        return day_number >= 3 and current_floor == FLOOR_ROOFTOP
