import discord
from discord.ext import commands
import asyncio
from datetime import datetime

# Configuration - HARDCODED VALUES
BOT_OWNER_ID = 842832497044881438  # REPLACE WITH YOUR DISCORD USER ID

class DMForwarding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner = None
        # Store message tracking
        self.pending_messages = {}  # {message_id: message_info}
        self.pending_invitations = {}  # {invitation_msg_id: invitation_info}
        self.authorized_users = {}  # {target_user_id: set(authorized_user_ids)}
        self.conversation_history = {}  # {target_user_id: list(messages)}

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
            await self.handle_authorized_user_reply(message)

    async def forward_message_to_authorized_users(self, message):
        """Forward a message to all authorized users for a conversation"""
        target_user = message.author
        
        # Create an embed with the user's message
        embed = discord.Embed(
            title=f"📩 DM from {message.author}",
            description=message.content,
            color=discord.Color.blue(),
            timestamp=message.created_at
        )
        embed.set_footer(text=f"User ID: {message.author.id}")
        
        # Add any attachments
        if message.attachments:
            attachment_urls = "\n".join([attachment.url for attachment in message.attachments])
            embed.add_field(name="Attachments", value=attachment_urls, inline=False)
        
        # Store in conversation history
        if target_user.id not in self.conversation_history:
            self.conversation_history[target_user.id] = []
        
        self.conversation_history[target_user.id].append({
            "sender": target_user.id,
            "content": message.content,
            "timestamp": datetime.now(),
            "attachments": [a.url for a in message.attachments],
            "type": "incoming"
        })
        
        # Send to owner with different color for authorized users
        try:
            owner_msg = await self.owner.send(embed=embed)
            await owner_msg.add_reaction("👥")  # Manage users
            await owner_msg.add_reaction("❌")  # Reject
            
            self.pending_messages[owner_msg.id] = {
                "type": "forwarded_message",
                "target_user": target_user,
                "original_embed": embed,
                "confirmation_message": None
            }
        except discord.Forbidden:
            print("Error: Cannot send messages to the owner. The owner might have DMs disabled.")
        
        # Send to authorized users for this conversation with different color
        if target_user.id in self.authorized_users:
            for user_id in self.authorized_users[target_user.id]:
                try:
                    user = await self.bot.fetch_user(user_id)
                    
                    # Create a different colored embed for authorized users
                    auth_embed = discord.Embed(
                        title=f"📩 DM from {message.author} (Shared)",
                        description=message.content,
                        color=discord.Color.purple(),  # Different color
                        timestamp=message.created_at
                    )
                    auth_embed.set_footer(text=f"User ID: {message.author.id}")
                    
                    if message.attachments:
                        attachment_urls = "\n".join([attachment.url for attachment in message.attachments])
                        auth_embed.add_field(name="Attachments", value=attachment_urls, inline=False)
                    
                    user_msg = await user.send(embed=auth_embed)
                    
                    self.pending_messages[user_msg.id] = {
                        "type": "forwarded_message",
                        "target_user": target_user,
                        "responder": user
                    }
                except discord.Forbidden:
                    print(f"Error: Cannot send messages to user {user_id}.")

    async def handle_authorized_user_reply(self, message):
        """Handle replies from authorized users to forwarded messages"""
        original_msg_id = message.reference.message_id
        
        if original_msg_id in self.pending_messages:
            message_info = self.pending_messages[original_msg_id]
            
            if message_info["type"] == "forwarded_message":
                target_user = message_info["target_user"]
                responder = message.author
                
                try:
                    # Send the response to the user with clear identification
                    response_embed = discord.Embed(
                        title=f"💬 Response from {responder.name}",
                        description=message.content,
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    
                    if responder.id == BOT_OWNER_ID:
                        response_embed.set_author(name="Bot Owner")
                    else:
                        response_embed.set_author(name="Authorized Assistant")
                    
                    await target_user.send(embed=response_embed)
                    
                    # Also send to owner if the responder is not the owner
                    if responder.id != BOT_OWNER_ID:
                        owner_notification = discord.Embed(
                            title=f"📤 {responder.name} responded to {target_user.name}",
                            description=message.content,
                            color=discord.Color.orange(),  # Different color for authorized user responses
                            timestamp=datetime.now()
                        )
                        await self.owner.send(embed=owner_notification)
                    
                    # Store in conversation history
                    if target_user.id not in self.conversation_history:
                        self.conversation_history[target_user.id] = []
                    
                    self.conversation_history[target_user.id].append({
                        "sender": responder.id,
                        "content": message.content,
                        "timestamp": datetime.now(),
                        "responder_name": responder.name,
                        "type": "outgoing"
                    })
                    
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to DM this user.")
                except Exception as e:
                    await message.channel.send(f"An error occurred: {e}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # Ignore bot's own reactions
        if user == self.bot.user:
            return
            
        # Handle reactions on forwarded messages
        if reaction.message.id in self.pending_messages:
            message_info = self.pending_messages[reaction.message.id]
            
            if message_info["type"] == "forwarded_message":
                await self.handle_forwarded_message_reaction(reaction, user, message_info)
                
        # Handle reactions on invitation messages
        elif reaction.message.id in self.pending_invitations:
            await self.handle_invitation_reaction(reaction, user)

    async def handle_forwarded_message_reaction(self, reaction, user, message_info):
        """Handle reactions on forwarded messages"""
        target_user = message_info["target_user"]
        
        if str(reaction.emoji) == "❌" and user.id == BOT_OWNER_ID:
            # Owner wants to reject the message
            await self.handle_rejection(reaction, target_user, message_info)
                
        elif str(reaction.emoji) == "👥" and user.id == BOT_OWNER_ID:
            # Owner wants to manage users for this conversation
            await self.show_user_management(reaction, target_user)

    async def handle_invitation_reaction(self, reaction, user):
        """Handle reactions on invitation messages"""
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

    async def handle_rejection(self, reaction, target_user, message_info):
        """Handle message rejection by owner"""
        # Delete all related messages
        try:
            await reaction.message.delete()
            if message_info.get("confirmation_message"):
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

    async def show_user_management(self, reaction, target_user):
        """Show user management options for a conversation"""
        try:
            await reaction.message.clear_reactions()
        except:
            pass
        
        # Create management embed
        management_embed = discord.Embed(
            title=f"👥 User Management for {target_user.name}",
            description="Manage who can respond to this user's messages",
            color=discord.Color.gold()
        )
        
        # List authorized users
        authorized_users = self.authorized_users.get(target_user.id, set())
        if authorized_users:
            users_list = []
            for user_id in authorized_users:
                try:
                    user_obj = await self.bot.fetch_user(user_id)
                    users_list.append(f"{user_obj.name} (ID: {user_id})")
                except:
                    users_list.append(f"Unknown User (ID: {user_id})")
            
            management_embed.add_field(
                name="Authorized Users",
                value="\n".join(users_list) or "No users authorized",
                inline=False
            )
        else:
            management_embed.add_field(
                name="Authorized Users",
                value="No users authorized yet",
                inline=False
            )
        
        # Add conversation stats
        history_count = len(self.conversation_history.get(target_user.id, []))
        management_embed.add_field(
            name="Conversation Stats",
            value=f"{history_count} messages in history",
            inline=False
        )
        
        # Send management message
        management_msg = await self.owner.send(embed=management_embed)
        
        # Add reactions for management options
        await management_msg.add_reaction("👤")  # Add user
        await management_msg.add_reaction("🚫")  # Remove user
        await management_msg.add_reaction("📜")  # View history
        await management_msg.add_reaction("❌")  # Close
        
        # Store management message info
        self.pending_messages[management_msg.id] = {
            "type": "user_management",
            "target_user": target_user
        }

    async def invite_new_user(self, target_user):
        """Invite a new user to the conversation"""
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
            invitation_embed = discord.Embed(
                title="📨 Conversation Invitation",
                description=(
                    f"You have been invited to join a conversation with {target_user.name} (ID: {target_user.id}).\n\n"
                    f"**If you accept:**\n"
                    f"- You will receive all messages from this user\n"
                    f"- You can respond to them by replying to the messages\n"
                    f"- The bot owner can remove you at any time\n\n"
                    f"React with ✅ to accept or ❌ to decline."
                ),
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            invitation_msg = await invited_user.send(embed=invitation_embed)
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

    async def remove_user(self, target_user, user_id_to_remove):
        """Remove a user from a conversation"""
        try:
            # Remove from authorized users
            if target_user.id in self.authorized_users and user_id_to_remove in self.authorized_users[target_user.id]:
                self.authorized_users[target_user.id].remove(user_id_to_remove)
                
                # Get the user object for the removed user
                removed_user = await self.bot.fetch_user(user_id_to_remove)
                
                # Notify the removed user
                try:
                    await removed_user.send(f"You have been removed from the conversation with {target_user.name}.")
                except:
                    pass
                
                # Send confirmation to owner
                await self.owner.send(f"User {removed_user.name} has been successfully removed from the conversation with {target_user.name}.")
                
                return True
            else:
                await self.owner.send("This user is not authorized for this conversation.")
                return False
                
        except Exception as e:
            await self.owner.send(f"An error occurred while removing the user: {e}")
            return False

    async def show_remove_user_options(self, target_user):
        """Show options for removing users from a conversation"""
        authorized_users = self.authorized_users.get(target_user.id, set())
        
        if not authorized_users:
            no_users_embed = discord.Embed(
                title="No Users to Remove",
                description="There are no authorized users for this conversation.",
                color=discord.Color.red()
            )
            await self.owner.send(embed=no_users_embed)
            return
        
        # Create remove user embed
        remove_embed = discord.Embed(
            title=f"🚫 Remove User from {target_user.name}'s Conversation",
            description="Please provide the user ID to remove from this conversation:",
            color=discord.Color.red()
        )
        
        # List authorized users
        users_list = []
        for user_id in authorized_users:
            try:
                user_obj = await self.bot.fetch_user(user_id)
                users_list.append(f"{user_obj.name} (ID: {user_id})")
            except:
                users_list.append(f"Unknown User (ID: {user_id})")
        
        remove_embed.add_field(
            name="Authorized Users",
            value="\n".join(users_list),
            inline=False
        )
        
        # Send remove options message
        await self.owner.send(embed=remove_embed)
        
        # Ask for user ID to remove
        ask_msg = await self.owner.send("Please provide the ID of the user you want to remove:")
        
        def check(m):
            return m.author.id == BOT_OWNER_ID and m.channel == ask_msg.channel
        
        try:
            # Wait for user ID
            response = await self.bot.wait_for('message', timeout=60.0, check=check)
            user_id = int(response.content)
            
            # Remove the user
            success = await self.remove_user(target_user, user_id)
            
            if success:
                # Show management menu again
                await self.show_user_management(None, target_user)
            
        except asyncio.TimeoutError:
            await self.owner.send("Timed out waiting for user ID.")
        except ValueError:
            await self.owner.send("Invalid user ID. Please provide a numeric user ID.")
        except Exception as e:
            await self.owner.send(f"An error occurred: {e}")

    async def show_conversation_history(self, target_user):
        """Show conversation history for a user"""
        history = self.conversation_history.get(target_user.id, [])
        
        if not history:
            no_history_embed = discord.Embed(
                title="No Conversation History",
                description="There is no history for this conversation yet.",
                color=discord.Color.blue()
            )
            await self.owner.send(embed=no_history_embed)
            return
        
        # Create history embed
        history_embed = discord.Embed(
            title=f"📜 Conversation History with {target_user.name}",
            description=f"Total messages: {len(history)}",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        # Add last 10 messages to history
        recent_messages = history[-10:]
        for msg in recent_messages:
            try:
                sender = await self.bot.fetch_user(msg["sender"])
                sender_name = sender.name
            except:
                sender_name = f"User {msg['sender']}"
            
            # Format timestamp
            time_str = msg["timestamp"].strftime("%Y-%m-%d %H:%M")
            
            # Determine message direction
            direction = "➡️" if msg.get("type") == "outgoing" else "⬅️"
            
            history_embed.add_field(
                name=f"{direction} {sender_name} ({time_str})",
                value=msg["content"][:500] + ("..." if len(msg["content"]) > 500 else ""),
                inline=False
            )
        
        await self.owner.send(embed=history_embed)

    async def accept_invitation(self, invitation_info, reaction):
        """Handle invitation acceptance"""
        target_user = invitation_info["target_user"]
        invited_user = invitation_info["invited_user"]
        
        # Add to authorized users
        if target_user.id not in self.authorized_users:
            self.authorized_users[target_user.id] = set()
        self.authorized_users[target_user.id].add(invited_user.id)
        
        # Send conversation history if available
        if target_user.id in self.conversation_history:
            history_embed = discord.Embed(
                title=f"📜 Conversation History with {target_user.name}",
                description="Here are the recent messages from this conversation:",
                color=discord.Color.purple(),
                timestamp=datetime.now()
            )
            
            # Add last 5 messages to history
            recent_messages = self.conversation_history[target_user.id][-5:]
            for i, msg in enumerate(recent_messages):
                try:
                    sender = await self.bot.fetch_user(msg["sender"])
                    sender_name = sender.name
                except:
                    sender_name = f"User {msg['sender']}"
                
                # Determine message direction
                direction = "➡️" if msg.get("type") == "outgoing" else "⬅️"
                
                history_embed.add_field(
                    name=f"{direction} {sender_name} ({msg['timestamp'].strftime('%H:%M')})",
                    value=msg["content"][:100] + ("..." if len(msg["content"]) > 100 else ""),
                    inline=False
                )
            
            await invited_user.send(embed=history_embed)
        
        # Send success messages
        success_embed = discord.Embed(
            title="✅ Invitation Accepted",
            description=f"You have been added to the conversation with {target_user.name}.",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        success_embed.add_field(
            name="How to respond",
            value="Simply reply to any message from this user to send a response.",
            inline=False
        )
        
        await invited_user.send(embed=success_embed)
        
        # Notify owner
        owner_notification = discord.Embed(
            title="✅ User Added to Conversation",
            description=f"{invited_user.name} has accepted the invitation to join the conversation with {target_user.name}.",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        await self.owner.send(embed=owner_notification)
        
        # Update invitation message
        try:
            await reaction.message.clear_reactions()
            accepted_embed = discord.Embed(
                title="✅ Invitation Accepted",
                description="You have joined this conversation.",
                color=discord.Color.green()
            )
            await reaction.message.edit(embed=accepted_embed)
        except:
            pass

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # Ignore bot's own reactions
        if user == self.bot.user:
            return
            
        # Handle reactions on forwarded messages
        if reaction.message.id in self.pending_messages:
            message_info = self.pending_messages[reaction.message.id]
            
            if message_info["type"] == "forwarded_message":
                await self.handle_forwarded_message_reaction(reaction, user, message_info)
            elif message_info["type"] == "user_management" and user.id == BOT_OWNER_ID:
                await self.handle_management_reaction(reaction, user, message_info)
                
        # Handle reactions on invitation messages
        elif reaction.message.id in self.pending_invitations:
            await self.handle_invitation_reaction(reaction, user)

    async def handle_management_reaction(self, reaction, user, message_info):
        """Handle reactions on management messages"""
        target_user = message_info["target_user"]
        
        if str(reaction.emoji) == "👤":
            # Add a new user
            await self.invite_new_user(target_user)
        elif str(reaction.emoji) == "🚫":
            # Remove a user
            await self.show_remove_user_options(target_user)
        elif str(reaction.emoji) == "📜":
            # Show conversation history
            await self.show_conversation_history(target_user)
        elif str(reaction.emoji) == "❌":
            # Close the management menu
            await reaction.message.delete()

async def setup(bot):
    await bot.add_cog(DMForwarding(bot))
