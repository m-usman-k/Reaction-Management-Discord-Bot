import discord
from discord import app_commands
from discord.ext import tasks
import csv
import os
import datetime
import asyncio
from typing import Dict, List, Tuple, Optional
from config import BOT_TOKEN

# Initialize Discord client with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

class PointsBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = PointsBot()

# File paths for data storage
POINTS_FILE = 'data/points.csv'
SETTINGS_FILE = 'data/settings.csv'
WPT_MESSAGES_FILE = 'data/wpt_messages.csv'

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# CSV file structure
def ensure_csv_files():
    """Create CSV files with headers if they don't exist"""
    files_and_headers = {
        POINTS_FILE: ['user_id', 'points'],
        SETTINGS_FILE: ['key', 'value'],
        WPT_MESSAGES_FILE: ['message_id', 'channel_id', 'expiration', 'emoji_points']
    }
    
    for file_path, headers in files_and_headers.items():
        if not os.path.exists(file_path):
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

# Data management functions
def get_setting(key: str) -> Optional[str]:
    """Retrieve a setting value from settings.csv"""
    try:
        with open(SETTINGS_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['key'] == key:
                    return row['value']
    except FileNotFoundError:
        ensure_csv_files()
    return None

def set_setting(key: str, value: str) -> None:
    """Save or update a setting in settings.csv"""
    rows = []
    updated = False
    
    try:
        with open(SETTINGS_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        for row in rows:
            if row['key'] == key:
                row['value'] = value
                updated = True
                break
                
        if not updated:
            rows.append({'key': key, 'value': value})
            
        with open(SETTINGS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['key', 'value'])
            writer.writeheader()
            writer.writerows(rows)
    except FileNotFoundError:
        ensure_csv_files()
        set_setting(key, value)

def get_user_points(user_id: int) -> int:
    """Get points for a specific user"""
    try:
        with open(POINTS_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if int(row['user_id']) == user_id:
                    return int(row['points'])
    except FileNotFoundError:
        ensure_csv_files()
    return 0

def update_user_points(user_id: int, points: int) -> None:
    """Update or set points for a user"""
    rows = []
    updated = False
    
    try:
        with open(POINTS_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        for row in rows:
            if int(row['user_id']) == user_id:
                row['points'] = str(points)
                updated = True
                break
        
        if not updated:
            rows.append({'user_id': str(user_id), 'points': str(points)})
        
        with open(POINTS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['user_id', 'points'])
            writer.writeheader()
            writer.writerows(rows)
    except FileNotFoundError:
        ensure_csv_files()
        update_user_points(user_id, points)

# Role checking
def has_required_role():
    """Check if user has the required role for command execution"""
    async def predicate(interaction: discord.Interaction) -> bool:
        required_role_id = get_setting('required_role')
        if not required_role_id:
            return True
        
        try:
            required_role_id = int(required_role_id)
            return any(role.id == required_role_id for role in interaction.user.roles)
        except (ValueError, AttributeError):
            return False
    
    return app_commands.check(predicate)

# Command error handling
class CommandError(Exception):
    """Base exception for command errors"""
    pass

# Slash Commands
@bot.tree.command(name="createwpt", description="Create a WPT message with reactions for points")
@app_commands.describe(
    channel="The channel to post the message in",
    title="The title of the message",
    message="The content of the message",
    emoji_points="Format: emoji:points,emoji:points (e.g., 👍:5,❤️:10)",
    expiration="Time until expiration in hours (e.g., 24)"
)
@has_required_role()
async def createwpt(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    message: str,
    emoji_points: str,
    expiration: int
):
    try:
        # Parse emoji:points pairs
        emoji_dict = {}
        for pair in emoji_points.split(','):
            emoji, points = pair.split(':')
            emoji_dict[emoji.strip()] = int(points)

        # Create embed
        embed = discord.Embed(
            title=title,
            description=message,
            color=discord.Color.blue()
        )
        
        # Add expiration time
        expiration_time = datetime.datetime.now() + datetime.timedelta(hours=expiration)
        embed.add_field(
            name="Expires",
            value=f"<t:{int(expiration_time.timestamp())}:R>",
            inline=False
        )
        
        # Add point values
        for emoji, points in emoji_dict.items():
            embed.add_field(name=emoji, value=f"{points} points", inline=True)
        
        # Send message and add reactions
        sent_message = await channel.send(embed=embed)
        for emoji in emoji_dict.keys():
            await sent_message.add_reaction(emoji)
        
        # Store message info
        with open(WPT_MESSAGES_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                sent_message.id,
                channel.id,
                expiration_time.isoformat(),
                emoji_points
            ])
        
        await interaction.response.send_message(
            f"WPT message created in {channel.mention}",
            ephemeral=True
        )
        
    except Exception as e:
        await interaction.response.send_message(
            f"Error creating WPT message: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="pointset", description="Manually modify user points")
@app_commands.describe(
    user="The user to modify points for",
    value="The number of points to add or remove",
    reason="The reason for the point adjustment"
)
@has_required_role()
async def pointset(
    interaction: discord.Interaction,
    user: discord.Member,
    value: int,
    reason: str
):
    try:
        current_points = get_user_points(user.id)
        new_points = current_points + value
        update_user_points(user.id, new_points)
        
        # Log the adjustment if a reason channel is set
        reason_channel_id = get_setting('reason_channel')
        if reason_channel_id:
            try:
                reason_channel = await bot.fetch_channel(int(reason_channel_id))
                await reason_channel.send(
                    f"🔄 Point Adjustment:\n"
                    f"• Moderator: {interaction.user.mention}\n"
                    f"• User: {user.mention}\n"
                    f"• Change: {value:+d} points\n"
                    f"• New Total: {new_points}\n"
                    f"• Reason: {reason}"
                )
            except Exception as e:
                await interaction.followup.send(
                    f"Warning: Could not log to reason channel: {str(e)}",
                    ephemeral=True
                )
        
        await interaction.response.send_message(
            f"Updated {user.mention}'s points from {current_points} to {new_points}",
            ephemeral=True
        )
        
    except Exception as e:
        await interaction.response.send_message(
            f"Error adjusting points: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="setrole", description="Set the required role for using bot commands")
@app_commands.describe(role="The role to set as required")
async def setrole(interaction: discord.Interaction, role: discord.Role):
    try:
        set_setting('required_role', str(role.id))
        await interaction.response.send_message(
            f"Required role set to {role.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error setting required role: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="setreasonchannel", description="Set the channel for logging point adjustments")
@app_commands.describe(channel="The channel to use for logging")
async def setreasonchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        set_setting('reason_channel', str(channel.id))
        await interaction.response.send_message(
            f"Reason channel set to {channel.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error setting reason channel: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="points", description="Display your current points balance")
async def points(interaction: discord.Interaction):
    try:
        points = get_user_points(interaction.user.id)
        await interaction.response.send_message(
            f"You have {points} points",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Error retrieving points: {str(e)}",
            ephemeral=True
        )

# Event Handlers
@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    if user.bot:
        return
        
    try:
        message_data = None
        with open(WPT_MESSAGES_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if int(row['message_id']) == reaction.message.id:
                    message_data = row
                    break
        
        if message_data:
            emoji_points = dict(
                pair.split(':')
                for pair in message_data['emoji_points'].split(',')
            )
            
            
            
            if str(reaction.emoji) in emoji_points:
                points_to_add = int(emoji_points[str(reaction.emoji)])
                current_points = get_user_points(user.id)
                update_user_points(user.id, current_points + points_to_add)
                
    except Exception as e:
        print(f"Error processing reaction: {str(e)}")

@bot.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
    if user.bot:
        return
        
    try:
        message_data = None
        with open(WPT_MESSAGES_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if int(row['message_id']) == reaction.message.id:
                    message_data = row
                    break
        
        if message_data:
            emoji_points = dict(
                pair.split(':')
                for pair in message_data['emoji_points'].split(',')
            )
            
            if str(reaction.emoji) in emoji_points:
                points_to_remove = int(emoji_points[str(reaction.emoji)])
                current_points = get_user_points(user.id)
                update_user_points(user.id, current_points - points_to_remove)
                
    except Exception as e:
        print(f"Error processing reaction removal: {str(e)}")

@tasks.loop(minutes=5)
async def check_expirations():
    try:
        now = datetime.datetime.now()
        expired_messages = []
        active_messages = []
        
        with open(WPT_MESSAGES_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                expiration = datetime.datetime.fromisoformat(row['expiration'])
                if expiration <= now:
                    expired_messages.append((int(row['message_id']), int(row['channel_id'])))
                else:
                    active_messages.append(row)
        
        for message_id, channel_id in expired_messages:
            try:
                channel = await bot.fetch_channel(channel_id)
                message = await channel.fetch_message(message_id)
                await message.delete()
            except:
                pass  # Message or channel may no longer exist
        
        with open(WPT_MESSAGES_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['message_id', 'channel_id', 'expiration', 'emoji_points'])
            writer.writeheader()
            writer.writerows(active_messages)
            
    except Exception as e:
        print(f"Error checking expirations: {str(e)}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.tree.sync()
    check_expirations.start()
    print('Bot is ready!')

# Run the bot
if __name__ == "__main__":
    ensure_csv_files()
    bot.run(BOT_TOKEN)

