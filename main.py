import os
import nextcord

from os import environ as env

from nextcord import Intents, Interaction
from nextcord.ext import commands
from nextcord.ext.commands import errors
from nextcord.ext.application_checks import errors as application_errors


class Bot(commands.Bot):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdv_view_set = False

	async def on_ready(self):
		print("Ready")

	async def on_command_error(self, ctx, error):
		if isinstance(error, errors.CommandNotFound):
			return
		elif isinstance(error, errors.TooManyArguments):
			await ctx.send("Vous avez donné trop d'arguments!")
			return
		elif isinstance(error, errors.BadArgument):
			await ctx.send(
				"La commande a rencontré une erreur en tentant d'analyser votre argument."
			)
			return
		elif isinstance(error, errors.MissingRequiredArgument):
			await ctx.send("Arguments requis manquant.")
		# kinda annoying and useless error.
		elif isinstance(error, nextcord.NotFound) and "Interaction inconnu" in str(error):
			return
		elif isinstance(error, errors.MissingRole):
			role = ctx.guild.get_role(int(error.missing_role))  # type: ignore
			await ctx.send(f'Le role "{role.name}" est requis pour utiliser cette commande.') # type: ignore
			return
		else:
			await ctx.send(
				f"La commande a rencontré une erreur: `{type(error)}:{str(error)}`"
			)

	async def on_application_command_error(self, interaction: Interaction, error: Exception) -> None:
		if isinstance(error, application_errors.ApplicationMissingRole):
			role = interaction.guild.get_role(int(error.missing_role))  # type: ignore
			await interaction.send(f"Le role {role.mention} est requis pour uitliser cette commmande.", ephemeral=True)  # type: ignore
			return
		elif isinstance(error, application_errors.ApplicationMissingPermissions):
			await interaction.send(f"Le role {error.missing_permissions} est requis pour uitliser cette commmande.", ephemeral=True)
			return
		else:
			await interaction.send(
				f"La commande a rencontré une erreur: `{type(error)}:{str(error)}`",
				ephemeral=True,
			)


client = Bot("=", intents=Intents(messages=True, guilds=True, members=True, message_content=True))

for filename in os.listdir("./cogs"):
	if filename.endswith('.py'):
		client.load_extension(f'cogs.{filename[:-3]}')
		print(f"cogs: {filename[:-3]} cog loaded.")

if __name__ == '__main__':
	client.run(env["DISCORD_TOKEN"])
