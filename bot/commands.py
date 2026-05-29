from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from .storage import clear_all_sessions, create_session, get_all_sessions, set_message_ref
from .templates import RAID_TEMPLATES
from .views import build_raid_text, build_raid_view, get_role_mention

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Hour choices: 00 – 23
_HOUR_CHOICES = [
    app_commands.Choice(name=f"{h:02d}:--", value=h)
    for h in range(24)
]

# Minute choices: multiples of 10
_MINUTE_CHOICES = [
    app_commands.Choice(name=f"--:{m:02d}", value=m)
    for m in range(0, 60, 10)
]


def _build_date_time(hour: int, minute: int) -> str:
    """Return a date+time string in GMT+7 format for storage.

    If the chosen hour:minute has already passed today (GMT+7), tomorrow's
    date is used automatically.
    """
    now_utc = datetime.now(timezone.utc)
    gmt7    = now_utc + timedelta(hours=7)
    target  = gmt7.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if target < gmt7:
        target += timedelta(days=1)

    return f"{target.day} {_MONTHS[target.month - 1]} {target.year} | {hour:02d}:{minute:02d} GMT+7"


def setup_commands(bot: commands.Bot) -> None:
    """Register all slash commands onto bot.tree."""

    # ── /raid-open ────────────────────────────────────────────────────────────
    @bot.tree.command(name="raid-open", description="Open a new raid session")
    @app_commands.describe(
        raid_type="Raid type to open",
        hour="Raid start hour (GMT+7, 24-hour)",
        minute="Raid start minute (multiples of 10)",
    )
    @app_commands.choices(
        raid_type=[
            app_commands.Choice(name="Boma Dungeon",            value="boma"),
            app_commands.Choice(name="Samael Fortress Madness", value="samael"),
            app_commands.Choice(name="The Wandering Troupe",    value="wandering"),
        ],
        hour=_HOUR_CHOICES,
        minute=_MINUTE_CHOICES,
    )
    async def raid_open(
        interaction: discord.Interaction,
        raid_type: str,
        hour: int,
        minute: int,
    ) -> None:
        """Create a new raid session. Date is today or tomorrow based on the chosen time."""
        date_time = _build_date_time(hour, minute)
        session   = create_session(raid_type, date_time, str(interaction.user.id), interaction.guild.id)
        pingid    = get_role_mention(interaction.guild,session["template_name"])
        
        if not session:
            await interaction.response.send_message("❌ Invalid raid type.", ephemeral=True)
            return

        text = build_raid_text(interaction.guild,session)
        view = build_raid_view(session)

        await interaction.response.send_message(text, view=view,
            allowed_mentions=discord.AllowedMentions(roles=True))
        msg = await interaction.original_response()
        set_message_ref(session["id"], str(msg.id), str(interaction.channel_id))

    # ── /raid-list ────────────────────────────────────────────────────────────
    @bot.tree.command(name="raid-list", description="Show all active raid sessions")
    async def raid_list(interaction: discord.Interaction) -> None:
        """Display up to 5 active (non-expired) sessions with Join/Leave buttons."""
        sessions = get_all_sessions(interaction.guild.id)
        if not sessions:
            await interaction.response.send_message("📭 No active raid sessions found.")
            return

        await interaction.response.defer()

        for i, session in enumerate(sessions[:5]):
            text = build_raid_text(interaction.guild,session)
            view = build_raid_view(session)
            if i == 0:
                await interaction.edit_original_response(content=text, view=view)
            elif i == 1:
                await interaction.followup.send(content=text, view=view
                #,allowed_mentions=discord.AllowedMentions(roles=True)
                )
            else:
                await interaction.followup.send(content=text, view=view)

        if len(sessions) > 5:
            await interaction.followup.send(
                f"> ℹ️ Showing 5 of **{len(sessions)}** active sessions."
            )

    # ── /raid-help ────────────────────────────────────────────────────────────
    @bot.tree.command(name="raid-help", description="Show Raid Bot usage guide")
    async def raid_help(interaction: discord.Interaction) -> None:
        """Send the usage guide (only visible to the requesting user)."""
        template_list = "\n".join(
            f"**{t.name}** — {len(t.slots)} slots"
            for t in RAID_TEMPLATES.values()
        )
        text = "\n".join([
            "⚔️ **Raid Bot — Help**",
            "",
            "**Commands:**",
            "`/raid-open`  — Create a new raid session with Join/Leave buttons",
            "`/raid-list`  — Show all active sessions",
            "`/raid-help`  — Show this guide",
            "`/clear-all`  — Delete all sessions (server owner only)",
            "",
            "**Available Raid Types:**",
            template_list,
            "",
            "**How to use:**",
            "1. Use `/raid-open` → choose raid type, hour and minute (GMT+7)",
            "   → If the time has already passed today, tomorrow's date is used automatically",
            "2. Click **Join** to register for a slot",
            "3. Click **Leave** to unregister from a slot",
            "4. Click **Done** when the dungeon is complete",
            "5. Only the session creator can press **Done** or **Delete**",
        ])
        await interaction.response.send_message(text, ephemeral=True)

    # ── /clear-all (server owner only) ───────────────────────────────────────
    @bot.tree.command(name="clear-all", description="Delete all raid sessions (server owner only)")
    async def clear_all(interaction: discord.Interaction) -> None:
        """Wipe every session from the database. Restricted to the Discord server owner."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used inside a server.", ephemeral=True
            )
            return

        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                "❌ Only the server owner can use this command.", ephemeral=True
            )
            return

        total = clear_all_sessions()
        await interaction.response.send_message(
            f"🗑️ **{total} session(s) deleted.**",
            ephemeral=True,
        )


# ── /Test (server owner only) ───────────────────────────────────────