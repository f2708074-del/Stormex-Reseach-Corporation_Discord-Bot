import discord
from discord.ext import commands

# Configuration - HARDCODED VALUES
BOT_OWNER_ID = 842832497044881438  # REPLACE WITH YOUR DISCORD USER ID

class DMForwarding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_message_map = {}  # Maps your messages to original users
        self.owner = None

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.bot.user} has connected to Discord!')
        # Get the owner user object
        self.owner = await self.bot.fetch_user(BOT_OWNER_ID)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
            
        # Handle DMs to the bot (global, from any user)
        if isinstance(message.channel, discord.DMChannel) and message.author != self.owner:
            # Don't process commands in DMs for this cog
            if message.content.startswith(self.bot.command_prefix):
                return
                
            # Forward the DM to the owner
            if self.owner:
                try:
                    # Create an embed with the user's message
                    embed = discord.Embed(
                        title=f"DM from {message.author}",
                        description=message.content,
                        color=discord.Color.blue(),
                        timestamp=message.created_at
                    )
                    embed.set_footer(text=f"User ID: {message.author.id}")
                    
                    # Add any attachments
                    if message.attachments:
                        attachment_urls = "\n".join([attachment.url for attachment in message.attachments])
                        embed.add_field(name="Attachments", value=attachment_urls, inline=False)
                    
                    # Send the embed to the owner and store the mapping
                    forwarded_msg = await self.owner.send(embed=embed)
                    self.user_message_map[forwarded_msg.id] = message.author.id
                    
                    # Send a confirmation to the user
                    await message.channel.send("Your message has been forwarded to the bot owner. They will respond when available.")
                except discord.Forbidden:
                    print("Error: Cannot send messages to the owner. The owner might have DMs disabled.")

        # Handle replies from the owner
        elif (isinstance(message.channel, discord.DMChannel) and 
              message.author == self.owner and
              message.reference and
              not message.content.startswith(self.bot.command_prefix)):
            
            # Get the original forwarded message
            try:
                original_msg_id = message.reference.message_id
                user_id = self.user_message_map.get(original_msg_id)
                
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
