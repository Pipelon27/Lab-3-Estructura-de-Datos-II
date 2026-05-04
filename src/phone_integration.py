"""
src/phone_integration.py  —  Phone system integration layer
==========================================================
Bridges the phone with game systems:
  • Missions → Academic Tasks
  • Reputation events → Social posts
  • NPC dialogue → Text messages
  • Game time → Schedule

This layer ensures the phone feels reactive to story events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from src.phone import (
    Phone, SocialPost, TextMessage, AcademicTask, 
    ScheduleEvent, PhoneApp
)

if TYPE_CHECKING:
    from src.mission import MissionManager
    from src.reputation import ReputationSystem
    from src.dialogue import DialogueSystem


# ══════════════════════════════════════════════════════════════
#  PHONE INTEGRATION MANAGER
# ══════════════════════════════════════════════════════════════

class PhoneIntegrationManager:
    """
    Manages bidirectional communication between game systems
    and the phone.
    
    Responsibilities:
      • Convert game events → phone notifications/posts
      • Convert phone interactions → game consequences
      • Sync data between systems
      • Handle narrative branching based on phone usage
    """

    def __init__(self, phone: Phone):
        self.phone = phone
        self.post_counter = 0
        self.message_counter = 0
        self.task_counter = 0
        
        # Track which NPCs have sent messages
        self.messaging_npcs: set[str] = set()
        
        # Social dynamics tracking
        self.anonymously_posted_about: dict[str, int] = {}  # npc_id -> count
        self.bullying_incidents: list[dict] = []  # for narrative tracking
    
    # ──────────────────────────────────────────────────────────
    #  MISSION ↔ ACADEMIC TASK SYNC
    # ──────────────────────────────────────────────────────────
    
    def sync_missions_to_phone(self, missions: list):
        """
        Convert game missions to academic tasks.
        
        Missions marked with metadata 'is_phone_task' = True
        will appear in the academic app.
        """
        self.phone.academic_tasks.clear()
        
        for mission in missions:
            # Check if this mission should appear as an academic task
            if not getattr(mission, 'visible_on_phone', True):
                continue
            
            # Map mission status to task status
            status_map = {
                "not_started": "pending",
                "active": "in_progress",
                "completed": "completed",
                "failed": "pending",
            }
            
            task_status = status_map.get(mission.status, "pending")
            
            # Calculate progress (0.0 to 1.0)
            progress = getattr(mission, 'phone_progress', 0.0)
            if mission.status == "completed":
                progress = 1.0
            
            # Get issuer name (if mission has npc_issuer field)
            issuer = getattr(mission, 'npc_issuer', 'Sistema')
            
            task = AcademicTask(
                id=f"task_{mission.id}",
                title=mission.title,
                description=mission.description,
                issuer=issuer,
                status=task_status,
                deadline=getattr(mission, 'deadline', None),
                progress=progress,
                is_main_mission=mission.priority > 0,
            )
            
            self.phone.add_academic_task(task)
    
    def mission_completed_callback(self, mission_id: str, mission_title: str):
        """Called when a mission is completed."""
        self.phone.update_academic_task(
            f"task_{mission_id}",
            status="completed",
            progress=1.0
        )
        
        # Optional: post to social feed
        # (representing the player's accomplishment)
        self._create_system_notification(
            f"¡Tarea completada! {mission_title}",
            is_system=True
        )
    
    # ──────────────────────────────────────────────────────────
    #  REPUTATION ↔ SOCIAL FEED SYNC
    # ──────────────────────────────────────────────────────────
    
    def create_social_post(
        self,
        content: str,
        author_npc_id: str = None,
        author_name: str = "Desconocido",
        is_anonymous: bool = False,
        affects_reputation: bool = False,
        reputation_target: str = None,
        image_tag: str = None,
    ) -> SocialPost:
        """
        Create a social post.
        
        Args:
            content: Post text
            author_npc_id: NPC that posted (None if anonymous)
            author_name: Display name
            is_anonymous: Whether it's anonymous
            affects_reputation: If True, impacts game reputation
            reputation_target: Who is affected (usually player name)
            image_tag: Optional emoji/tag for visual category
        """
        self.post_counter += 1
        
        post = SocialPost(
            id=f"post_{self.post_counter}",
            author=author_name,
            author_npc_id=author_npc_id,
            content=content,
            timestamp="ahora",  # TODO: integrate with game time
            is_anonymous=is_anonymous,
            likes=0,
            mentions=[],
            image_tag=image_tag,
            affects_reputation=affects_reputation,
            reputation_target=reputation_target,
        )
        
        self.phone.add_social_post(post)
        
        # Track anonymously posted content
        if is_anonymous and reputation_target:
            self.anonymously_posted_about[reputation_target] = \
                self.anonymously_posted_about.get(reputation_target, 0) + 1
        
        return post
    
    def bullying_incident(
        self,
        bully_npc_id: str,
        victim_npc_id: str,
        incident_type: str,  # "post", "rumor", "taunt", etc.
        is_anonymous: bool = True,
    ):
        """
        Log a bullying incident.
        
        This affects:
          • Social posts (anonymous posts about victim)
          • Reputation of bully/victim
          • Game events and narrative branches
          • Player's standing with other NPCs
        """
        incident_descriptions = {
            "post": f"Se compartió algo negativo sobre {victim_npc_id}",
            "rumor": f"Circulan rumores sobre {victim_npc_id}",
            "taunt": f"Burlas públicas a {victim_npc_id}",
            "exclusion": f"Se excluyó a {victim_npc_id} de actividades",
        }
        
        description = incident_descriptions.get(incident_type, "Incidente social negativo")
        
        # Create anonymous post
        self.create_social_post(
            content=description,
            author_npc_id=bully_npc_id if not is_anonymous else None,
            author_name="Anónimo" if is_anonymous else f"NPC_{bully_npc_id}",
            is_anonymous=is_anonymous,
            affects_reputation=True,
            reputation_target=victim_npc_id,
            image_tag="⚠️",
        )
        
        # Log incident for narrative tracking
        self.bullying_incidents.append({
            "bully": bully_npc_id,
            "victim": victim_npc_id,
            "type": incident_type,
            "anonymous": is_anonymous,
        })
    
    def like_post(self, post_id: str):
        """Like a social post."""
        for post in self.phone.social_posts:
            if post.id == post_id:
                post.likes += 1
                break
    
    # ──────────────────────────────────────────────────────────
    #  NPC DIALOGUE ↔ MESSAGES SYNC
    # ──────────────────────────────────────────────────────────
    
    def send_text_message(
        self,
        npc_id: str,
        npc_name: str,
        content: str,
        is_response: bool = False,
    ) -> TextMessage:
        """
        Send a text message from an NPC to the player.
        
        Represents:
          • NPC responses to player actions
          • Narrative updates
          • Social interactions
          • Quest hints (contextual help)
        """
        self.message_counter += 1
        
        message = TextMessage(
            id=f"msg_{self.message_counter}",
            sender_npc_id=npc_id,
            sender_name=npc_name,
            content=content,
            timestamp="ahora",  # TODO: integrate with game time
            is_read=False,
            attachment=None,
        )
        
        self.phone.add_text_message(npc_id, message)
        self.messaging_npcs.add(npc_id)
        
        return message
    
    def get_npc_conversations(self) -> dict[str, list[TextMessage]]:
        """Get all conversations grouped by NPC."""
        return self.phone.messages.copy()
    
    # ──────────────────────────────────────────────────────────
    #  SCHEDULE MANAGEMENT
    # ──────────────────────────────────────────────────────────
    
    def set_daily_schedule(self, day_schedule: list[tuple]):
        """
        Set the schedule from the game's day schedule.
        
        Expected format: list of (DayPhase enum, duration_minutes)
        Converts to ScheduleEvent objects for the phone.
        """
        events = []
        
        phase_to_event = {
            # These names should match your actual DayPhase enum
            "morning_arrival": ScheduleEvent(8, "Llegada", "Entrada", ""),
            "class_1": ScheduleEvent(9, "Clase 1", "Aula", ""),
            "break": ScheduleEvent(11, "Descanso", "Patio", ""),
            "class_2": ScheduleEvent(12, "Clase 2", "Aula", ""),
            "lunch": ScheduleEvent(13, "Almuerzo", "Cafetería", ""),
            "class_3": ScheduleEvent(14, "Clase 3", "Aula", ""),
            "after_school": ScheduleEvent(16, "Después de clases", "Campus", ""),
            "departure": ScheduleEvent(17, "Salida", "Entrada", ""),
        }
        
        for phase, duration in day_schedule:
            phase_name = str(phase).lower()
            if phase_name in phase_to_event:
                events.append(phase_to_event[phase_name])
        
        self.phone.set_schedule_events(events)
    
    # ──────────────────────────────────────────────────────────
    #  NARRATIVE CONSEQUENCES
    # ──────────────────────────────────────────────────────────
    
    def check_phone_driven_events(self) -> list[dict]:
        """
        Check if phone activity has triggered narrative events.
        
        Returns list of triggered events:
          • Too many anonymous posts about someone → isolation
          • Certain message exchanges → romance/friendship flags
          • Task completions → reputation changes
        """
        triggered_events = []
        
        # Check for bullying escalation
        for victim, count in self.anonymously_posted_about.items():
            if count >= 3:  # threshold
                triggered_events.append({
                    "type": "bullying_escalation",
                    "victim": victim,
                    "severity": min(count // 3, 3),  # 1-3 severity levels
                })
        
        return triggered_events
    
    # ──────────────────────────────────────────────────────────
    #  UTILITIES
    # ──────────────────────────────────────────────────────────
    
    def _create_system_notification(self, text: str, is_system: bool = True):
        """Create a system-generated notification/post."""
        if is_system:
            self.create_social_post(
                content=text,
                author_name="📌 Sistema",
                author_npc_id=None,
                is_anonymous=False,
                image_tag="📌",
            )
    
    def get_bullying_report(self) -> dict:
        """
        Get a summary of bullying incidents for narrative/ending calculation.
        
        Returns:
          • Total incidents
          • Most bullied NPCs
          • Most anonymous posts
          • Patterns
        """
        incident_count = len(self.bullying_incidents)
        
        victim_counts = {}
        for incident in self.bullying_incidents:
            victim = incident["victim"]
            victim_counts[victim] = victim_counts.get(victim, 0) + 1
        
        most_bullied = max(victim_counts.items(), key=lambda x: x[1]) if victim_counts else (None, 0)
        
        return {
            "total_incidents": incident_count,
            "most_bullied": most_bullied[0],
            "most_bullied_count": most_bullied[1],
            "unique_victims": len(victim_counts),
            "anonymous_posts_count": sum(1 for i in self.bullying_incidents if i["anonymous"]),
        }
