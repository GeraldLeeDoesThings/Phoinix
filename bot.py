import discord
import discord.app_commands as app_commands
import requests


class PhoinixBot(discord.Client):

    async def on_ready(self):
        print("Nya")

intents = discord.Intents.default()
intents.message_content = True

bot = PhoinixBot(intents=intents)
with open("token", "r") as token:
    bot.run(token.read())
