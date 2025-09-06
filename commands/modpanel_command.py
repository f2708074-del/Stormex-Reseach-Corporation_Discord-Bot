import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime

# Configuration
ALLOWED_GUILDS = [1366203495119589536]  # Replace with your guild ID
ALLOWED_ROLES = [1366424264600719461]   # Replace with your role ID

# Permission check function
def require_roles():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return False
        
        if interaction.guild.id not in ALLOWED_GUILDS:
            await interaction.response.send_message(
                "This command is not available in this server.",
                ephemeral=True
            )
            return False
        
        member_roles = [role.id for role in interaction.user.roles]
        has_allowed_role = any(role_id in member_roles for role_id in ALLOWED_ROLES)
        
        if not has_allowed_role:
            await interaction.response.send_message(
                "You do not have the required permissions to use this command.",
                ephemeral=True
            )
            return False
            
        return True
    return app_commands.check(predicate)

# Moderation Panel Cog
class ModerationPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="moderation-panel", description="Moderation actions for server management")
    @app_commands.guilds(*ALLOWED_GUILDS)
    @require_roles()
    @app_commands.describe(
        user="The user to perform the action on",
        action="The moderation action to perform"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Kick", value="kick"),
        app_commands.Choice(name="Timeout", value="timeout"),
        app_commands.Choice(name="Add Role", value="add_role"),
        app_commands.Choice(name="Remove Role", value="remove_role"),
        app_commands.Choice(name="Purge Messages", value="purge")
    ])
    async def moderation_panel(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        action: app_commands.Choice[str]
    ):
        action_value = action.value
        
        if action_value == "ban":
            modal = BanModal(user)
            await interaction.response.send_modal(modal)
            
        elif action_value == "kick":
            modal = KickModal(user)
            await interaction.response.send_modal(modal)
            
        elif action_value == "timeout":
            modal = TimeoutModal(user)
            await interaction.response.send_modal(modal)
            
        elif action_value == "add_role":
            modal = AddRoleModal(user)
            await interaction.response.send_modal(modal)
            
        elif action_value == "remove_role":
            modal = RemoveRoleModal(user)
            await interaction.response.send_modal(modal)
            
        elif action_value == "purge":
            modal = PurgeModal()
            await interaction.response.send_modal(modal)

# Modals for different actions
class BanModal(discord.ui.Modal, title="Ban User"):
    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user
        self.reason = discord.ui.TextInput(
            label="Reason for ban",
            placeholder="Enter the reason for banning this user...",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.user.ban(reason=self.reason.value)
            await interaction.response.send_message(
                f"Successfully banned {self.user.mention} for: {self.reason.value}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to ban this user.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while executing the command: {str(e)}",
                ephemeral=True
            )

class KickModal(discord.ui.Modal, title="Kick User"):
    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user
        self.reason = discord.ui.TextInput(
            label="Reason for kick",
            placeholder="Enter the reason for kicking this user...",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.user.kick(reason=self.reason.value)
            await interaction.response.send_message(
                f"Successfully kicked {self.user.mention} for: {self.reason.value}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to kick this user.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while executing the command: {str(e)}",
                ephemeral=True
            )

class TimeoutModal(discord.ui.Modal, title="Timeout User"):
    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user
        self.duration = discord.ui.TextInput(
            label="Duration (minutes)",
            placeholder="Enter timeout duration in minutes...",
            style=discord.TextStyle.short,
            required=True
        )
        self.reason = discord.ui.TextInput(
            label="Reason for timeout",
            placeholder="Enter the reason for timing out this user...",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.duration)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration_minutes = int(self.duration.value)
            until = discord.utils.utcnow() + datetime.timedelta(minutes=duration_minutes)
            await self.user.timeout(until, reason=self.reason.value)
            await interaction.response.send_message(
                f"Successfully timed out {self.user.mention} for {duration_minutes} minutes. Reason: {self.reason.value}",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number for duration.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to timeout this user.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while executing the command: {str(e)}",
                ephemeral=True
            )

class AddRoleModal(discord.ui.Modal, title="Add Role to User"):
    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user
        self.role = discord.ui.TextInput(
            label="Role ID to add",
            placeholder="Enter the ID of the role to add...",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.role)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role.value)
            role = interaction.guild.get_role(role_id)
            if role:
                await self.user.add_roles(role)
                await interaction.response.send_message(
                    f"Successfully added {role.name} to {self.user.mention}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Role not found. Please check the role ID.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid role ID.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to add this role.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while executing the command: {str(e)}",
                ephemeral=True
            )

class RemoveRoleModal(discord.ui.Modal, title="Remove Role from User"):
    def __init__(self, user: discord.Member):
        super().__init__()
        self.user = user
        self.role = discord.ui.TextInput(
            label="Role ID to remove",
            placeholder="Enter the ID of the role to remove...",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.role)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role.value)
            role = interaction.guild.get_role(role_id)
            if role:
                await self.user.remove_roles(role)
                await interaction.response.send_message(
                    f"Successfully removed {role.name} from {self.user.mention}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Role not found. Please check the role ID.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid role ID.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to remove this role.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while executing the command: {str(e)}",
                ephemeral=True
            )

class PurgeModal(discord.ui.Modal, title="Purge Messages"):
    def __init__(self):
        super().__init__()
        self.amount = discord.ui.TextInput(
            label="Number of messages to delete",
            placeholder="Enter the number of messages to purge (1-100)...",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
            if amount < 1 or amount > 100:
                await interaction.response.send_message(
                    "Please enter a number between 1 and 100.",
                    ephemeral=True
                )
                return
                
            # Delete the messages
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.response.send_message(
                f"Successfully deleted {len(deleted)} messages.",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to delete messages in this channel.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An error occurred while executing the command: {str(e)}",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationPanel(bot))
