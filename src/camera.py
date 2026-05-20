"""
src/camera.py  —  Top-down camera with smooth player tracking
==============================================================
The camera computes an offset so that the followed target stays
near the centre of the viewport.  ``apply()`` / ``apply_rect()``
are used by every drawable to convert world coords → screen coords.
"""

import pygame
from settings import SCREEN_WIDTH, SCREEN_HEIGHT


class Camera:
    """Viewport camera that follows a target sprite.

    Attributes
    ----------
    offset : pygame.math.Vector2
        Current pixel offset applied to world coordinates.
    map_width, map_height : int
        Bounds of the current zone (the camera never scrolls past them).
    lerp_speed : float
        Smoothing factor (0–1).  Higher = snappier follow.
    """

    def __init__(self, map_width: int, map_height: int, lerp_speed: float = 0.1):
        self.offset     = pygame.math.Vector2(0, 0)
        self.map_width  = map_width
        self.map_height = map_height
        self.lerp_speed = lerp_speed
        self.zoom       = 1.0
        self.view_w     = SCREEN_WIDTH
        self.view_h     = SCREEN_HEIGHT
        self.shake_timer = 0.0
        self.shake_amount = 0.0

    def shake(self, duration: float, amount: float):
        """Trigger screenshake."""
        self.shake_timer = duration
        self.shake_amount = amount

    def set_zoom(self, zoom: float):
        self.zoom = zoom
        self.view_w = int(SCREEN_WIDTH / zoom)
        self.view_h = int(SCREEN_HEIGHT / zoom)

    # ── public API ────────────────────────────────────────────

    def set_bounds(self, map_width: int, map_height: int):
        """Update the world bounds (e.g. after a zone transition)."""
        self.map_width  = map_width
        self.map_height = map_height

    def update(self, target, dt: float = 0.016):
        """Move the camera towards *target* (must have a ``rect``).

        Uses linear interpolation for smooth following and clamps
        to map boundaries so the camera never shows out-of-bounds.
        """
        # Desired offset centres the target on screen (considering zoom)
        goal_x = target.rect.centerx - self.view_w // 2
        goal_y = target.rect.centery - self.view_h // 2

        # Lerp towards goal
        self.offset.x += (goal_x - self.offset.x) * self.lerp_speed
        self.offset.y += (goal_y - self.offset.y) * self.lerp_speed

        # Clamp so we never scroll past map edges
        self.offset.x = max(0, min(self.offset.x, self.map_width  - self.view_w))
        self.offset.y = max(0, min(self.offset.y, self.map_height - self.view_h))

        # Apply screenshake
        if self.shake_timer > 0:
            self.shake_timer -= dt
            import random
            self.offset.x += random.uniform(-self.shake_amount, self.shake_amount)
            self.offset.y += random.uniform(-self.shake_amount, self.shake_amount)

    def apply(self, entity) -> pygame.Rect:
        """Return a copy of *entity.rect* shifted by the camera offset.

        Use this when blitting sprites:
        ``screen.blit(sprite.image, camera.apply(sprite))``
        """
        return entity.rect.move(-int(self.offset.x), -int(self.offset.y))

    def apply_rect(self, rect: pygame.Rect) -> pygame.Rect:
        """Shift an arbitrary ``pygame.Rect`` by the camera offset."""
        return rect.move(-int(self.offset.x), -int(self.offset.y))

    def apply_pos(self, x: float, y: float) -> tuple[int, int]:
        """Convert world (x, y) → screen (x, y)."""
        return int(x - self.offset.x), int(y - self.offset.y)

    def screen_to_world(self, sx: int, sy: int) -> tuple[int, int]:
        """Convert screen coords → world coords (for mouse picking)."""
        return int(sx + self.offset.x), int(sy + self.offset.y)
