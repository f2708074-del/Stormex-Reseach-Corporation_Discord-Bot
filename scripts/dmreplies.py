import discord
from discord.ext import commands
import asyncio

# Configuration - HARDCODED VALUES
BOT_OWNER_ID = 842832497044881438  # REPLACE WITH YOUR DISCORD USER ID

class DMForwarding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner = None
        self.pending_messages = {}  # {message_id: (target_user, original_embed, confirmation_message)}
        self.authorized_users = set()  # Users authorized to respond to DMs
        self.user_conversations = {}  # {user_id: set(authorized_user_ids)}

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
                
            # Forward the DM to the owner with reaction options
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
                    
                    # Send the embed to the owner with reactions
                    forwarded_msg = await self.owner.send(embed=embed)
                    
                    # Add reactions
                    await forwarded_msg.add_reaction("✅")  # Accept
                    await forwarded_msg.add_reaction("👤")  # Add user
                    await forwarded_msg.add_reaction("❌")  # Reject
                    
                    # Store the message info
                    self.pending_messages[forwarded_msg.id] = {
                        "target_user": message.author,
                        "original_embed": embed,
                        "confirmation_message": None
                    }
                    
                except discord.Forbidden:
                    print("Error: Cannot send messages to the owner. The owner might have DMs disabled.")

        # Handle replies from authorized users
        elif (isinstance(message.channel, discord.DMChannel) and 
              message.author.id in self.authorized_users and
              message.reference):
            
            # Get the original forwarded message
            try:
                original_msg_id = message.reference.message_id
                
                # Find which user this conversation is with
                target_user_id = None
                for uid, authorized_set in self.user_conversations.items():
                    if message.author.id in authorized_set:
                        target_user_id = uid
                        break
                
                if target_user_id:
                    user = await self.bot.fetch_user(target_user_id)
                    if user:
                        # Send the response to the user
                        await user.send(f"**Response from {message.author.name}:**\n{message.content}")
                        await message.add_reaction("✅")  # Confirm delivery
                    else:
                        await message.channel.send("Could not find the user to respond to.")
                else:
                    await message.channel.send("You are not authorized to respond to any conversations.")
            except Exception as e:
                await message.channel.send(f"An error occurred: {e}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # Check if the reaction is from the owner on a forwarded message
        if (user.id == BOT_OWNER_ID and 
            reaction.message.id in self.pending_messages and
            isinstance(reaction.message.channel, discord.DMChannel)):
            
            message_info = self.pending_messages[reaction.message.id]
            target_user = message_info["target_user"]
            
            if str(reaction.emoji) == "✅":  # Accept
                # Send confirmation to the user
                confirmation = await target_user.send("Your message has been succesfully sent. Please wait a response.")
                
                # Update message info
                message_info["confirmation_message"] = confirmation
                
                # Remove reactions
                await reaction.message.clear_reactions()
                await reaction.message.add_reaction("✅")  # Keep only checkmark
                
            elif str(reaction.emoji) == "❌":  # Reject
                # Delete all related messages
                try:
                    await reaction.message.delete()
                    if message_info["confirmation_message"]:
                        await message_info["confirmation_message"].delete()
                except:
                    pass
                
                # Send rejection message to user
                try:
                    reject_msg = await target_user.send("Your message has been rejected.")
                    # Delete after 5 seconds
                    await asyncio.sleep(5)
                    await reject_msg.delete()
                except:
                    pass
                
                # Remove from pending messages
                del self.pending_messages[reaction.message.id]
                
            elif str(reaction.emoji) == "👤":  # Add user
                # Ask for user ID
                ask_msg = await self.owner.send("Please provide the user ID to authorize for this conversation.")
                
                def check(m):
                    return m.author.id == BOT_OWNER_ID and m.channel == ask_msg.channel
                
                try:
                    # Wait for user ID
                    response = await self.bot.wait_for('message', timeout=60.0, check=check)
                    user_id = int(response.content)
                    
                    # Add to authorized users
                    self.authorized_users.add(user_id)
                    
                    # Add to conversation tracking
                    if target_user.id not in self.user_conversations:
                        self.user_conversations[target_user.id] = set()
                    self.user_conversations[target_user.id].add(user_id)
                    
                    # Send success message
                    success_msg = await self.owner.send(f"User {user_id} has been authorized to respond to {target_user.name}.")
                    
                    # Add remove reaction
                    await success_msg.add_reaction("🚫")  # Remove user
                    self.pending_messages[success_msg.id] = {
                        "target_user": target_user,
                        "added_user_id": user_id
                    }
                    
                except asyncio.TimeoutError:
                    await self.owner.send("Timed out waiting for user ID.")
                except ValueError:
                    await self.owner.send("Invalid user ID. Please provide a numeric user ID.")
                except Exception as e:
                    await self.owner.send(f"An error occurred: {e}")
    
    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        # Handle removal of authorized users
        if (user.id == BOT_OWNER_ID and 
            reaction.message.id in self.pending_messages and
            str(reaction.emoji) == "🚫" and
            isinstance(reaction.message.channel, discord.DMChannel)):
            
            message_info = self.pending_messages[reaction.message.id]
            if "added_user_id" in message_info:
                user_id = message_info["added_user_id"]
                target_user = message_info["target_user"]
                
                # Remove from authorized users
                if user_id in self.authorized_users:
                    self.authorized_users.remove(user_id)
                
                # Remove from conversation tracking
                if target_user.id in self.user_conversations and user_id in self.user_conversations[target_user.id]:
                    self.user_conversations[target_user.id].remove(user_id)
                
                # Send confirmation
                await self.owner.send(f"User {user_id} has been removed from the conversation with {target_user.name}.")
                
                # Delete the message
                await reaction.message.delete()
                del self.pending_messages[reaction.message.id]

async def setup(bot):
    await bot.add_cog(DMForwarding(bot))
