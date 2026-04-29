import os
import discord
import mysql.connector
from discord.ext import commands

token = os.getenv("DISCORD_TOKEN")

if not token:
    raise ValueError("DISCORD_TOKEN environment variable is missing.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


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


@bot.command()
@commands.has_permissions(administrator=True)
async def setupfaction(ctx, faction: str):
    allowedFactions = ["Freedom", "Duty", "Bandits", "EcoMili"]

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


@bot.command()
async def faction(ctx):
    factionName = getFactionForGuild(ctx.guild.id)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    await ctx.send(f"This server is assigned to: **{factionName}**")


@bot.command()
async def questgive(ctx, title: str, *, description: str = ""):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet. An admin must use `!setupfaction` first.")
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
            title,
            description,
            ctx.author.id
        )
    )

    db.commit()
    questId = cursor.lastrowid

    cursor.close()
    db.close()

    await ctx.send(
        f"Quest created for **{factionName}**.\n"
        f"Quest ID: `{questId}`\n"
        f"Title: **{title}**"
    )


@bot.command()
async def quests(ctx):
    guildId = ctx.guild.id
    factionName = getFactionForGuild(guildId)

    if not factionName:
        await ctx.send("This server has not been assigned to a faction yet.")
        return

    db = getDbConnection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, title, description
        FROM quests
        WHERE guild_id = %s
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (guildId,)
    )

    rows = cursor.fetchall()

    cursor.close()
    db.close()

    if not rows:
        await ctx.send(f"No quests found for **{factionName}**.")
        return

    message = f"Recent quests for **{factionName}**:\n\n"

    for quest in rows:
        message += f"`{quest['id']}` — **{quest['title']}**\n"
        if quest["description"]:
            message += f"{quest['description']}\n"
        message += "\n"

    await ctx.send(message)


bot.run(token)
