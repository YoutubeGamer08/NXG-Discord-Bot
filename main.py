# main.py
from keep_alive import keep_alive
keep_alive()

import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.messages = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)


# Your lobby VC channels
VC_LOBBIES = {
    1419099299119108267: "Non Members VC",
    1419086023169933363: "Clan Only VC",
    1419085046282715297: "Verified VC",
}

private_vcs = {}  # vc_id: owner_id
vc_limits = {}    # vc_id: user_limit

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

async def delete_when_empty(vc):
    while len(vc.members) > 0:
        owner_id = private_vcs.get(vc.id)
        if owner_id and owner_id not in [m.id for m in vc.members]:
            new_owner = vc.members[0]
            private_vcs[vc.id] = new_owner.id
            try:
                await new_owner.send(
                    f"You are now the owner of '{vc.name}' because the previous owner left.\n"
                    "Commands via DM:\n"
                    "`!kick @user`, `!rename New Name`, `!limit 4`, `!mute @user`, `!deafen @user`"
                )
            except discord.Forbidden:
                pass
        await asyncio.sleep(5)
    private_vcs.pop(vc.id, None)
    vc_limits.pop(vc.id, None)
    await vc.delete()

@bot.event
async def on_voice_state_update(member, before, after):
    # Create private VC when joining a lobby
    if after.channel and after.channel.id in VC_LOBBIES:
        lobby_name = VC_LOBBIES[after.channel.id]

        private_vc = await member.guild.create_voice_channel(
            name=f"{lobby_name} - {member.display_name}",
            category=after.channel.category
        )

        await member.move_to(private_vc)

        await private_vc.set_permissions(member, connect=True, manage_channels=True,
                                         move_members=True, mute_members=True, deafen_members=True)
        await private_vc.set_permissions(member.guild.default_role, connect=False)

        private_vcs[private_vc.id] = member.id

        try:
            await member.send(
                f"Your private VC '{private_vc.name}' has been created!\n"
                "Commands via DM:\n"
                "`!kick @user`, `!rename New Name`, `!limit 4`, `!mute @user`, `!deafen @user`"
            )
        except discord.Forbidden:
            pass

        bot.loop.create_task(delete_when_empty(private_vc))

    # Handle join requests
    if after.channel and after.channel.id in private_vcs and member.id != private_vcs[after.channel.id]:
        owner_id = private_vcs[after.channel.id]
        owner = await bot.fetch_user(owner_id)

        await member.move_to(None)
        try:
            await member.send(f"The owner of '{after.channel.name}' has been notified. Waiting for approval...")
        except discord.Forbidden:
            pass
        try:
            await owner.send(f"{member.display_name} wants to join your private VC '{after.channel.name}'. Reply with 'yes' or 'no'.")
        except discord.Forbidden:
            return

        def check(m):
            return m.author == owner and m.content.lower() in ["yes", "no"]

        async def handle_request():
            try:
                msg = await bot.wait_for('message', check=check, timeout=60)
                if msg.content.lower() == "yes":
                    limit = vc_limits.get(after.channel.id)
                    if limit and len(after.channel.members) >= limit:
                        await owner.send(f"Cannot allow {member.display_name}: VC reached the limit ({limit}).")
                        await member.send(f"Your request to join '{after.channel.name}' was denied: VC full.")
                        return
                    await after.channel.set_permissions(member, connect=True)
                    await member.move_to(after.channel)
                    try:
                        await member.send(f"You have been approved and moved to '{after.channel.name}'!")
                    except discord.Forbidden:
                        pass
                    try:
                        await owner.send(f"{member.display_name} has been approved and moved into your VC.")
                    except discord.Forbidden:
                        pass
                else:
                    try:
                        await member.send(f"Your request to join '{after.channel.name}' was denied.")
                        await owner.send(f"{member.display_name} was denied access to your VC.")
                    except discord.Forbidden:
                        pass
            except asyncio.TimeoutError:
                try:
                    await owner.send(f"{member.display_name} tried to join your VC, but you did not respond in time.")
                    await member.send(f"Your request to join '{after.channel.name}' timed out. Owner did not respond.")
                except discord.Forbidden:
                    pass

        bot.loop.create_task(handle_request())

# DM commands
@bot.command()
async def kick(ctx, member: discord.Member):
    if isinstance(ctx.channel, discord.DMChannel):
        owner_vc = next((ctx.guild.get_channel(vc_id) for vc_id, owner_id in private_vcs.items() if owner_id == ctx.author.id), None)
        if not owner_vc:
            await ctx.send("You don't own any private VC right now.")
            return
        if member in owner_vc.members:
            await member.move_to(None)
            await ctx.send(f"{member.display_name} has been removed from your VC.")
            try:
                await member.send(f"You have been removed from '{owner_vc.name}' by the owner.")
            except discord.Forbidden:
                pass
        else:
            await ctx.send(f"{member.display_name} is not in your VC.")

@bot.command()
async def rename(ctx, *, new_name):
    if isinstance(ctx.channel, discord.DMChannel):
        owner_vc = next((ctx.guild.get_channel(vc_id) for vc_id, owner_id in private_vcs.items() if owner_id == ctx.author.id), None)
        if not owner_vc:
            await ctx.send("You don't own any private VC right now.")
            return
        await owner_vc.edit(name=new_name)
        await ctx.send(f"Your VC has been renamed to '{new_name}'.")

@bot.command()
async def limit(ctx, number: int):
    if isinstance(ctx.channel, discord.DMChannel):
        owner_vc = next((ctx.guild.get_channel(vc_id) for vc_id, owner_id in private_vcs.items() if owner_id == ctx.author.id), None)
        if not owner_vc:
            await ctx.send("You don't own any private VC right now.")
            return
        vc_limits[owner_vc.id] = number
        await ctx.send(f"Your VC member limit is now {number}.")

@bot.command()
async def mute(ctx, member: discord.Member):
    if isinstance(ctx.channel, discord.DMChannel):
        owner_vc = next((ctx.guild.get_channel(vc_id) for vc_id, owner_id in private_vcs.items() if owner_id == ctx.author.id), None)
        if not owner_vc:
            await ctx.send("You don't own any private VC right now.")
            return
        if member in owner_vc.members:
            await member.edit(mute=True)
            await ctx.send(f"{member.display_name} has been muted.")
        else:
            await ctx.send(f"{member.display_name} is not in your VC.")

@bot.command()
async def deafen(ctx, member: discord.Member):
    if isinstance(ctx.channel, discord.DMChannel):
        owner_vc = next((ctx.guild.get_channel(vc_id) for vc_id, owner_id in private_vcs.items() if owner_id == ctx.author.id), None)
        if not owner_vc:
            await ctx.send("You don't own any private VC right now.")
            return
        if member in owner_vc.members:
            await member.edit(deafen=True)
            await ctx.send(f"{member.display_name} has been deafened.")
        else:
            await ctx.send(f"{member.display_name} is not in your VC.")
import os

TOKEN = os.getenv("BOT_TOKEN")
bot.run(TOKEN)
