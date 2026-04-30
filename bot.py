import os
import discord
import mysql.connector
from discord.ext import commands

token = os.getenv("DISCORD_TOKEN")

if not token:
    raise ValueError("DISCORD_TOKEN environment variable is missing.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def getDbConnection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
        port=int(os.getenv("MYSQL_PORT", 3306))
    )


def getFactionForGuild(guildId):
    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT faction FROM guild_factions WHERE guild_id = %s",
        (guildId,)
    )

    result = cursor.fetchone()

    cursor.close()
    db.close()

    return result["faction"] if result else None


def playerExists(guildId, factionName, playerName):
    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM player_stats
        WHERE guild_id = %s AND faction = %s AND player_name = %s
        """,
        (guildId, factionName, playerName)
    )

    result = cursor.fetchone()

    cursor.close()
    db.close()

    return result is not None


def lonerGroupExists(guildId, factionName, groupName):
    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM loner_groups
        WHERE guild_id = %s AND faction = %s AND group_name = %s
        """,
        (guildId, factionName, groupName)
    )

    result = cursor.fetchone()

    cursor.close()
    db.close()

    return result is not None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.command()
@commands.has_permissions(administrator=True)
async def setupfaction(ctx, faction: str):
    allowedFactions = ["Freedom", "Duty", "Bandit", "Ecologist", "Military", "Granit"]

    if faction not in allowedFactions:
        await ctx.send(f"Invalid faction. Use one of: {', '.join(allowedFactions)}")
        return

    guildId = ctx.guild.id

    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO guild_factions (guild_id, faction)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE faction = VALUES(faction)
        """,
        (guildId, faction)
    )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(f"This server is now assigned to faction: **{faction}**")


@bot.command()
async def faction(ctx):
    factionName = getFactionForGuild(ctx.guild.id)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    await ctx.send(f"This server is assigned to: **{factionName}**")


@bot.command()
async def loneradd(ctx, player_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    if playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** already exists in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO player_stats (
            guild_id,
            faction,
            player_name,
            reputation,
            numQuestsCompleted,
            status
        )
        VALUES (%s, %s, %s, 0, 0, 'Neutral')
        """,
        (guildId, factionName, player_name)
    )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(f"Player **{player_name}** has been added to **{factionName}**.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def lonerremove(ctx, player_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    player_name = player_name.strip()

    if not playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor()

    # Remove from player_stats
    cursor.execute(
        """
        DELETE FROM player_stats
        WHERE guild_id = %s AND faction = %s AND player_name = %s
        """,
        (guildId, factionName, player_name)
    )

    # OPTIONAL: remove their active quests too
    cursor.execute(
        """
        DELETE FROM quests
        WHERE guild_id = %s AND faction = %s AND description LIKE %s
        """,
        (guildId, factionName, f"{player_name} |%")
    )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(
        f"**{player_name}** has been removed from **{factionName}**, including their active quests."
    )

@bot.command()
async def lonereditstatus(ctx, player_name: str, status: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    allowedStatuses = [
        "Hostile",
        "Untrustworthy",
        "Neutral",
        "Known",
        "Trustworthy",
        "Respected"
    ]

    if status not in allowedStatuses:
        await ctx.send(
            f"Invalid status. Use one of: {', '.join(allowedStatuses)}"
        )
        return

    if not playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE player_stats
        SET status = %s
        WHERE guild_id = %s AND faction = %s AND player_name = %s
        """,
        (status, guildId, factionName, player_name)
    )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(
        f"**{player_name}** status changed to **{status}** for **{factionName}**."
    )

@bot.command()
async def lonerstatus(ctx, player_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    # Optional normalization (recommended)
    player_name = player_name.strip()

    if not playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT reputation, numQuestsCompleted, status
        FROM player_stats
        WHERE guild_id = %s AND faction = %s AND player_name = %s
        """,
        (guildId, factionName, player_name)
    )

    stats = cursor.fetchone()

    cursor.close()
    db.close()

    # Safety fallback
    status = stats.get("status") if stats else None
    if not status:
        status = "Neutral"

    await ctx.send(
        f"**'{player_name}'**\n"
        f"Status: **{status}**\n"
        f"Completed Quests: **{stats['numQuestsCompleted']}**\n"
        f"Reputation: **{stats['reputation']}**"
    )

@bot.command()
async def lonergroupcreate(ctx, group_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    group_name = group_name.strip()

    db = getDbConnection()
    cursor = db.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO loner_groups (guild_id, faction, group_name)
            VALUES (%s, %s, %s)
            """,
            (guildId, factionName, group_name)
        )

        db.commit()
        await ctx.send(f"Loner group **{group_name}** created for **{factionName}**.")

    except mysql.connector.IntegrityError:
        await ctx.send(f"Loner group **{group_name}** already exists for **{factionName}**.")

    finally:
        cursor.close()
        db.close()


@bot.command()
async def lonergroupmemberadd(ctx, group_name: str, player_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    group_name = group_name.strip()
    player_name = player_name.strip()

    if not playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT 1
        FROM loner_groups
        WHERE guild_id = %s AND faction = %s AND group_name = %s
        """,
        (guildId, factionName, group_name)
    )

    group = cursor.fetchone()

    if not group:
        cursor.close()
        db.close()
        await ctx.send(f"Loner group **{group_name}** not found in **{factionName}**.")
        return

    try:
        cursor.execute(
            """
            INSERT INTO loner_group_members (guild_id, faction, group_name, player_name)
            VALUES (%s, %s, %s, %s)
            """,
            (guildId, factionName, group_name, player_name)
        )

        db.commit()
        await ctx.send(f"Added **{player_name}** to loner group **{group_name}**.")

    except mysql.connector.IntegrityError:
        await ctx.send(f"**{player_name}** is already in **{group_name}**.")

    finally:
        cursor.close()
        db.close()


@bot.command()
async def lonergroupmemberremove(ctx, group_name: str, player_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    group_name = group_name.strip()
    player_name = player_name.strip()

    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        DELETE FROM loner_group_members
        WHERE guild_id = %s
        AND faction = %s
        AND group_name = %s
        AND player_name = %s
        """,
        (guildId, factionName, group_name, player_name)
    )

    db.commit()
    removedCount = cursor.rowcount

    cursor.close()
    db.close()

    if removedCount == 0:
        await ctx.send(f"**{player_name}** was not found in **{group_name}**.")
        return

    await ctx.send(f"Removed **{player_name}** from loner group **{group_name}**.")

@bot.command()
async def lonergroupeditstatus(ctx, group_name: str, status: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    allowedStatuses = [
        "Hostile",
        "Untrustworthy",
        "Neutral",
        "Known",
        "Trustworthy",
        "Respected"
    ]

    if status not in allowedStatuses:
        await ctx.send(f"Invalid status. Use one of: {', '.join(allowedStatuses)}")
        return

    if not lonerGroupExists(guildId, factionName, group_name):
        await ctx.send(f"Loner group **{group_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE loner_groups
        SET status = %s
        WHERE guild_id = %s AND faction = %s AND group_name = %s
        """,
        (status, guildId, factionName, group_name)
    )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(f"Loner group **{group_name}** status changed to **{status}**.")

@bot.command()
async def lonergroupstatus(ctx, group_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT status
        FROM loner_groups
        WHERE guild_id = %s AND faction = %s AND group_name = %s
        """,
        (guildId, factionName, group_name)
    )

    group = cursor.fetchone()

    if not group:
        cursor.close()
        db.close()
        await ctx.send(f"Loner group **{group_name}** not found in **{factionName}**.")
        return

    cursor.execute(
        """
        SELECT player_name
        FROM loner_group_members
        WHERE guild_id = %s AND faction = %s AND group_name = %s
        ORDER BY player_name ASC
        """,
        (guildId, factionName, group_name)
    )

    members = cursor.fetchall()

    cursor.close()
    db.close()

    memberList = "\n".join([f"- {member['player_name']}" for member in members])

    if not memberList:
        memberList = "No members."

    await ctx.send(
        f"**Loner Group: {group_name}**\n"
        f"Faction: **{factionName}**\n"
        f"Status: **{group['status'] or 'Neutral'}**\n\n"
        f"**Members:**\n{memberList}"
    )

@bot.command()
async def questgive(ctx, player_name: str, quest: str, *, notes: str = ""):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet. Use `!setupfaction` first.")
        return

    if not playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** not found. Use `!loneradd \"{player_name}\"` first.")
        return

    db = getDbConnection()
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO quests (guild_id, faction, title, description, created_by)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            guildId,
            factionName,
            quest,
            f"{player_name} | {notes}",
            ctx.author.id
        )
    )

    db.commit()
    questId = cursor.lastrowid

    cursor.close()
    db.close()

    await ctx.send(
        f"**Quest Assigned**\n"
        f"Faction: **{factionName}**\n"
        f"Player: **{player_name}**\n"
        f"Quest: **{quest}**\n"
        f"Notes: {notes if notes else 'None'}\n"
        f"ID: `{questId}`"
    )


@bot.command()
async def questshowplayer(ctx, player_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    if not playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, title, description, created_at
        FROM quests
        WHERE guild_id = %s
        AND faction = %s
        AND description LIKE %s
        ORDER BY created_at DESC
        """,
        (guildId, factionName, f"{player_name} |%")
    )

    quests = cursor.fetchall()
    cursor.close()
    db.close()

    if not quests:
        await ctx.send(f"No active quests found for **{player_name}**.")
        return

    message = f"**Quests for {player_name} — {factionName}**\n\n"

    for quest in quests:
        description = quest["description"] or ""
        notes = description.split(" | ", 1)[1] if " | " in description else description
        message += f"`{quest['id']}` — **{quest['title']}**\nNotes: {notes if notes else 'None'}\n\n"

    await ctx.send(message)

@bot.command()
async def questgivelonergroup(ctx, group_name: str, quest: str, *, notes: str = ""):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    if not lonerGroupExists(guildId, factionName, group_name):
        await ctx.send(f"Loner group **{group_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT player_name
        FROM loner_group_members
        WHERE guild_id = %s AND faction = %s AND group_name = %s
        """,
        (guildId, factionName, group_name)
    )

    members = cursor.fetchall()

    if not members:
        cursor.close()
        db.close()
        await ctx.send(f"Loner group **{group_name}** has no members.")
        return

    questIds = []

    for member in members:
        playerName = member["player_name"]

        cursor.execute(
            """
            INSERT INTO quests (guild_id, faction, title, description, created_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                guildId,
                factionName,
                quest,
                f"{playerName} | Group: {group_name}. {notes}",
                ctx.author.id
            )
        )

        questIds.append(str(cursor.lastrowid))

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(
        f"**Group Quest Assigned**\n"
        f"Group: **{group_name}**\n"
        f"Faction: **{factionName}**\n"
        f"Quest: **{quest}**\n"
        f"Members Assigned: **{len(members)}**\n"
        f"Quest IDs: `{', '.join(questIds)}`"
    )

@bot.command()
async def questgiverewardlonergroup(ctx, group_name: str, quest: str, reward: str, reputation: int):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    if not lonerGroupExists(guildId, factionName, group_name):
        await ctx.send(f"Loner group **{group_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT player_name
        FROM loner_group_members
        WHERE guild_id = %s AND faction = %s AND group_name = %s
        """,
        (guildId, factionName, group_name)
    )

    members = cursor.fetchall()

    if not members:
        cursor.close()
        db.close()
        await ctx.send(f"Loner group **{group_name}** has no members.")
        return

    completedCount = 0

    for member in members:
        playerName = member["player_name"]

        cursor.execute(
            """
            DELETE FROM quests
            WHERE guild_id = %s
            AND faction = %s
            AND title = %s
            AND description LIKE %s
            """,
            (guildId, factionName, quest, f"{playerName} | Group: {group_name}.%")
        )

        if cursor.rowcount > 0:
            completedCount += cursor.rowcount

            cursor.execute(
                """
                UPDATE player_stats
                SET reputation = reputation + %s,
                    numQuestsCompleted = numQuestsCompleted + 1
                WHERE guild_id = %s AND faction = %s AND player_name = %s
                """,
                (reputation, guildId, factionName, playerName)
            )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(
        f"**Group Quest Reward Given**\n"
        f"Group: **{group_name}**\n"
        f"Quest: **{quest}**\n"
        f"Reward: **{reward}**\n"
        f"Reputation Gained Per Loner: **{reputation}**\n"
        f"Completed Quest Records Removed: **{completedCount}**"
    )

@bot.command()
async def questshowall(ctx):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, title, description, created_at
        FROM quests
        WHERE guild_id = %s
        AND faction = %s
        ORDER BY created_at DESC
        """,
        (guildId, factionName)
    )

    quests = cursor.fetchall()
    cursor.close()
    db.close()

    if not quests:
        await ctx.send(f"No active quests found for **{factionName}**.")
        return

    message = f"**All active quests for {factionName}**\n\n"

    for quest in quests:
        description = quest["description"] or ""

        if " | Group: " in description:
            playerName, groupInfo = description.split(" | Group: ", 1)

            if ". " in groupInfo:
                groupName, notes = groupInfo.split(". ", 1)
            else:
                groupName, notes = groupInfo, ""

            message += (
                f"`Quest ID: {quest['id']}` — **[GROUP QUEST]**\n"
                f"Group: **{groupName}**\n"
                f"Loner: **{playerName}**\n"
                f"Task: **{quest['title']}**\n"
                f"Notes: {notes if notes else 'None'}\n\n"
            )

        elif " | " in description:
            playerName, notes = description.split(" | ", 1)

            message += (
                f"`Quest ID: {quest['id']}` — **[LONER QUEST]**\n"
                f"Loner: **{playerName}**\n"
                f"Task: **{quest['title']}**\n"
                f"Notes: {notes if notes else 'None'}\n\n"
            )

        else:
            message += (
                f"`Quest ID: {quest['id']}` — **[UNKNOWN QUEST]**\n"
                f"Task: **{quest['title']}**\n"
                f"Notes: {description if description else 'None'}\n\n"
            )

    await ctx.send(message)


@bot.command()
async def questgivereward(ctx, player_name: str, quest_id: int, reward: str, reputation: int):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    if not playerExists(guildId, factionName, player_name):
        await ctx.send(f"Player **{player_name}** not found in **{factionName}**.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, title, description
        FROM quests
        WHERE id = %s AND guild_id = %s AND faction = %s
        """,
        (quest_id, guildId, factionName)
    )

    quest = cursor.fetchone()

    if not quest:
        cursor.close()
        db.close()
        await ctx.send("Quest not found.")
        return

    if not quest["description"].startswith(f"{player_name} |"):
        cursor.close()
        db.close()
        await ctx.send(f"Quest ID `{quest_id}` does not belong to **{player_name}**.")
        return

    cursor.execute(
        """
        DELETE FROM quests
        WHERE id = %s AND guild_id = %s AND faction = %s
        """,
        (quest_id, guildId, factionName)
    )

    cursor.execute(
        """
        UPDATE player_stats
        SET reputation = reputation + %s,
            numQuestsCompleted = numQuestsCompleted + 1
        WHERE guild_id = %s AND faction = %s AND player_name = %s
        """,
        (reputation, guildId, factionName, player_name)
    )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(
        f"**Quest Completed**\n"
        f"Player: **{player_name}**\n"
        f"Quest: **{quest['title']}**\n"
        f"Reward: **{reward}**\n"
        f"Reputation Gained: **{reputation}**"
    )

@bot.command()
async def help(ctx):
    message = """
**📜 Bot Commands**

-----------------------------------------------------------------------------------------------------------------------------------------------------------------

**Faction Setup**
!setupfaction [Faction] 
 → Assign this server to a faction. Admin only.
!faction 
 → Show this server's assigned faction.

-----------------------------------------------------------------------------------------------------------------------------------------------------------------

**Players**
!loneradd "Loner Name" 
 → Add a loner to your faction database.
!lonerremove "Loner Name" 
 → Remove a loner from your faction database.

!lonerstatus "Loner Name" 
 → Show status, completed quests, and reputation.

!lonereditstatus "Loner Name" [Status]
 → Change a loner's status to:
     - Hostile, Untrustworthy, Neutral, Known, Trustworthy, Respected.

-----------------------------------------------------------------------------------------------------------------------------------------------------------------

**Loner Groups**
!lonergroupcreate "Group Name"
 → Create a loner group for your faction.

!lonergroupmemberadd "Group Name" "Loner Name"
 → Add a loner to a group.

!lonergroupmemberremove "Group Name" "Loner Name"
 → Remove a loner from a group.

!lonergroupstatus "Group Name"
 → Show a loner group's status and members.

!lonergroupeditstatus "Group Name" [Status]
 → Change a loner group's status to:
     - Hostile, Untrustworthy, Neutral, Known, Trustworthy, Respected.

-----------------------------------------------------------------------------------------------------------------------------------------------------------------

**Quests**
IMPORTANT: Make sure to add the loner's name to the database before assigning or retrieving quests.

!questgive "Loner Name" "Quest Title" [notes]
 → Assign a quest to an existing loner.

!questshowplayer "Loner Name"
 → Show active quests for a chosen loner.

!questshowall 
 → Show all active quests for your faction.

!questgivereward "Loner Name" [quest_id] "Reward" [reputation]
 → Complete a quest and grant rewards/reputation.

-----------------------------------------------------------------------------------------------------------------------------------------------------------------

**Group Quests**
!questgivelonergroup "Group Name" "Quest Title" [notes]
 → Assign a quest to every loner in a group.

!questgiverewardlonergroup "Group Name" "Quest Title" "Reward" [reputation]
 → Complete a group quest and reward every group member.

-----------------------------------------------------------------------------------------------------------------------------------------------------------------

**Utility**
!ping 
 → Check if bot is alive.

-----------------------------------------------------------------------------------------------------------------------------------------------------------------
"""
    await ctx.send(message)
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing input. Use `!help` to see the correct command format.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid input type. Check numbers and use quotes around multi-word names, groups, quests, or rewards.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        await ctx.send("An unexpected error occurred.")
        raise error

bot.run(token)
