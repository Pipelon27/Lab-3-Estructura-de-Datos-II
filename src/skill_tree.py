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
    XP_PER_LEVEL, SKILL_POINT_PER_LEVEL,
)


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
        self.selected_index = 0       # for UI navigation
        self._flat:  list[SkillNode] = []   # cache for drawing
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
        if player.skill_points < node.cost:
            return False

        node.unlocked = True
        player.skill_points -= node.cost

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
            self.selected_index = max(0, self.selected_index - 1)
        elif event.key == pygame.K_DOWN:
            self.selected_index = min(len(self._flat) - 1, self.selected_index + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if 0 <= self.selected_index < len(self._flat):
                node = self._flat[self.selected_index]
                return self.unlock_skill(node, player)
        return None

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, player):
        """Render the full skill-tree screen."""
        screen.fill(UI_BG)

        font_title = pygame.font.SysFont("arial", 36, bold=True)
        font_node  = pygame.font.SysFont("arial", 22)
        font_desc  = pygame.font.SysFont("arial", 16)
        font_info  = pygame.font.SysFont("arial", 18)

        # Header
        screen.blit(
            font_title.render(f"Skill Tree  —  SP: {player.skill_points}", True, UI_ACCENT),
            (30, 20),
        )

        # List skills
        y = 80
        for i, skill in enumerate(self._flat):
            is_sel  = (i == self.selected_index)
            indent  = skill.depth() * 30
            prefix  = "►" if is_sel else " "
            status  = " ✓" if skill.unlocked else ""
            avail   = skill.is_available() and not skill.unlocked

            if skill.unlocked:
                colour = NOTIF_SUCCESS
            elif avail:
                colour = UI_ACCENT
            else:
                colour = UI_TEXT_DIM

            line = f"{prefix} {'  ' * (skill.depth() - 1)}{'├─ ' if skill.depth() > 1 else ''}{skill.name} (cost {skill.cost}){status}"
            surf = font_node.render(line, True, colour)
            rx   = 40 + indent
            ry   = y

            if is_sel:
                bg = pygame.Rect(rx - 6, ry - 2, SCREEN_WIDTH - 80 - indent, 28)
                pygame.draw.rect(screen, UI_PANEL, bg, border_radius=5)
                pygame.draw.rect(screen, colour, bg, 1, border_radius=5)
                # Description below list
                desc = font_desc.render(skill.description, True, UI_TEXT)
                screen.blit(desc, (40, SCREEN_HEIGHT - 80))
                # Effect
                if skill.effect:
                    eff_txt = "  |  ".join(f"{k} +{v}" for k, v in skill.effect.items())
                    screen.blit(font_info.render(eff_txt, True, NOTIF_SUCCESS), (40, SCREEN_HEIGHT - 55))

            screen.blit(surf, (rx, ry))
            y += 32

        # Footer hint
        hint = font_desc.render("↑↓ Navigate  |  ENTER Unlock  |  ESC Back", True, UI_TEXT_DIM)
        screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 25)))


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
        cost=1, effect={"attack_damage": 5},
    ))
    strength.add_child(SkillNode(
        "Combo Master", "Chain hits faster",
        cost=2, effect={"combo_speed": 2},
    ))
    strength.add_child(SkillNode(
        "Knockback", "Push enemies back on hit",
        cost=2, effect={"knockback_force": 3},
    ))
    root.add_child(strength)

    # ── Athleticism ──
    athleticism = SkillNode("Athleticism", "Speed & endurance branch", cost=0)
    athleticism.unlocked = True
    athleticism.add_child(SkillNode(
        "Sprint Boost", "Move faster while sprinting",
        cost=1, effect={"sprint_speed": 2},
    ))
    athleticism.add_child(SkillNode(
        "Dodge Roll", "Roll to evade attacks",
        cost=2, effect={"dodge_distance": 3},
    ))
    athleticism.add_child(SkillNode(
        "Stamina+", "Increase max stamina",
        cost=1, effect={"max_stamina": 20},
    ))
    root.add_child(athleticism)

    # ── Popularity ──
    popularity = SkillNode("Popularity", "Social influence branch", cost=0)
    popularity.unlocked = True
    popularity.add_child(SkillNode(
        "Team Leader", "+reputation gain with Athletes",
        cost=1, effect={"rep_athletes_bonus": 5},
    ))
    popularity.add_child(SkillNode(
        "Crowd Support", "NPCs may help in combat",
        cost=2, effect={"crowd_chance": 10},
    ))
    popularity.add_child(SkillNode(
        "Influence Aura", "Nearby NPCs respect you more",
        cost=3, effect={"respect_aura": 5},
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
        cost=1, effect={"hack_time_bonus": 3},
    ))
    hacking.add_child(SkillNode(
        "Security Override", "Bypass tougher locks",
        cost=2, effect={"hack_difficulty_reduction": 1},
    ))
    hacking.add_child(SkillNode(
        "Camera Control", "Remote-view security cameras",
        cost=2, effect={"camera_range": 2},
    ))
    root.add_child(hacking)

    # ── Intelligence ──
    intelligence = SkillNode("Intelligence", "Knowledge & analysis branch", cost=0)
    intelligence.unlocked = True
    intelligence.add_child(SkillNode(
        "Better Clues", "Highlight hidden interactables",
        cost=1, effect={"clue_radius": 50},
    ))
    intelligence.add_child(SkillNode(
        "Puzzle Solver", "Extra hints in puzzles",
        cost=2, effect={"puzzle_hints": 1},
    ))
    intelligence.add_child(SkillNode(
        "XP Boost", "Earn 20% more XP",
        cost=2, effect={"xp_multiplier": 20},
    ))
    root.add_child(intelligence)

    # ── Social Engineering ──
    social = SkillNode("Social Engineering", "Manipulation & persuasion", cost=0)
    social.unlocked = True
    social.add_child(SkillNode(
        "Better Trades", "Improved trade values",
        cost=1, effect={"trade_bonus": 10},
    ))
    social.add_child(SkillNode(
        "Persuasion", "Unlock new dialogue options",
        cost=2, effect={"persuasion_level": 1},
    ))
    social.add_child(SkillNode(
        "Lie Detection", "See NPC private face sooner",
        cost=3, effect={"trust_reveal_threshold": -15},
    ))
    root.add_child(social)

    return SkillTree(root)
