import re
from datetime import datetime, timezone, timedelta

import discord

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━"

_GMT7 = timezone(timedelta(hours=7))

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_raid_datetime(date_time_str: str) -> datetime | None:
    """Parse '14 May 2026 | 08:30 GMT+7' (or legacy '...WIB') into a timezone-aware datetime.

    Returns None if the string does not match the expected format.
    """
    match = re.match(
        r"(\d{1,2})\s+(\w+)\s+(\d{4})\s*\|\s*(\d{1,2}):(\d{2})\s*(?:GMT\+7|WIB)",
        date_time_str.strip(),
    )
    if not match:
        return None

    day, month_str, year, hour, minute = match.groups()
    month = _MONTHS.get(month_str)
    if not month:
        return None

    try:
        return datetime(int(year), month, int(day), int(hour), int(minute), tzinfo=_GMT7)
    except ValueError:
        return None


_DAY_EN   = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTH_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_gmt7(date_time_str: str) -> str:
    """Format a stored date-time string for display in GMT+7, 24-hour format.

    Example output: 'Wednesday, 14 May 2026 • 08:30 GMT+7'
    Falls back to the raw string if parsing fails.
    """
    dt = _parse_raid_datetime(date_time_str)
    if not dt:
        return date_time_str
    day_name   = _DAY_EN[dt.weekday()]
    month_name = _MONTH_EN[dt.month]
    return f"{day_name}, {dt.day:02d} {month_name} {dt.year} • {dt.hour:02d}:{dt.minute:02d} GMT+7"

def get_role_mention(guild: discord.Guild,role_name: str) -> str:
    """
    Search role by name and return mention.
    """

    role = discord.utils.get(
        guild.roles,
        name=role_name
    )

    if role:
        return role.mention

    return f"@{role_name}"
    

def build_raid_text(guild: discord.Guild,session: dict) -> str:
    """Build the full message text for a raid session."""
    is_done       = session.get("status") == "done"
    apostle_slots = [s for s in session["slots"] if s["category"] == "apostle"]
    hitter_slots  = [s for s in session["slots"] if s["category"] == "hitter"]
    filled        = sum(1 for s in session["slots"] if s["claimed_by"])
    total         = len(session["slots"])

    date_display = _format_gmt7(session["date_time"])

    lines: list[str] = []

    if is_done:
        lines.append("## ✅ DUNGEON COMPLETED ✅")

    initiator_id = session.get("created_by")
    initiator_text = f"<@{initiator_id}>" if initiator_id else "Unknown"

    lines += [
        f"**Date & Time : {date_display}**",
        f"👤 **Initiated by:** {initiator_text}",
        SEPARATOR,
        get_role_mention(guild,session["template_name"]),
    ]

    for slot in apostle_slots:
        claimed = f"**{slot['claimed_username']}**" if slot["claimed_by"] else "[Unclaimed]"
        lines.append(f"🔮 **{slot['role']}:** {claimed}")

    if hitter_slots and len(hitter_slots) == 5:
        lines.append("⚔️ **Hitters:**")
        for i, slot in enumerate(hitter_slots):
            claimed   = f"**{slot['claimed_username']}**" if slot["claimed_by"] else "[Unclaimed]"
            connector = "┗" if i == len(hitter_slots) - 1 else "┣"
            lines.append(f"   {connector} ⚔️ {slot['role']} = {claimed}")
    else:
        lines.append("⚔️ Participants:")
        for i, slot in enumerate(hitter_slots):
            claimed   = f"**{slot['claimed_username']}**" if slot["claimed_by"] else "[Unclaimed]"
            connector = "┗" if i == len(hitter_slots) - 1 else "┣"
            lines.append(f"   {connector} ⚔️ {slot['role']} = {claimed}")

    if is_done:
        lines.append(f"> ✅ {filled}/{total} slots • ID: `{session['id']}`")
    else:
        lines.append(f"> 🎯 {filled}/{total} slots • ID: `{session['id']}`")

    return "\n".join(lines)


def build_raid_view(session: dict) -> discord.ui.View:
    """Build the Discord View with Join/Leave slot buttons plus Done and Delete.

    Active layout (example: 6 slots):
        Row 0 : slot 0 · slot 1 · slot 2
        Row 1 : slot 3 · slot 4 · slot 5
        Row 2 : ✅ Done · 🗑️ Delete

    Done layout:
        Row 0 : ✅ Dungeon Completed (disabled) · 🗑️ Delete
    """
    view    = discord.ui.View(timeout=None)
    is_done = session.get("status") == "done"

    if is_done:
        view.add_item(discord.ui.Button(
            label="✅ Dungeon Completed",
            style=discord.ButtonStyle.success,
            custom_id=f"rnoop:{session['id']}",
            disabled=True,
            row=0,
        ))
        view.add_item(discord.ui.Button(
            label="Delete",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            custom_id=f"rdel:{session['id']}",
            row=0,
        ))
        return view

    for idx, slot in enumerate(session["slots"]):
        row = idx // 3
        if slot["claimed_by"]:
            btn = discord.ui.Button(
                label=slot["role"],
                style=discord.ButtonStyle.danger,
                emoji="🚪",
                custom_id=f"rleave:{session['id']}:{idx}",
                row=row,
            )
        else:
            style = (discord.ButtonStyle.primary
                     if slot["category"] == "apostle"
                     else discord.ButtonStyle.secondary)
            emoji = "🔮" if slot["category"] == "apostle" else "⚔️"
            btn   = discord.ui.Button(
                label=slot["role"],
                style=style,
                emoji=emoji,
                custom_id=f"rjoin:{session['id']}:{idx}",
                row=row,
            )
        view.add_item(btn)

    action_row = min((len(session["slots"]) + 2) // 3, 4)
    view.add_item(discord.ui.Button(
        label="Done",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id=f"rdone:{session['id']}",
        row=action_row,
    ))
    view.add_item(discord.ui.Button(
        label="Delete",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id=f"rdel:{session['id']}",
        row=action_row,
    ))

    return view
