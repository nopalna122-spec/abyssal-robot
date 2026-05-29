from datetime import datetime, timezone, timedelta

from .db import get_connection
from .templates import RAID_TEMPLATES
from .views import _parse_raid_datetime

# Session ID counter — stored in a list so closures can mutate it
_counter: list[int] = [1]


def load_counter() -> None:
    """Read the highest session ID from the DB on startup using MAX() — O(1), no full scan."""
    conn = get_connection()
    row = conn.execute("SELECT MAX(CAST(id AS INTEGER)) AS max_id FROM raid_sessions").fetchone()
    conn.close()
    _counter[0] = (row["max_id"] or 0) + 1


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_session(session_row, slot_rows) -> dict:
    """Combine a session row and its slot rows into a single Python dict."""
    slots = sorted(slot_rows, key=lambda s: s["slot_index"])

    return {
        "id":            session_row["id"],
        "template_key":  session_row["template_key"],
        "template_name": session_row["template_name"],
        "date_time":     session_row["date_time"],
        "created_by":    session_row["created_by"],
        "message_id":    session_row["message_id"],
        "channel_id":    session_row["channel_id"],
        "created_at":    session_row["created_at"],
        "status":        session_row["status"] or "active",
        "expires_at":    session_row["expires_at"],
        "guild_id":      session_row["guild_id"],

        "slots": [
            {
                "role":             s["role"],
                "category":         s["category"],
                "claimed_by":       s["claimed_by"],
                "claimed_username": s["claimed_username"],
            }
            for s in slots
        ],
    }


# ── Public CRUD functions ─────────────────────────────────────────────────────

def create_session(
    template_key: str,
    date_time: str,
    created_by: str,
    guild_id: int
) -> dict | None:

    """Create a new raid session."""

    template = RAID_TEMPLATES.get(template_key)

    if not template:
        return None

    session_id = str(_counter[0])
    _counter[0] += 1

    now = datetime.now(timezone.utc)

    # Auto expire after 10 minutes
    raid_dt = _parse_raid_datetime(date_time)

    if raid_dt:
        expires_at = (
            raid_dt.astimezone(timezone.utc)
            + timedelta(minutes=10)
        ).isoformat()
    else:
        expires_at = (
            now + timedelta(minutes=10)
        ).isoformat()

    conn = get_connection()

    conn.execute(
        "INSERT INTO raid_sessions "
        "(id, guild_id, template_key, template_name, date_time, created_by, status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
        (
            session_id,
            guild_id,
            template_key,
            template.name,
            date_time,
            created_by,
            expires_at,
            now.isoformat(),
        ),
    )

    for i, slot in enumerate(template.slots):

        conn.execute(
            "INSERT INTO raid_slots "
            "(session_id, slot_index, role, category) "
            "VALUES (?, ?, ?, ?)",
            (
                session_id,
                i,
                slot.role,
                slot.category,
            ),
        )

    conn.commit()
    conn.close()

    return {
        "id":            session_id,
        "template_key":  template_key,
        "template_name": template.name,
        "date_time":     date_time,
        "created_by":    created_by,
        "message_id":    None,
        "channel_id":    None,
        "created_at":    now.isoformat(),
        "status":        "active",
        "expires_at":    expires_at,
        "guild_id":      guild_id,

        "slots": [
            {
                "role": s.role,
                "category": s.category,
                "claimed_by": None,
                "claimed_username": None,
            }
            for s in template.slots
        ],
    }


def get_session(session_id: str) -> dict | None:

    conn = get_connection()

    row = conn.execute(
        "SELECT * FROM raid_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if not row:
        conn.close()
        return None

    slots = conn.execute(
        "SELECT * FROM raid_slots WHERE session_id = ?",
        (session_id,)
    ).fetchall()

    conn.close()

    return _build_session(row, slots)


def get_all_sessions(guild_id: int) -> list[dict]:

    conn = get_connection()

    rows = conn.execute("""
        SELECT s.id, s.template_key, s.template_name, s.date_time,
               s.created_by, s.message_id, s.channel_id,
               s.created_at, s.status, s.expires_at,
               sl.slot_index, sl.role, sl.category,
               sl.claimed_by, sl.claimed_username
        FROM raid_sessions s
        LEFT JOIN raid_slots sl ON sl.session_id = s.id
        WHERE s.status = 'active'
          AND (s.expires_at IS NULL OR s.expires_at > datetime('now'))
          AND s.guild_id = ?
        ORDER BY s.created_at, sl.slot_index
    """, (guild_id,)).fetchall()

    conn.close()

    sessions: dict[str, dict] = {}

    for row in rows:

        sid = row["id"]

        if sid not in sessions:

            sessions[sid] = {
                "id":            row["id"],
                "template_key":  row["template_key"],
                "template_name": row["template_name"],
                "date_time":     row["date_time"],
                "created_by":    row["created_by"],
                "message_id":    row["message_id"],
                "channel_id":    row["channel_id"],
                "created_at":    row["created_at"],
                "status":        row["status"] or "active",
                "expires_at":    row["expires_at"],
                "slots":         [],
            }

        if row["slot_index"] is not None:

            sessions[sid]["slots"].append({
                "role":             row["role"],
                "category":         row["category"],
                "claimed_by":       row["claimed_by"],
                "claimed_username": row["claimed_username"],
            })

    return list(sessions.values())


def set_message_ref(
    session_id: str,
    message_id: int,
    channel_id: int,
) -> None:
    """
    Store Discord message/channel references
    so the bot can track raid messages.
    """

    conn = get_connection()

    conn.execute(
        """
        UPDATE raid_sessions
        SET message_id = ?, channel_id = ?
        WHERE id = ?
        """,
        (
            str(message_id),
            str(channel_id),
            session_id,
        ),
    )

    conn.commit()
    conn.close()


async def cleanup_expired_sessions(bot) -> int:
    """
    Send notification for expired raids,
    then delete them from database.
    """

    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    expired_sessions = conn.execute("""
        SELECT id, channel_id, template_name, created_by
        FROM raid_sessions
        WHERE expires_at IS NOT NULL
          AND expires_at < ?
    """, (now,)).fetchall()

    total = 0

    for session in expired_sessions:

        # Send expiration notification
        try:

            channel = bot.get_channel(int(session["channel_id"]))

            if channel:
                await channel.send(
                    f"⏰ The dungeon **{session['template_name']}** "
                    f"initiated by <@{session['created_by']}> "
                    f"has ended automatically after 10 minutes."
                )

        except Exception as e:
            print(f"Failed to send expiration message: {e}")

        # Delete session
        conn.execute(
            "DELETE FROM raid_sessions WHERE id = ?",
            (session["id"],)
        )

        total += 1

    conn.commit()
    conn.close()

    return total


def clear_all_sessions() -> int:

    conn = get_connection()

    cur = conn.execute("DELETE FROM raid_sessions")

    conn.commit()
    conn.close()

    _counter[0] = 1

    return cur.rowcount