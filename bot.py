import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio
import concurrent.futures
import string
import random

TOKEN = 'YOUR BOT TOKEN'

disconnect = 0
intents = discord.Intents.all()
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)
song_queue = asyncio.Queue()

@bot.event
async def on_ready():
    await bot.tree.sync()


@bot.event
async def on_voice_state_update(member, before, after):
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    
    if voice_client and voice_client.channel:
        if len(voice_client.channel.members) == 1 and voice_client.channel.members[0].id == bot.user.id:
            global song_queue
            song_queue = asyncio.Queue()
            voice_client.stop()

            for filename in os.listdir('downloads'):
                file_path = os.path.join('downloads', filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")

            await voice_client.disconnect()

def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def download_and_convert(url):

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'downloads/%(id)s_{generate_random_string(5)}.%(ext)s',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        audio_file = ydl.prepare_filename(info)

        info_text = f"Title: {info.get('title', 'Unknown')}\n" \
                    f"Creator: {info.get('uploader', 'Unknown')}\n" \
                    f"Duration: {info.get('duration', 0):.0f} seconds\n" \
                    f"Views: {info.get('view_count', 'Unknown')}\n" \
                    f"Upload Date: {info.get('upload_date', 'Unknown')}\n"
        info_file = f'{audio_file}.txt'
        with open(info_file, 'w') as f:
            f.write(info_text)

    return audio_file, info_file

@bot.tree.command()
async def play(interaction: discord.Interaction, url: str):
    global disconnect
    disconnect = 0

    if not interaction.user.voice:
        await interaction.response.send_message("You are not connected to a voice channel.")
        return

    voice_channel = interaction.user.voice.channel

    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    if voice_client is None:
        voice_client = await voice_channel.connect()
    else:
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    if voice_client.is_playing() or not song_queue.empty():
        audio_file_info = await asyncio.get_event_loop().run_in_executor(
            executor, download_and_convert, url
        )
        await song_queue.put(audio_file_info)
        embed = discord.Embed(
            description="Music added to the queue.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    else:
        with yt_dlp.YoutubeDL({}) as ydl:
            info = ydl.extract_info(url, download=False)
            embed = discord.Embed(
                title="Currently Playing:",
                description=f"**Title:** {info.get('title', 'Unknown')}\n"
                            f"**Creator:** {info.get('uploader', 'Unknown')}\n"
                            f"**Duration:** {info.get('duration', 0):.0f} seconds\n"
                            f"**Views:** {info.get('view_count', 'Unknown')}\n"
                            f"**Upload Date:** {info.get('upload_date', 'Unknown')}\n",
                color=discord.Color.blue()
            )
            if info.get('thumbnail'):
                embed.set_image(url=info['thumbnail'])
            await interaction.response.send_message(embed=embed)

            audio_file_info = await asyncio.get_event_loop().run_in_executor(
                executor, download_and_convert, url
            )

            await song_queue.put(audio_file_info) 

            if not voice_client.is_playing():
                await play_next(interaction)

@bot.tree.command()
async def skip(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if voice_client:
        if song_queue.empty():
            await interaction.response.send_message(embed=discord.Embed(description="There is no music in the queue.", color=discord.Color.red()))
        else:
            voice_client.stop()
            await interaction.response.send_message(embed=discord.Embed(description="Next song.", color=discord.Color.blue()))

            currently_playing = await song_queue.get()
            print(currently_playing)
            os.remove(currently_playing[0]) 
            os.remove(currently_playing[1]) 
    else:
        await interaction.response.send_message(embed=discord.Embed(description="The bot is not connected to a voice channel.", color=discord.Color.red()))

@bot.tree.command()
async def disconnect(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if interaction.user.voice and voice_client:
        global song_queue
        song_queue = asyncio.Queue()
        voice_client.stop()
        await song_queue.join()

        for filename in os.listdir('downloads'):
            file_path = os.path.join('downloads', filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")

        await voice_client.disconnect()
        await interaction.response.send_message(embed=discord.Embed(description="Disconnected from the voice channel and cleared the queue.", color=discord.Color.red()))
    else:
        await interaction.response.send_message("You must be connected to a voice channel to use this command.")
    global disconnect
    disconnect = 1

async def play_next(interaction: discord.Interaction):
    if disconnect == 1:
        return
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if not voice_client: 
        return 

    if song_queue.empty():
        return

    audio_file_info = await song_queue.get()
    audio_file = audio_file_info[0]
    info_file = audio_file_info[1]

    with open(info_file, 'r') as f:
        info_lines = f.readlines()
    next_song_title = info_lines[0].strip().split(':', 1)[1]
    next_song_creator = info_lines[1].strip().split(':', 1)[1]

    if voice_client.is_connected():
        voice_client.play(discord.FFmpegPCMAudio(audio_file))
    else:
        return

    while voice_client.is_playing():
        await asyncio.sleep(1)

    os.remove(audio_file) 
    os.remove(info_file)

    embed = discord.Embed(
        title="Next Song",
        description=f"**Title:** {next_song_title}\n"
                    f"**Creator:** {next_song_creator}",
        color=discord.Color.blue()
    )
    await interaction.followup.send(embed=embed)

    await play_next(interaction)

bot.run(TOKEN)
