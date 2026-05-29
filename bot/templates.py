from dataclasses import dataclass
from typing import Literal

SlotCategory = Literal["apostle", "hitter"]


@dataclass
class SlotTemplate:
    """Definition of a single slot within a raid template (role name + category)."""
    role: str
    category: SlotCategory


@dataclass
class RaidTemplate:
    """A complete raid type definition, containing a display name and a list of slots."""
    name: str
    slots: list[SlotTemplate]


# ── Available raid types ───────────────────────────────────────────────────────
# To add a new raid type, insert a new entry here.
# The key is the internal value used in the database and slash commands.
RAID_TEMPLATES: dict[str, RaidTemplate] = {
    "boma": RaidTemplate(
        name="Boma Dungeon",
        slots=[
            SlotTemplate("Apostle",       "apostle"),
            SlotTemplate("High DPS",      "hitter"),
            SlotTemplate("Any DPS",       "hitter"),
            SlotTemplate("High Debuffer", "hitter"),
            SlotTemplate("Any Debuffer",  "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
        ],
    ),
    "samael": RaidTemplate(
        name="Samael Fortress Madness",
        slots=[
            SlotTemplate("Apostle",       "apostle"),
            SlotTemplate("High DPS",      "hitter"),
            SlotTemplate("High Debuffer", "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
        ],
    ),
    "wandering": RaidTemplate(
        name="Wandering Troupe",
        slots=[
            SlotTemplate("Any Roles",     "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
            SlotTemplate("Any Roles",     "hitter"),
        ],
    ),
}
