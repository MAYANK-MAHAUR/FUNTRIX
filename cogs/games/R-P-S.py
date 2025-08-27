import asyncio
import random
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# Load environment variables if you are using a .env file
# load_dotenv() 

# --- Constants ---
CHOICES = [
    app_commands.Choice(name="🪨 Rock", value="rock"),
    app_commands.Choice(name="📄 Paper", value="paper"),
    app_commands.Choice(name="✂️ Scissors", value="scissors")
]

BEATS = {
    "rock": "paper",
    "paper": "scissors",
    "scissors": "rock"
}

# --- UI View for the Dropdown ---
class RPSView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance

    @discord.ui.select(
        placeholder="Choose your move...",
        options=[
            discord.SelectOption(label="Rock", value="rock", emoji="🪨"),
            discord.SelectOption(label="Paper", value="paper", emoji="📄"),
            discord.SelectOption(label="Scissors", value="scissors", emoji="✂️")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        guild_id = interaction.guild.id
        game_data = self.cog.active_rps.get(guild_id)

        if not game_data:
            return await interaction.response.send_message(
                "❗ No RPS game is currently running in this server.", ephemeral=True
            )

        if interaction.user.id in game_data["guesses"]:
            return await interaction.response.send_message(
                "❌ You have already made your guess for this round!", ephemeral=True
            )

        guess_value = select.values[0]
        game_data["guesses"][interaction.user.id] = guess_value

        guess_name = "your move"
        for option in select.options:
            if option.value == guess_value:
                guess_name = f"{option.emoji} {option.label}"
                break
        
        await interaction.response.send_message(
            f"✅ Your guess of **{guess_name}** has been recorded.", ephemeral=True
        )

# --- Main Cog ---
class RPS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_rps = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print("RPS cog is ready.")

    @app_commands.command(name="startrps", description="Start a Rock Paper Scissors game.")
    @app_commands.describe(choice="Choose your move to start the game.")
    @app_commands.choices(choice=CHOICES)
    async def start_rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        # NOTE: This version does not have role restrictions, as the user's
        # `GUESS_THE_NUMBER.py` has its own `ALLOWED_ROLES` list.
        # You may want to re-add your `DatabaseManager` and role checks if needed.
        guild_id = interaction.guild.id

        if guild_id in self.active_rps:
            return await interaction.response.send_message(
                "❗ An RPS game is already running in this server.", ephemeral=True
            )

        winning_move = BEATS[choice.value]
        
        self.active_rps[guild_id] = {
            "channel_id": interaction.channel.id,
            "winning_move": winning_move,
            "guesses": {},
            "stop_event": asyncio.Event(),
            "message_id": None
        }

        embed = discord.Embed(
            title="🪨📄✂️ Rock Paper Scissors",
            description=(
                "**A new game has started!**\n\n"
                "The host has chosen their secret move.\n"
                "To win, you must pick the move that **beats** their choice.\n\n"
                "You have **60 seconds** to pick!\n\n"
                "👇 Use the dropdown menu below to lock in your move."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Good luck!")
        
        view = RPSView(self)
        await interaction.response.send_message(embed=embed, view=view)
        
        message = await interaction.original_response()
        self.active_rps[guild_id]["message_id"] = message.id
        
        self.bot.loop.create_task(self.run_rps_game(interaction.channel))

    async def run_rps_game(self, channel):
        guild_id = channel.guild.id
        game_data = self.active_rps.get(guild_id, {})
        if not game_data:
            return

        try:
            await asyncio.wait_for(game_data["stop_event"].wait(), timeout=60.0)
            await channel.send("🛑 RPS game cancelled by an admin.")
        
        except asyncio.TimeoutError:
            winning_move = game_data["winning_move"]
            correct_guesses = [
                user_id for user_id, guess in game_data["guesses"].items()
                if guess == winning_move
            ]

            await channel.send("🔍 **Time's up! Finding the winner...**")
            await asyncio.sleep(2)

            if correct_guesses:
                winner_id = random.choice(correct_guesses)
                winner_user = self.bot.get_user(winner_id) or await self.bot.fetch_user(winner_id)
                
                final_embed = discord.Embed(
                    title="🎉 We Have a Winner!",
                    description=f"{winner_user.mention} guessed the correct move!",
                    color=discord.Color.green()
                )
                await channel.send(embed=final_embed)

            else:
                final_embed = discord.Embed(
                    title="Game Over",
                    description="😔 No one guessed correctly!",
                    color=discord.Color.red()
                )
                await channel.send(embed=final_embed)

        # --- Cleanup ---
        if game_data and game_data.get("message_id"):
            try:
                original_message = await channel.fetch_message(game_data["message_id"])
                await original_message.edit(view=None)
            except (discord.NotFound, discord.Forbidden):
                pass
        
        self.active_rps.pop(guild_id, None)
        await channel.send("✅ The game is over.")

    @app_commands.command(name="stoprps", description="Force stop the Rock Paper Scissors game")
    async def stoprps(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        
        if not any(role.name in ["Game Master", "Moderator"] for role in interaction.user.roles):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)

        if guild_id in self.active_rps:
            self.active_rps[guild_id]["stop_event"].set()
            await interaction.response.send_message("🛑 Stopping the RPS game...", ephemeral=True)
        else:
            await interaction.response.send_message(
                "❗ No RPS game is currently running in this server.", ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(RPS(bot))