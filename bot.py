import os
import discord
import mysql.connector
from discord.ext import commands

# Retrieve token
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

    if result:
        return result["faction"]

    return None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

#Sets what faction the discord is using.
@bot.command()
@commands.has_permissions(administrator=True)
async def setupfaction(ctx, faction: str):
    allowedFactions = ["Freedom", "Duty", "Bandit", "Ecologist", "Military", "Test"]

    if faction not in allowedFactions:
        await ctx.send(
            f"Invalid faction. Use one of: {', '.join(allowedFactions)}"
        )
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

# Allows the user to check what faction is assigned to the discord.
@bot.command()
async def faction(ctx):
    factionName = getFactionForGuild(ctx.guild.id)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    await ctx.send(f"This server is assigned to: **{factionName}**")

#Allows a factioner to give a quest to a player, and add notes.
@bot.command()
async def questgive(ctx, player_name: str, quest: str, *, notes: str = ""):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet. Use `!setupfaction` first.")
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

# Shows all quests given for a specific player by the faction.
@bot.command()
async def questshowplayer(ctx, player_name: str):
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
        AND description LIKE %s
        ORDER BY created_at DESC
        """,
        (guildId, factionName, f"{player_name} |%")
    )

    quests = cursor.fetchall()
    cursor.close()
    db.close()

    if not quests:
        await ctx.send(f"No quests found for **{player_name}**.")
        return

    message = f"**Quests for {player_name} — {factionName}**\n\n"

    for quest in quests:
        notes = quest["description"].split(" | ", 1)[1] if " | " in quest["description"] else quest["description"]
        message += f"`{quest['id']}` — **{quest['title']}**\nNotes: {notes}\n\n"

    await ctx.send(message)

# Allows a factioner to see all the quests given out by the faction.
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
        await ctx.send(f"No quests found for **{factionName}**.")
        return

    message = f"**All quests for {factionName}**\n\n"

    for quest in quests:
        description = quest["description"] or ""
        if " | " in description:
            playerName, notes = description.split(" | ", 1)
        else:
            playerName, notes = "Unknown", description

        message += f"`{quest['id']}` — **{playerName}**: {quest['title']}\nNotes: {notes}\n\n"

    await ctx.send(message)

# Allows a factioner to reward any player for completing a quest, and given them reputation for doing so.
@bot.command()
async def questgivereward(ctx, player_name: str, quest_id: int, reward: str, reputation: int):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    # Check that quest exists
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

    # Remove quest from active quests
    cursor.execute(
        """
        DELETE FROM quests
        WHERE id = %s AND guild_id = %s AND faction = %s
        """,
        (quest_id, guildId, factionName)
    )

    # Add/update player stats
    cursor.execute(
        """
        INSERT INTO player_stats (
            guild_id,
            faction,
            player_name,
            reputation,
            numQuestsCompleted
        )
        VALUES (%s, %s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE
            reputation = reputation + VALUES(reputation),
            numQuestsCompleted = numQuestsCompleted + 1
        """,
        (guildId, factionName, player_name, reputation)
    )

    db.commit()
    cursor.close()
    db.close()

    await ctx.send(
        f"**Quest Completed**\n"
        f"Player: **{player_name}**\n"
        f"Quest: **{quest['title']}**\n"
        f"Reward: **{reward}**\n"
        f"Reputation Gained: **{reputation}**\n"
        f"Total completed quests increased by 1."
    )

# Allows a factioner to check how many quests a player has completed.
@bot.command()
async def questnumbercompleted(ctx, player_name: str):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT reputation, numQuestsCompleted
        FROM player_stats
        WHERE guild_id = %s AND faction = %s AND player_name = %s
        """,
        (guildId, factionName, player_name)
    )

    stats = cursor.fetchone()

    cursor.close()
    db.close()

    if not stats:
        await ctx.send(f"No completed quest data found for **{player_name}**.")
        return

    await ctx.send(
        f"**{player_name} Stats**\n"
        f"Completed Quests: **{stats['numQuestsCompleted']}**\n"
        f"Reputation: **{stats['reputation']}**"
    )

# Help command
@bot.command()
async def help(ctx):
    message = """
**📜 Bot Commands**

**Faction Setup**
!setupfaction [Faction] — Assign this server to a faction (Admin only)
!faction — Show this server's faction

**Quests**
!questgive "Player Name" "Quest Title" [notes]  
→ Assign a quest to a player

Example:
!questgive "Stalker Ivan" "Artifact Hunt" Retrieve a Night Star from Agroprom

!quests — Show recent quests  
!questshowplayer "Player Name" — Show all quests for a specific player  
!questshowall — Show all quests for this faction  

**Quest Completion**
!questgivereward "Player Name" [quest_id] "Reward" [reputation]  
→ Complete a quest, remove it, give reward, and add reputation  

Example:
!questgivereward "Stalker Ivan" 4 "3000 RU and medkit" 10

!questnumbercompleted "Player Name"  
→ Show completed quest count and total reputation  

**Utility**
!ping — Check if bot is alive  
!hello — Say hello  
"""
    await ctx.send(message)
