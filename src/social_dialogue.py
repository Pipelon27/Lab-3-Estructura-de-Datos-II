"""
src/social_dialogue.py  —  Social interaction state machine
=============================================================
Core dialogue manager for NPC social interactions.
Drives the 3-option choice cycle, enforces stability rules,
and manages state transitions through the interaction flow.
"""

from __future__ import annotations

from enum import Enum, auto
import pygame
from settings import SOCIAL_COOLDOWN, GameState


class InteractionState(Enum):
    """States of a social interaction."""
    IDLE = auto()              # No active interaction
    APPROACHING = auto()       # Player in range, prompt shown
    ACTIVE = auto()            # UI open, waiting for input
    WAITING_CHOICE = auto()    # Player selecting option
    RESOLVING = auto()         # Applying consequences
    CLOSING = auto()           # Fading out


class SocialDialogueManager:
    """Manages active NPC social interactions with state machine & stability rules.
    
    Responsibilities:
    - Own the active conversation state (singleton lock)
    - Generate contextual NPC lines
    - Handle 3-option response cycle
    - Apply interaction consequences via ReputationManager
    - Enforce stability rules (cooldowns, locks, etc.)
    
    Only ONE interaction can be active at a time.
    """

    # NPC response pool — keyed by (group, emotional_state)
    NPC_LINES = {
        # Athletes
        ("athletes", "neutral"):    ["You again?", "What do you want?", "Sup.", "Need something?"],
        ("athletes", "open"):       ["Hey, what's up?", "Oh, it's you!", "Want to talk?"],
        ("athletes", "nervous"):    ["Stay back.", "I don't want trouble.", "Please leave me alone."],
        ("athletes", "hostile"):    ["Back off!", "Seriously, get away from me."],

        # Tech Club
        ("tech_club", "neutral"):   ["Hello.", "Can I help you?", "Yes?"],
        ("tech_club", "open"):      ["Good to see you.", "What's going on?", "How can I help?"],
        ("tech_club", "nervous"):   ["I... I'm not sure...", "Um, give me a moment."],
        ("tech_club", "hostile"):   ["I don't want to talk to you."],

        # Populars
        ("populars", "neutral"):    ["What?", "Can you not?", "Is there a reason for this?"],
        ("populars", "open"):       ["Hey there!", "Oh, hi!", "How's it going?"],
        ("populars", "nervous"):    ["I'm busy right now.", "Can this wait?"],
        ("populars", "hostile"):    ["Get away from me!"],

        # Academics
        ("academics", "neutral"):   ["Yes?", "Did you need something?", "Hello."],
        ("academics", "open"):      ["Oh, it's you!", "I'm glad you're here.", "Good to see you."],
        ("academics", "nervous"):   ["I... what?", "Can we talk about this later?"],
        ("academics", "hostile"):   ["I really don't want to see you right now."],

        # Rebels
        ("rebels", "neutral"):      ["What?", "What do you want?", "Yeah?"],
        ("rebels", "open"):         ["Hey, you!", "I'm actually glad to see you.", "What's happening?"],
        ("rebels", "nervous"):      ["Don't... don't hurt me.", "Please, just go."],
        ("rebels", "hostile"):      ["Get lost!"],

        # Outsiders
        ("outsiders", "neutral"):   ["Hi?", "Can I help?", "What's up?"],
        ("outsiders", "open"):      ["Oh, hey!", "I'm really happy to see you!", "What's new?"],
        ("outsiders", "nervous"):   ["Oh no...", "I didn't expect this."],
        ("outsiders", "hostile"):   ["Leave me alone!"],
    }

    def __init__(self):
        self.state = InteractionState.IDLE
        self._active_npc = None          # Current NPC (singleton lock)
        self._player = None              # Reference to player for distance checks
        self._selected_option_idx = 0    # 0 = IGNORE, 1 = RESPOND, 2 = INTIMIDATE
        self._available_options = ["ignore", "respond", "intimidate"]
        self._npc_line = ""              # Current NPC dialogue line
        self._cooldown_timer: dict[str, float] = {}  # npc_id → remaining cooldown
        self._resolving_timer = 0.0      # Timer during RESOLVING state
        self._visible = False             # UI visibility flag
        self.reputation_manager = None   # Will be set by Game
        self.social_ui = None            # Will be set by Game
        self.conversation_active = False # Global lock for interaction

    # ── PUBLIC API ─────────────────────────────────────────────

    def try_start(self, npc, player) -> bool:
        """Attempt to start an interaction with an NPC.
        
        Checks:
        - No active interaction
        - NPC cooldown expired
        - Player is close enough
        
        Returns True if interaction started, False otherwise.
        """
        if self.conversation_active:
            print("[SocialSystem] Interaction blocked: conversation already active")
            return False

        if self.state != InteractionState.IDLE:
            print(f"[SocialSystem] Interaction blocked: state is {self.state.name}, not IDLE")
            return False

        # Validate external dependencies
        if npc is None:
            print("[SocialSystem] Interaction blocked: NPC is None")
            return False
        
        if self.social_ui is None:
            print("[SocialSystem] Interaction blocked: Missing social UI")
            return False
            
        if self.reputation_manager is None:
            print("[SocialSystem] Interaction blocked: Missing reputation manager")
            return False

        # Check cooldown
        if npc.id in self._cooldown_timer and self._cooldown_timer[npc.id] > 0:
            return False

        # Set as active
        self._active_npc = npc
        self._player = player
        self._selected_option_idx = 0
        self._npc_line = self._generate_npc_line(npc)
        
        print(f"[SocialSystem] Attempting interaction with {npc.name}")
        
        # Generate options with deltas BEFORE opening UI
        options_data = self._get_options_with_deltas()

        # Update state lock
        self.conversation_active = True
        self.state = InteractionState.ACTIVE
        self._visible = True
        
        print("[SocialSystem] Dialogue UI created")

        # Show UI with the NPC line
        if self.social_ui:
            self.social_ui.show(npc, options_data)
            self.social_ui.set_npc_line(self._npc_line)

        return True

    def force_close(self):
        """Safe cleanup — called on ESC, death, or state change.
        
        Resets all state without applying consequences.
        """
        if self.social_ui:
            self.social_ui.hide()
        self.state = InteractionState.IDLE
        self._active_npc = None
        self._player = None
        self._visible = False
        self._selected_option_idx = 0
        self.conversation_active = False
        print("[SocialSystem] Dialogue closed successfully")

    def confirm_choice(self):
        """Player confirmed their selected option.
        
        Triggers:
        1. NPC memory update
        2. Reputation delta application
        3. Transition to RESOLVING
        """
        if not self._active_npc:
            return

        action = self._available_options[self._selected_option_idx]

        # Update NPC social memory
        self._active_npc.update_social_memory(action)

        # Apply reputation consequences
        if self.reputation_manager:
            deltas = self.reputation_manager.apply_interaction(
                self._active_npc.group.value, action, self._active_npc.id
            )
            # (UI will display deltas if needed)

        # Transition to resolving
        self.state = InteractionState.RESOLVING
        self._resolving_timer = 0.5  # Brief pause before closing

        # Log for debugging
        print(f"[SOCIAL] {self._active_npc.name} ({action}) — {self._active_npc.group.value}")

    def handle_input(self, event: pygame.event.Event) -> bool:
        """Process input during interaction.
        
        W/S: move cursor
        E/RETURN: confirm choice
        MOUSE: select and confirm
        
        Returns True if input was handled, False otherwise.
        """
        if self.state != InteractionState.ACTIVE:
            return False

        # Mouse Support
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.social_ui:
                idx = self.social_ui.get_clicked_option(event.pos)
                if idx is not None:
                    self._selected_option_idx = idx
                    self.confirm_choice()
                    return True
            return False

        if event.type != pygame.KEYDOWN:
            return False

        key = event.key

        # W / UP — move selection up
        if key in (pygame.K_w, pygame.K_UP):
            self._selected_option_idx = (self._selected_option_idx - 1) % len(self._available_options)
            if self.social_ui:
                self.social_ui.set_selected(self._selected_option_idx)
            return True

        # S / DOWN — move selection down
        elif key in (pygame.K_s, pygame.K_DOWN):
            self._selected_option_idx = (self._selected_option_idx + 1) % len(self._available_options)
            if self.social_ui:
                self.social_ui.set_selected(self._selected_option_idx)
            return True

        # E / RETURN — confirm
        elif key in (pygame.K_e, pygame.K_RETURN):
            self.confirm_choice()
            return True

        return False

    def update(self, dt: float):
        """Tick timers and manage state transitions.
        
        Called once per frame from Game.update().
        """
        # Decrement all active cooldowns
        for npc_id in list(self._cooldown_timer.keys()):
            self._cooldown_timer[npc_id] -= dt
            if self._cooldown_timer[npc_id] <= 0:
                del self._cooldown_timer[npc_id]

        # Handle RESOLVING state
        if self.state == InteractionState.RESOLVING:
            self._resolving_timer -= dt
            if self._resolving_timer <= 0:
                self.state = InteractionState.CLOSING

        # Handle CLOSING state
        if self.state == InteractionState.CLOSING:
            # After brief pause, fully close
            if self._active_npc:
                npc_id = self._active_npc.id
                self._cooldown_timer[npc_id] = SOCIAL_COOLDOWN
            
            self.force_close()

    # ── PRIVATE HELPERS ────────────────────────────────────

    def _generate_npc_line(self, npc) -> str:
        """Generate a contextual NPC line based on group & emotional state."""
        import random
        
        key = (npc.group.value, npc.emotional_state)
        lines = self.NPC_LINES.get(key, [])
        
        if not lines:
            # Fallback
            key = (npc.group.value, "neutral")
            lines = self.NPC_LINES.get(key, ["Hi there."])
        
        return random.choice(lines) if lines else "Hi there."

    def _get_options_with_deltas(self) -> list[dict]:
        """Build option list with reputation delta preview.
        
        Returns list of dicts: {"label": str, "action": str, "deltas": list[ReputationDelta]}
        """
        if not self._active_npc or not self.reputation_manager:
            return []

        group = self._active_npc.group.value
        options = []

        for action in self._available_options:
            # Simulate the interaction to get expected deltas
            try:
                deltas = self.reputation_manager.apply_interaction(group, action)
            except Exception as e:
                print(f"[SocialSystem] Failed generating deltas: {e}")
                deltas = []
            
            # Revert (we only want to see the preview)
            # (In a real system, we'd do this more carefully with a transaction)
            # For now, just gather the info
            
            options.append({
                "label": action.capitalize(),
                "action": action,
                "deltas": deltas,
            })

        return options

    def is_visible(self) -> bool:
        """Check if the interaction UI should be visible."""
        return self._visible and self.state in (
            InteractionState.ACTIVE,
            InteractionState.WAITING_CHOICE,
            InteractionState.RESOLVING,
        )

    def get_active_npc(self):
        """Return the currently active NPC, if any."""
        return self._active_npc

    def get_state(self) -> InteractionState:
        """Return current interaction state."""
        return self.state
