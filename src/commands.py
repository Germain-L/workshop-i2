from discord.ext import commands
from .moderation import moderate_conversation
from .database import get_user_score, get_top_users, get_moderation_stats

class ModCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def moderate_now(self, ctx):
        await moderate_conversation(ctx, self.bot)

    @commands.command()
    async def user_score(self, ctx, user: commands.UserConverter):
        score = await get_user_score(user.id)
        await ctx.send(f"{user.name}'s score: {score}")

    @commands.command()
    async def leaderboard(self, ctx):
        top_users = await get_top_users(10)
        leaderboard_message = "🏆 Top 10 Users:\n\n"
        for i, (username, score) in enumerate(top_users, 1):
            leaderboard_message += f"{i}. {username}: {score} points\n"
        await ctx.send(leaderboard_message)

    @commands.command()
    async def modstats(self, ctx):
        total_moderated, channels_moderated = await get_moderation_stats()
        stats_message = f"📊 Moderation Statistics:\n\n"
        stats_message += f"Total messages moderated: {total_moderated}\n"
        stats_message += f"Channels moderated: {channels_moderated}\n"
        await ctx.send(stats_message)

    @commands.command()
    async def help(self, ctx):
        help_message = (
            "Here are the commands you can use:\n"
            "`!moderate_now`: Manually moderate the ongoing conversation in this channel.\n"
            "`!user_score @user`: Check the score of a specific user.\n"
            "`!leaderboard`: Display the top 10 users with the highest scores.\n"
            "`!modstats`: Display moderation statistics.\n"
            "The score will be adjusted based on message harmfulness.\n"
            "\n"
            "For additional assistance, please reach out to a moderator."
        )
        await ctx.send(help_message)