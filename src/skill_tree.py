"""
src/skill_tree.py  —  N-ary skill tree (custom data structure)
===============================================================
Each character owns a **SkillTree** built as an n-ary tree:

    Root ("Skills")
     ├── Branch 1  (e.g. Strength)
     │    ├── Leaf  (Heavy Punch)
     │    ├── Leaf  (Combo Master)
     │    └── Leaf  (Knockback)
     ├── Branch 2  …
     └── Branch 3  …

**No external library** is used — the tree is implemented from scratch
with ``SkillNode`` containing a list of children.
"""

from __future__ import annotations

import pygame
from settings import (
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, WHITE, NOTIF_SUCCESS, NOTIF_WARNING,
    SCREEN_WIDTH, SCREEN_HEIGHT,
    XP_PER_LEVEL, SKILL_POINT_PER_LEVEL, VT323_PATH)


# ══════════════════════════════════════════════════════════════
#  SKILL NODE  (n-ary tree node)
# ══════════════════════════════════════════════════════════════

class SkillNode:
    """A single node in the skill tree.

    Attributes
    ----------
    name        : str   human-readable name
    description : str   tooltip / help text
    cost        : int   skill points required to unlock
    unlocked    : bool  whether the player has purchased this skill
    parent      : SkillNode | None
    children    : list[SkillNode]
    effect      : dict  stat modifiers applied when unlocked
                        e.g. {"damage": 5, "speed": 1}
    """

    def __init__(self, name: str, description: str = "",
                 cost: int = 1, effect: dict | None = None):
        self.name        = name
        self.description = description
        self.cost        = cost
        self.unlocked    = False
        self.parent:  SkillNode | None = None
        self.children: list[SkillNode] = []
        self.effect:  dict             = effect or {}

    # ── tree operations ───────────────────────────────────────

    def add_child(self, child: SkillNode) -> SkillNode:
        """Attach *child* as a sub-skill.  Returns *child* for chaining."""
        child.parent = self
        self.children.append(child)
        return child

    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def is_root(self) -> bool:
        return self.parent is None

    def depth(self) -> int:
        """Depth from root (root = 0)."""
        d = 0
        n = self
        while n.parent is not None:
            d += 1
            n = n.parent
        return d

    def is_available(self) -> bool:
        """A skill is available if its parent is unlocked (or it is root)
        and it has not yet been unlocked itself."""
        if self.unlocked:
            return False
        if self.parent is None:
            return True               # root is always "available"
        return self.parent.unlocked

    # ── traversals ────────────────────────────────────────────

    def pre_order(self) -> list[SkillNode]:
        """Pre-order traversal (self, then children left→right)."""
        result = [self]
        for child in self.children:
            result.extend(child.pre_order())
        return result

    def level_order(self) -> list[SkillNode]:
        """BFS / level-order traversal."""
        from collections import deque
        result = []
        queue  = deque([self])
        while queue:
            node = queue.popleft()
            result.append(node)
            for child in node.children:
                queue.append(child)
        return result

    def __repr__(self):
        status = "✓" if self.unlocked else "✗"
        return f"SkillNode({self.name} [{status}])"


# ══════════════════════════════════════════════════════════════
#  SKILL TREE  (wraps the root node)
# ══════════════════════════════════════════════════════════════

class SkillTree:
    """An n-ary tree of skills with unlock / query / draw logic.

    Parameters
    ----------
    root : SkillNode
        The invisible root node whose children are the main branches.
    """

    def __init__(self, root: SkillNode):
        self.root      = root
        self.root.unlocked = True     # root is always unlocked
        self.selected_node = self.root.children[0] if self.root.children else self.root
        self._flat:  list[SkillNode] = []   # cache for drawing
        self._node_pos: dict[SkillNode, tuple[int, int]] = {}
        self._refresh_flat()

    def _refresh_flat(self):
        """Flatten tree into display order (pre-order, skip root)."""
        self._flat = self.root.pre_order()[1:]   # skip invisible root

    # ── queries ───────────────────────────────────────────────

    def get_all_skills(self) -> list[SkillNode]:
        return self._flat

    def get_unlocked(self) -> list[SkillNode]:
        return [s for s in self._flat if s.unlocked]

    def get_available(self) -> list[SkillNode]:
        return [s for s in self._flat if s.is_available()]

    def find_by_name(self, name: str) -> SkillNode | None:
        for s in self._flat:
            if s.name == name:
                return s
        return None

    # ── unlock ────────────────────────────────────────────────

    def unlock_skill(self, node: SkillNode, player) -> bool:
        """Try to unlock *node*.  Returns True on success.

        Checks:
        1. Parent must be unlocked (availability).
        2. Player must have enough skill points.
        """
        if not node.is_available():
            return False
        if player.money < node.cost:
            return False

        node.unlocked = True
        player.money -= node.cost

        # Apply stat effects
        for stat, value in node.effect.items():
            current = getattr(player, stat, None)
            if current is not None:
                setattr(player, stat, current + value)

        self._refresh_flat()
        return True

    # ── input handling (when SKILL_TREE_SCREEN is active) ─────

    def handle_input(self, event: pygame.event.Event, player):
        """Navigate and unlock skills in the tree screen."""
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_UP:
            if self.selected_node.parent and not self.selected_node.parent.is_root():
                self.selected_node = self.selected_node.parent
        elif event.key == pygame.K_DOWN:
            if self.selected_node.children:
                self.selected_node = self.selected_node.children[0]
        elif event.key == pygame.K_LEFT:
            if self.selected_node.parent:
                sibs = self.selected_node.parent.children
                idx = sibs.index(self.selected_node)
                if idx > 0:
                    self.selected_node = sibs[idx - 1]
        elif event.key == pygame.K_RIGHT:
            if self.selected_node.parent:
                sibs = self.selected_node.parent.children
                idx = sibs.index(self.selected_node)
                if idx < len(sibs) - 1:
                    self.selected_node = sibs[idx + 1]
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            return self.unlock_skill(self.selected_node, player)
        return None

    def handle_controller(self, controller, player):
        """Navigate and unlock skills using a controller."""
        # Navigation
        menu_h = controller.get_menu_direction_horizontal()
        menu_v = controller.get_menu_direction()

        if menu_v < 0:  # Up
            if self.selected_node.parent and not self.selected_node.parent.is_root():
                self.selected_node = self.selected_node.parent
        elif menu_v > 0:  # Down
            if self.selected_node.children:
                self.selected_node = self.selected_node.children[0]
        elif menu_h < 0:  # Left
            if self.selected_node.parent:
                sibs = self.selected_node.parent.children
                idx = sibs.index(self.selected_node)
                if idx > 0:
                    self.selected_node = sibs[idx - 1]
        elif menu_h > 0:  # Right
            if self.selected_node.parent:
                sibs = self.selected_node.parent.children
                idx = sibs.index(self.selected_node)
                if idx < len(sibs) - 1:
                    self.selected_node = sibs[idx + 1]

        # Confirm purchase (A button)
        if controller.is_confirm_pressed():
            return self.unlock_skill(self.selected_node, player)
        return None

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, player):
        """Render the full skill-tree screen as a graphical tree."""
        screen.fill(UI_BG)

        font_title = pygame.font.Font(VT323_PATH, 32)
        font_node  = pygame.font.Font(VT323_PATH, 18)
        font_desc  = pygame.font.Font(VT323_PATH, 16)
        font_info  = pygame.font.Font(VT323_PATH, 18)

        # Header
        screen.blit(
            font_title.render(f"Skill Tree  —  Money: ${player.money}", True, UI_ACCENT),
            (30, 20),
        )

        # Calculate layout
        self._node_pos = {}
        self._calculate_layout(self.root, 0, SCREEN_WIDTH, 100, 150)

        # Draw edges (connections) first
        for node in self.root.level_order():
            if node.is_root(): continue
            px, py = self._node_pos[node.parent]
            nx, ny = self._node_pos[node]
            
            # Draw line from parent to child
            color = NOTIF_SUCCESS if node.unlocked else UI_BORDER
            pygame.draw.line(screen, color, (px, py), (nx, ny), 3)

        # Draw nodes
        for node in self.root.level_order():
            if node.is_root(): continue
            nx, ny = self._node_pos[node]
            is_sel = (node == self.selected_node)
            avail  = node.is_available() and not node.unlocked

            # Node color
            if node.unlocked:
                color = NOTIF_SUCCESS
            elif avail:
                color = UI_ACCENT
            else:
                color = UI_TEXT_DIM

            # Selection highlight
            if is_sel:
                pygame.draw.circle(screen, UI_PANEL, (nx, ny), 35)
                pygame.draw.circle(screen, color, (nx, ny), 35, 3)
                
                # Info panel at bottom
                info_rect = pygame.Rect(40, SCREEN_HEIGHT - 120, SCREEN_WIDTH - 80, 100)
                pygame.draw.rect(screen, UI_PANEL, info_rect, border_radius=10)
                pygame.draw.rect(screen, UI_BORDER, info_rect, 2, border_radius=10)
                
                self._text(screen, node.name, font_node, UI_ACCENT, 60, SCREEN_HEIGHT - 110)
                self._text(screen, f"Cost: ${node.cost}", font_info, WHITE, SCREEN_WIDTH - 150, SCREEN_HEIGHT - 110)
                self._wrap_text(screen, node.description, font_desc, UI_TEXT, 60, SCREEN_HEIGHT - 85, SCREEN_WIDTH - 200)
                
                if node.effect:
                    eff_txt = " | ".join(f"{k}: +{v}" for k, v in node.effect.items())
                    self._text(screen, eff_txt, font_info, NOTIF_SUCCESS, 60, SCREEN_HEIGHT - 50)
            
            # Node circle
            pygame.draw.circle(screen, UI_BG, (nx, ny), 28)
            pygame.draw.circle(screen, color, (nx, ny), 28, 2)
            
            # Label
            label = font_node.render(node.name[:2], True, color)
            screen.blit(label, label.get_rect(center=(nx, ny)))
            
            # Full name above/below
            full_name = font_desc.render(node.name, True, color)
            screen.blit(full_name, full_name.get_rect(midtop=(nx, ny + 32)))

        # Footer hint
        from src.controller import get_controller
        controller = get_controller()
        controller_connected = controller.connected and getattr(controller, "last_input_method", "keyboard") == "controller"

        if controller_connected:
            hint_txt = "D-pad: Navigate  |  [A]: Unlock  |  [Y]: Back"
        else:
            hint_txt = "Arrows: Navigate  |  ENTER: Unlock  |  ESC: Back"
        hint = font_desc.render(hint_txt, True, UI_TEXT_DIM)
        screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 25)))

    def _calculate_layout(self, node, x_start, x_end, y, y_step):
        """Recursively calculate positions for nodes."""
        mid_x = (x_start + x_end) // 2
        self._node_pos[node] = (mid_x, y)
        
        if node.children:
            child_w = (x_end - x_start) // len(node.children)
            for i, child in enumerate(node.children):
                self._calculate_layout(child, x_start + i * child_w, x_start + (i + 1) * child_w, y + y_step, y_step)

    def _text(self, s, text, font, color, x, y):
        s.blit(font.render(text, True, color), (x, y))

    def _wrap_text(self, s, text, font, color, x, y, max_w):
        words = text.split()
        lines = []
        cur_line = ""
        for w in words:
            test = cur_line + " " + w if cur_line else w
            if font.size(test)[0] <= max_w:
                cur_line = test
            else:
                lines.append(cur_line)
                cur_line = w
        lines.append(cur_line)
        for i, line in enumerate(lines):
            s.blit(font.render(line, True, color), (x, y + i * 18))


# ══════════════════════════════════════════════════════════════
#  FACTORY FUNCTIONS — build per-character trees
# ══════════════════════════════════════════════════════════════

def build_aiden_tree() -> SkillTree:
    """Construct Aiden's skill tree.

    Branches: Strength, Athleticism, Popularity.
    """
    root = SkillNode("Aiden Skills", "Aiden's abilities")

    # ── Strength ──
    strength = SkillNode("Strength", "Raw power branch", cost=0)
    strength.unlocked = True  # branch unlocked by default
    strength.add_child(SkillNode(
        "Heavy Punch", "A devastating single blow",
        cost=10, effect={"attack_damage": 5},
    ))
    strength.add_child(SkillNode(
        "Combo Master", "Chain hits faster",
        cost=20, effect={"combo_speed": 2},
    ))
    strength.add_child(SkillNode(
        "Knockback", "Push enemies back on hit",
        cost=20, effect={"knockback_force": 3},
    ))
    root.add_child(strength)

    # ── Athleticism ──
    athleticism = SkillNode("Athleticism", "Speed & endurance branch", cost=0)
    athleticism.unlocked = True
    athleticism.add_child(SkillNode(
        "Sprint Boost", "Move faster while sprinting",
        cost=10, effect={"sprint_speed": 2},
    ))
    athleticism.add_child(SkillNode(
        "Dodge Roll", "Roll to evade attacks",
        cost=20, effect={"dodge_distance": 3},
    ))
    athleticism.add_child(SkillNode(
        "Stamina+", "Increase max stamina",
        cost=10, effect={"max_stamina": 20},
    ))
    root.add_child(athleticism)

    # ── Popularity ──
    popularity = SkillNode("Popularity", "Social influence branch", cost=0)
    popularity.unlocked = True
    popularity.add_child(SkillNode(
        "Team Leader", "+reputation gain with Athletes",
        cost=10, effect={"rep_athletes_bonus": 5},
    ))
    popularity.add_child(SkillNode(
        "Crowd Support", "NPCs may help in combat",
        cost=20, effect={"crowd_chance": 10},
    ))
    popularity.add_child(SkillNode(
        "Influence Aura", "Nearby NPCs respect you more",
        cost=30, effect={"respect_aura": 5},
    ))
    root.add_child(popularity)

    return SkillTree(root)


def build_lena_tree() -> SkillTree:
    """Construct Lena's skill tree.

    Branches: Hacking, Intelligence, Social Engineering.
    """
    root = SkillNode("Lena Skills", "Lena's abilities")

    # ── Hacking ──
    hacking = SkillNode("Hacking", "Digital infiltration branch", cost=0)
    hacking.unlocked = True
    hacking.add_child(SkillNode(
        "Faster Cracking", "Reduce hack minigame timer",
        cost=10, effect={"hack_time_bonus": 3},
    ))
    hacking.add_child(SkillNode(
        "Security Override", "Bypass tougher locks",
        cost=20, effect={"hack_difficulty_reduction": 1},
    ))
    hacking.add_child(SkillNode(
        "Camera Control", "Remote-view security cameras",
        cost=20, effect={"camera_range": 2},
    ))
    root.add_child(hacking)

    # ── Intelligence ──
    intelligence = SkillNode("Intelligence", "Knowledge & analysis branch", cost=0)
    intelligence.unlocked = True
    intelligence.add_child(SkillNode(
        "Better Clues", "Highlight hidden interactables",
        cost=10, effect={"clue_radius": 50},
    ))
    intelligence.add_child(SkillNode(
        "Puzzle Solver", "Extra hints in puzzles",
        cost=20, effect={"puzzle_hints": 1},
    ))
    intelligence.add_child(SkillNode(
        "XP Boost", "Earn 20% more XP",
        cost=20, effect={"xp_multiplier": 20},
    ))
    root.add_child(intelligence)

    # ── Social Engineering ──
    social = SkillNode("Social Engineering", "Manipulation & persuasion", cost=0)
    social.unlocked = True
    social.add_child(SkillNode(
        "Better Trades", "Improved trade values",
        cost=10, effect={"trade_bonus": 10},
    ))
    social.add_child(SkillNode(
        "Persuasion", "Unlock new dialogue options",
        cost=20, effect={"persuasion_level": 1},
    ))
    social.add_child(SkillNode(
        "Lie Detection", "See NPC private face sooner",
        cost=30, effect={"trust_reveal_threshold": -15},
    ))
    root.add_child(social)

    return SkillTree(root)
