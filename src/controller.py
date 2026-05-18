"""
src/controller.py  —  Xbox Controller Input Handler
========================================================
Handles all joystick/gamepad input for the game.

Controls:
- Left Stick: Movement (with deadzone)
- Right Stick: Menu/Dialogue navigation (vertical only)
- RT (Right Trigger): Dash
- A Button: Select/Confirm/Interact
- B Button: Cancel/Back
- X Button: Inventory
- Y Button: Skill Tree
- Start: Pause
- Back/View: Map
- RB: Light Attack (Aiden) / Hack (Lena)
- LB: Heavy Attack (Aiden) / Block (Aiden)
"""

from __future__ import annotations

import pygame
from typing import Callable


# ══════════════════════════════════════════════════════════════
#  DEADZONE & SENSITIVITY
# ══════════════════════════════════════════════════════════════
STICK_DEADZONE = 0.15          # Ignore small stick movements
STICK_MENU_THRESHOLD = 0.5     # Threshold for menu navigation
TRIGGER_THRESHOLD = 0.3        # RT pressed threshold
MENU_REPEAT_DELAY = 0.25       # Seconds between menu movements (stick)


# ══════════════════════════════════════════════════════════════
#  XBOX BUTTON MAPPINGS (pygame joystick constants)
# ══════════════════════════════════════════════════════════════
# Xbox controller button indices:
XBOX_A = 0
XBOX_B = 1
XBOX_X = 2
XBOX_Y = 3
XBOX_LB = 4
XBOX_RB = 5
XBOX_BACK = 6        # View button (two lines)
XBOX_START = 7       # Menu button (three lines / hamburger)
XBOX_LS_PRESS = 9      # Left stick press (L3)
XBOX_RS_PRESS = 10     # Right stick press (R3)

# D-pad is typically hat 0 in pygame
XBOX_DPAD_HAT = 0

# Axis indices:
XBOX_AXIS_LS_X = 0   # Left stick X
XBOX_AXIS_LS_Y = 1   # Left stick Y (inverted in pygame)
XBOX_AXIS_LT = 2     # Left trigger
XBOX_AXIS_RS_X = 3   # Right stick X
XBOX_AXIS_RS_Y = 4   # Right stick Y
XBOX_AXIS_RT = 5     # Right trigger


# ══════════════════════════════════════════════════════════════
#  CONTROLLER MANAGER
# ══════════════════════════════════════════════════════════════

class ControllerManager:
    """Manages Xbox controller input with deadzones and event handling.
    
    Provides:
    - Movement vector from left stick
    - Menu navigation from D-pad (with repeat delay)
    - Trigger states for dash
    - Button press detection
    - Hot-swapping support (detects controller connection/disconnection)
    """
    
    def __init__(self):
        self.joystick: pygame.joystick.JoystickType | None = None
        self.connected = False
        
        # Stick values (clamped to deadzone)
        self.left_stick_x = 0.0
        self.left_stick_y = 0.0
        self.right_stick_x = 0.0
        self.right_stick_y = 0.0
        
        # D-pad values
        self.dpad_x = 0    # -1 left, 0 neutral, 1 right
        self.dpad_y = 0    # 1 up, 0 neutral, -1 down
        self._prev_dpad_x = 0
        self._prev_dpad_y = 0
        
        # Trigger values (0.0 to 1.0)
        self.rt_value = 0.0
        self.lt_value = 0.0
        
        # Button states (current frame)
        self.buttons_pressed = set()
        self.buttons_held = set()
        self.buttons_released = set()
        
        # Menu navigation timing
        self._menu_timer = 0.0
        self._menu_repeat_timer = 0.0
        self._dpad_first_move = True
        
        # Dash trigger (RT) debounce
        self._rt_was_pressed = False
        self.dash_triggered = False
        
        # Hot-swap detection
        self._last_joystick_count = 0
        self._reconnect_timer = 0.0
        
        self.last_input_method = "keyboard"
        self._init_joystick()
    
    def _init_joystick(self):
        """Initialize the first available joystick."""
        pygame.joystick.init()
        self._last_joystick_count = pygame.joystick.get_count()
        if pygame.joystick.get_count() > 0:
            try:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                self.connected = True
                print(f"[Controller] Connected: {self.joystick.get_name()}")
            except Exception as e:
                print(f"[Controller] Failed to init joystick: {e}")
                self.connected = False
                self.joystick = None
        else:
            self.connected = False
            self.joystick = None
    
    def _try_reconnect(self):
        """Try to reconnect a controller if one was connected."""
        current_count = pygame.joystick.get_count()
        if current_count != self._last_joystick_count:
            self._last_joystick_count = current_count
            if current_count > 0 and not self.connected:
                print("[Controller] New controller detected, attempting connection...")
                self._init_joystick()
            elif current_count == 0 and self.connected:
                print("[Controller] Controller disconnected")
                self.connected = False
                self.joystick = None
    
    def update(self, dt: float):
        """Update controller state. Call once per frame."""
        # Check for hot-swapping (controller connect/disconnect)
        self._reconnect_timer += dt
        if self._reconnect_timer >= 1.0:  # Check every second
            self._reconnect_timer = 0.0
            self._try_reconnect()
        
        if not self.connected or not self.joystick:
            return
        
        # Update stick values with deadzone
        self.left_stick_x = self._apply_deadzone(
            self.joystick.get_axis(XBOX_AXIS_LS_X)
        )
        self.left_stick_y = self._apply_deadzone(
            self.joystick.get_axis(XBOX_AXIS_LS_Y)
        )
        self.right_stick_x = self._apply_deadzone(
            self.joystick.get_axis(XBOX_AXIS_RS_X)
        )
        self.right_stick_y = self._apply_deadzone(
            self.joystick.get_axis(XBOX_AXIS_RS_Y)
        )
        
        # Update D-pad (hat)
        if self.joystick.get_numhats() > 0:
            hat_x, hat_y = self.joystick.get_hat(XBOX_DPAD_HAT)
            self.dpad_x = hat_x  # -1 left, 0 neutral, 1 right
            self.dpad_y = hat_y  # Pygame hat_y is 1 up, -1 down
        
        # Update triggers (normalize from -1,1 to 0,1 range)
        raw_rt = self.joystick.get_axis(XBOX_AXIS_RT)
        raw_lt = self.joystick.get_axis(XBOX_AXIS_LT)
        self.rt_value = self._normalize_trigger(raw_rt)
        self.lt_value = self._normalize_trigger(raw_lt)
        
        # Dash detection (RT pressed)
        rt_pressed = self.rt_value > TRIGGER_THRESHOLD
        self.dash_triggered = rt_pressed and not self._rt_was_pressed
        self._rt_was_pressed = rt_pressed
        
        # Update button states
        self.buttons_pressed.clear()
        self.buttons_released.clear()
        
        for i in range(self.joystick.get_numbuttons()):
            if self.joystick.get_button(i):
                if i not in self.buttons_held:
                    self.buttons_pressed.add(i)
                self.buttons_held.add(i)
            else:
                if i in self.buttons_held:
                    self.buttons_released.add(i)
                self.buttons_held.discard(i)
        
        # Update menu navigation timer
        if self._menu_timer > 0:
            self._menu_timer -= dt

        # Dynamically switch input method to controller if there's any active input
        has_activity = (
            abs(self.left_stick_x) > 0.15 or
            abs(self.left_stick_y) > 0.15 or
            abs(self.right_stick_x) > 0.15 or
            abs(self.right_stick_y) > 0.15 or
            self.rt_value > 0.15 or
            self.lt_value > 0.15 or
            len(self.buttons_pressed) > 0 or
            self.dpad_x != 0 or
            self.dpad_y != 0
        )
        if has_activity:
            self.last_input_method = "controller"

    def _apply_deadzone(self, value: float) -> float:
        """Apply deadzone to stick value."""
        if abs(value) < STICK_DEADZONE:
            return 0.0
        # Rescale to full range
        sign = 1 if value > 0 else -1
        return sign * (abs(value) - STICK_DEADZONE) / (1 - STICK_DEADZONE)
    
    def _normalize_trigger(self, value: float) -> float:
        """Normalize trigger from pygame's -1,1 range to 0,1."""
        # Pygame reports triggers as -1 (rest) to 1 (pressed)
        return max(0.0, (value + 1) / 2)
    
    # ── Movement ───────────────────────────────────────────────
    
    def get_movement_vector(self) -> tuple[float, float]:
        """Get normalized movement vector from left stick.
        
        Returns (dx, dy) where values are in range [-1, 1].
        """
        return (self.left_stick_x, self.left_stick_y)
    
    def is_moving(self) -> bool:
        """Check if left stick is being moved."""
        return abs(self.left_stick_x) > 0.01 or abs(self.left_stick_y) > 0.01
    
    # ── Menu Navigation ──────────────────────────────────────
    
    def get_menu_direction(self) -> int:
        """Get menu navigation direction from D-pad (cruzeta).
        
        Returns: -1 (up), 1 (down), or 0 (neutral)
        Uses D-pad Y axis for vertical menu navigation with debounce.
        """
        if self._menu_timer > 0:
            return 0
        
        # Check D-pad Y: pygame hat_y is 1 for UP press, -1 for DOWN press
        if self.dpad_y > 0:  # Up pressed on D-pad
            self._menu_timer = MENU_REPEAT_DELAY
            return -1  # Move up in menu
        elif self.dpad_y < 0:  # Down pressed on D-pad
            self._menu_timer = MENU_REPEAT_DELAY
            return 1  # Move down in menu
        
        return 0
    
    def get_menu_direction_horizontal(self) -> int:
        """Get horizontal menu direction from D-pad.
        
        Returns -1 (left), 1 (right), or 0 (neutral) with debounce.
        """
        if self._menu_timer > 0:
            return 0

        if self.dpad_x < 0:  # Left pressed
            self._menu_timer = MENU_REPEAT_DELAY
            return -1
        elif self.dpad_x > 0:  # Right pressed
            self._menu_timer = MENU_REPEAT_DELAY
            return 1

        return 0

    def get_menu_direction_continuous(self) -> int:
        """Get immediate menu direction without timing (for holding)."""
        # dpad_y = 1 means UP pressed, dpad_y = -1 means DOWN pressed
        if self.dpad_y > 0:  # Up pressed
            return -1
        elif self.dpad_y < 0:  # Down pressed
            return 1
        return 0
    
    # ── Button Helpers ───────────────────────────────────────
    
    def is_button_pressed(self, button: int) -> bool:
        """Check if button was pressed this frame."""
        return button in self.buttons_pressed
    
    def is_button_held(self, button: int) -> bool:
        """Check if button is currently held."""
        return button in self.buttons_held
    
    def is_button_released(self, button: int) -> bool:
        """Check if button was released this frame."""
        return button in self.buttons_released
    
    # ── Game-specific Input Checks ───────────────────────────
    
    def is_dash_triggered(self) -> bool:
        """Check if dash (RT) was triggered this frame."""
        return self.dash_triggered
    
    def is_confirm_pressed(self) -> bool:
        """A button pressed (confirm/select/interact)."""
        return XBOX_A in self.buttons_pressed
    
    def is_cancel_pressed(self) -> bool:
        """B button pressed (cancel/back)."""
        return XBOX_B in self.buttons_pressed
    
    def is_inventory_pressed(self) -> bool:
        """X button pressed (inventory)."""
        return XBOX_X in self.buttons_pressed
    
    def is_skill_tree_pressed(self) -> bool:
        """Y button pressed (skill tree)."""
        return XBOX_Y in self.buttons_pressed
    
    def is_pause_pressed(self) -> bool:
        """Menu button (three lines / hamburger) pressed for pause."""
        return XBOX_START in self.buttons_pressed
    
    def is_menu_button_pressed(self) -> bool:
        """Menu button (three lines / hamburger) - alias for is_pause_pressed."""
        return self.is_pause_pressed()
    
    def is_map_pressed(self) -> bool:
        """Back button pressed (map)."""
        return XBOX_BACK in self.buttons_pressed
    
    def is_attack_pressed(self) -> bool:
        """RB button pressed (light attack / hack)."""
        return XBOX_RB in self.buttons_pressed
    
    def is_block_pressed(self) -> bool:
        """LB button pressed (heavy attack / block)."""
        return XBOX_LB in self.buttons_pressed
    
    def is_interact_pressed(self) -> bool:
        """A button pressed (interact - same as confirm)."""
        return self.is_confirm_pressed()
    
    # ── Utility ──────────────────────────────────────────────
    
    def rumble(self, low_frequency: float = 0.5, high_frequency: float = 0.5, 
               duration_ms: int = 200):
        """Trigger controller rumble if supported."""
        if self.connected and self.joystick and hasattr(self.joystick, 'rumble'):
            try:
                self.joystick.rumble(low_frequency, high_frequency, duration_ms)
            except Exception:
                pass  # Rumble not supported
    
    def stop_rumble(self):
        """Stop any active rumble."""
        if self.connected and self.joystick and hasattr(self.joystick, 'stop_rumble'):
            try:
                self.joystick.stop_rumble()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════
#  GLOBAL CONTROLLER INSTANCE
# ══════════════════════════════════════════════════════════════

_controller_instance: ControllerManager | None = None


def get_controller() -> ControllerManager:
    """Get the singleton controller instance."""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = ControllerManager()
    return _controller_instance


def init_controller():
    """Initialize the global controller instance."""
    global _controller_instance
    _controller_instance = ControllerManager()


def update_controller(dt: float):
    """Update the global controller instance."""
    controller = get_controller()
    controller.update(dt)


# Legacy keyboard compatibility: combine controller + keyboard input
def get_combined_movement(keys) -> tuple[float, float]:
    """Get movement from both controller and keyboard.
    
    Args:
        keys: pygame.key.get_pressed() result
        
    Returns:
        (dx, dy) movement vector
    """
    from settings import KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT
    
    controller = get_controller()
    cx, cy = controller.get_movement_vector()
    
    # Add keyboard input
    kx, ky = 0.0, 0.0
    if keys[KEY_LEFT]:
        kx -= 1.0
    if keys[KEY_RIGHT]:
        kx += 1.0
    if keys[KEY_UP]:
        ky -= 1.0
    if keys[KEY_DOWN]:
        ky += 1.0
    
    # Normalize keyboard diagonal
    if kx != 0 and ky != 0:
        kx *= 0.7071
        ky *= 0.7071
    
    # Combine - use max magnitude
    dx = max(-1.0, min(1.0, cx + kx)) if (cx != 0 or kx != 0) else 0.0
    dy = max(-1.0, min(1.0, cy + ky)) if (cy != 0 or ky != 0) else 0.0
    
    # Re-normalize if combined exceeds 1.0
    magnitude = (dx * dx + dy * dy) ** 0.5
    if magnitude > 1.0:
        dx /= magnitude
        dy /= magnitude
    
    return (dx, dy)
