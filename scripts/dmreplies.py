import discord
from discord.ext import commands
import asyncio

# Configuration - HARDCODED VALUES
BOT_OWNER_ID = 842832497044881438  # REPLACE WITH YOUR DISCORD USER ID

class DMForwarding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner = None
        self.pending_messages = {}  # {message_id: {target_user, original_embed, confirmation_message}}
        self.pending_responses = {}  # {message_id: {target_user, responder}}
        self.authorized_users = {}  # {target_user_id: set(authorized_user_ids)}
        self.user_conversations = {}  # {target_user_id: {authorized_user_id: conversation_messages}}
        self.pending_invitations = {}  # {invitation_msg_id: {target_user, invited_user}}

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
                
            # Forward the DM to the owner and authorized users
            await self.forward_message_to_authorized_users(message)
                
        # Handle replies from authorized users
        elif (isinstance(message.channel, discord.DMChannel) and 
              message.reference and
              not message.content.startswith(self.bot.command_prefix)):
            
            # Check if the message is a reply to a forwarded message
            original_msg_id = message.reference.message_id
            
            if original_msg_id in self.pending_responses:
                response_info = self.pending_responses[original_msg_id]
                target_user = response_info["target_user"]
                responder = response_info["responder"]
                
                try:
                    # Send the response to the user
                    await target_user.send(f"**Response from {responder.name}:**\n{message.content}")
                    await message.add_reaction("✅")  # Confirm delivery
                    
                    # Store the message in conversation history
                    if target_user.id not in self.user_conversations:
                        self.user_conversations[target_user.id] = {}
                    
                    if responder.id not in self.user_conversations[target_user.id]:
                        self.user_conversations[target_user.id][responder.id] = []
                    
                    self.user_conversations[target_user.id][responder.id].append({
                        "from": responder.id,
                        "content": message.content,
                        "timestamp": message.created_at
                    })
                    
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to DM this user.")
                except Exception as e:
                    await message.channel.send(f"An error occurred: {e}")

    async def forward_message_to_authorized_users(self, message):
        """Forward a message to all authorized users for a conversation"""
        target_user = message.author
        
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
        
        # Send to owner
        try:
            owner_msg = await self.owner.send(embed=embed)
            await owner_msg.add_reaction("✅")  # Accept
            await owner_msg.add_reaction("👤")  # Add user
            await owner_msg.add_reaction("❌")  # Reject
            
            self.pending_messages[owner_msg.id] = {
                "target_user": target_user,
                "original_embed": embed,
                "confirmation_message": None
            }
            
            # Store for response tracking
            self.pending_responses[owner_msg.id] = {
                "target_user": target_user,
                "responder": self.owner
            }
        except discord.Forbidden:
            print("Error: Cannot send messages to the owner. The owner might have DMs disabled.")
        
        # Send to authorized users for this conversation
        if target_user.id in self.authorized_users:
            for user_id in self.authorized_users[target_user.id]:
                try:
                    user = await self.bot.fetch_user(user_id)
                    user_msg = await user.send(embed=embed)
                    await user_msg.add_reaction("✅")  # Accept (send response)
                    await user_msg.add_reaction("🚫")  # Remove self from conversation
                    
                    # Store for response tracking
                    self.pending_responses[user_msg.id] = {
                        "target_user": target_user,
                        "responder": user
                    }
                except discord.Forbidden:
                    print(f"Error: Cannot send messages to user {user_id}.")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # Ignore bot's own reactions
        if user == self.bot.user:
            return
            
        # Handle reactions on forwarded messages
        if reaction.message.id in self.pending_messages and isinstance(reaction.message.channel, discord.DMChannel):
            message_info = self.pending_messages[reaction.message.id]
            target_user = message_info["target_user"]
            
            if str(reaction.emoji) == "✅" and user.id in [BOT_OWNER_ID] + list(self.authorized_users.get(target_user.id, [])):
                # User wants to respond - already handled by the reply system
                pass
                
            elif str(reaction.emoji) == "❌" and user.id == BOT_OWNER_ID:
                # Owner wants to reject the message
                await self.handle_rejection(reaction, target_user, message_info)
                
            elif str(reaction.emoji) == "👤" and user.id == BOT_OWNER_ID:
                # Owner wants to add a user
                await self.handle_add_user(reaction, target_user)
                
        # Handle reactions on invitation messages
        elif reaction.message.id in self.pending_invitations and isinstance(reaction.message.channel, discord.DMChannel):
            invitation_info = self.pending_invitations[reaction.message.id]
            target_user = invitation_info["target_user"]
            invited_user = invitation_info["invited_user"]
            
            if user.id == invited_user.id:
                if str(reaction.emoji) == "✅":
                    # User accepts invitation
                    await self.accept_invitation(invitation_info, reaction)
                elif str(reaction.emoji) == "❌":
                    # User rejects invitation
                    await invited_user.send("You have declined the invitation to join the conversation.")
                    await reaction.message.delete()
                    del self.pending_invitations[reaction.message.id]
                    
        # Handle removal reactions
        elif str(reaction.emoji) == "🚫" and isinstance(reaction.message.channel, discord.DMChannel):
            # Check if user is authorized for any conversation
            for target_id, authorized_set in self.authorized_users.items():
                if user.id in authorized_set and user.id != BOT_OWNER_ID:
                    # Remove user from authorized list
                    authorized_set.remove(user.id)
                    await user.send(f"You have been removed from the conversation with user ID {target_id}.")
                    
                    # Notify owner
                    target_user = await self.bot.fetch_user(target_id)
                    await self.owner.send(f"User {user.name} has removed themselves from the conversation with {target_user.name}.")
                    break

    async def handle_rejection(self, reaction, target_user, message_info):
        """Handle message rejection by owner"""
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
        if reaction.message.id in self.pending_responses:
            del self.pending_responses[reaction.message.id]

    async def handle_add_user(self, reaction, target_user):
        """Handle adding a new user to the conversation"""
        # Ask for user ID
        ask_msg = await self.owner.send("Please provide the user ID to authorize for this conversation.")
        
        def check(m):
            return m.author.id == BOT_OWNER_ID and m.channel == ask_msg.channel
        
        try:
            # Wait for user ID
            response = await self.bot.wait_for('message', timeout=60.0, check=check)
            user_id = int(response.content)
            
            # Get the user object
            invited_user = await self.bot.fetch_user(user_id)
            
            # Send invitation to the user
            invitation_msg = await invited_user.send(
                f"You have been invited to join a conversation with {target_user.name} (ID: {target_user.id}).\n"
                f"React with ✅ to accept or ❌ to decline.\n"
                f"If you accept, you will receive all messages from this user and can respond to them."
            )
            
            await invitation_msg.add_reaction("✅")
            await invitation_msg.add_reaction("❌")
            
            # Store invitation info
            self.pending_invitations[invitation_msg.id] = {
                "target_user": target_user,
                "invited_user": invited_user
            }
            
            await self.owner.send(f"Invitation sent to {invited_user.name}.")
            
        except asyncio.TimeoutError:
            await self.owner.send("Timed out waiting for user ID.")
        except ValueError:
            await self.owner.send("Invalid user ID. Please provide a numeric user ID.")
        except discord.NotFound:
            await self.owner.send("User not found. Please check the user ID.")
        except Exception as e:
            await self.owner.send(f"An error occurred: {e}")

    async def accept_invitation(self, invitation_info, reaction):
        """Handle invitation acceptance"""
        target_user = invitation_info["target_user"]
        invited_user = invitation_info["invited_user"]
        
        # Add to authorized users
        if target_user.id not in self.authorized_users:
            self.authorized_users[target_user.id] = set()
        self.authorized_users[target_user.id].add(invited_user.id)
        
        # Send conversation history if available
        if target_user.id in self.user_conversations:
            history_text = "**Conversation history:**\n"
            for responder_id, messages in self.user_conversations[target_user.id].items():
                responder = await self.bot.fetch_user(responder_id)
                history_text += f"\nFrom {responder.name}:\n"
                for msg in messages[-10:]:  # Last 10 messages
                    history_text += f"- {msg['content']}\n"
            
            await invited_user.send(history_text)
        
        await invited_user.send(f"You have been added to the conversation with {target_user.name}. You will now receive all their messages.")
        await self.owner.send(f"{invited_user.name} has accepted the invitation to join the conversation with {target_user.name}.")
        
        # Add remove reaction to the invitation message
        await reaction.message.add_reaction("🚫")  # Remove user
        
        # Update invitation info to include remove capability
        self.pending_invitations[reaction.message.id]["can_remove"] = True

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        """Handle removal of authorized users"""
        if (user.id == BOT_OWNER_ID and 
            reaction.message.id in self.pending_invitations and
            str(reaction.emoji) == "🚫" and
            isinstance(reaction.message.channel, discord.DMChannel)):
            
            invitation_info = self.pending_invitations[reaction.message.id]
            if "can_remove" in invitation_info and invitation_info["can_remove"]:
                invited_user = invitation_info["invited_user"]
                target_user = invitation_info["target_user"]
                
                # Remove from authorized users
                if (target_user.id in self.authorized_users and 
                    invited_user.id in self.authorized_users[target_user.id]):
                    self.authorized_users[target_user.id].remove(invited_user.id)
                
                # Send notifications
                await invited_user.send(f"You have been removed from the conversation with {target_user.name}.")
                await self.owner.send(f"{invited_user.name} has been removed from the conversation with {target_user.name}.")
                
                # Delete the message
                await reaction.message.delete()
                del self.pending_invitations[reaction.message.id]

async def setup(bot):
    await bot.add_cog(DMForwarding(bot))
