import discord
from discord.ext import commands
import os

# Configuration
BOT_OWNER_ID = int(os.environ.get('BOT_OWNER_ID', 0))  # Get your user ID from environment variable
ALLOWED_GUILD = int(os.environ.get('ALLOWED_GUILD', 0))  # Your server ID from environment variable

class DMForwarding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.forward_channel_id = None
        self.user_message_map = {}  # Maps your messages to original users

    async def setup_forward_channel(self):
        """Setup the forwarding channel in the allowed guild"""
        guild = self.bot.get_guild(ALLOWED_GUILD)
        if not guild:
            print(f"Error: Could not find guild with ID {ALLOWED_GUILD}")
            return
            
        # Try to find an existing channel
        for channel in guild.text_channels:
            if channel.name == "bot-dm-forwarding":
                self.forward_channel_id = channel.id
                return
                
        # Create a new channel if it doesn't exist
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            new_channel = await guild.create_text_channel(
                "bot-dm-forwarding",
                overwrites=overwrites,
                reason="Channel for forwarding DMs to the bot owner"
            )
            self.forward_channel_id = new_channel.id
            await new_channel.send("This channel is for forwarding DMs sent to the bot. Reply to a message to respond to the user.")
        except discord.Forbidden:
            print("Error: Bot doesn't have permission to create channels")
        except Exception as e:
            print(f"Error creating channel: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.bot.user} has connected to Discord!')
        await self.setup_forward_channel()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
            
        # Handle DMs to the bot
        if isinstance(message.channel, discord.DMChannel):
            # Don't process commands in DMs for this cog
            if message.content.startswith(self.bot.command_prefix):
                return
                
            # Forward the DM to the designated channel
            if self.forward_channel_id:
                channel = self.bot.get_channel(self.forward_channel_id)
                if channel:
                    # Create an embed with the user's message
                    embed = discord.Embed(
                        title=f"DM from {message.author}",
                        description=message.content,
                        color=discord.Color.blue(),
                        timestamp=message.created_at
                    )
                    embed.set_footer(text=f"User ID: {message.author.id}")
                    
                    # Send the embed and store the mapping
                    forwarded_msg = await channel.send(embed=embed)
                    self.user_message_map[forwarded_msg.id] = message.author.id
                    
                    # Send a confirmation to the user
                    await message.channel.send("Your message has been forwarded to the bot owner. They will respond when available.")

        # Handle replies in the forwarding channel
        elif (message.channel.id == self.forward_channel_id and 
              message.reference and 
              message.author.id == BOT_OWNER_ID and
              not message.content.startswith(self.bot.command_prefix)):
            
            # Get the original forwarded message
            try:
                original_msg = await message.channel.fetch_message(message.reference.message_id)
                user_id = self.user_message_map.get(original_msg.id)
                
                if user_id:
                    user = await self.bot.fetch_user(user_id)
                    if user:
                        # Send the response to the user
                        await user.send(f"**Response from bot owner:**\n{message.content}")
                        await message.add_reaction("✅")  # Confirm delivery
                    else:
                        await message.channel.send("Could not find the user to respond to.")
                else:
                    await message.channel.send("This message doesn't correspond to any DM conversation.")
            except discord.NotFound:
                await message.channel.send("The referenced message was not found.")
            except discord.Forbidden:
                await message.channel.send("I don't have permission to DM this user.")
            except Exception as e:
                await message.channel.send(f"An error occurred: {e}")

async def setup(bot):
    await bot.add_cog(DMForwarding(bot))
