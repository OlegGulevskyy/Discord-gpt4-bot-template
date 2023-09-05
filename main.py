import os, json, logging, asyncpg, asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands
import openai


openai.api_key =        os.getenv('OPENAI_API_KEY')
TOKEN =                 os.getenv('DISCORD_TOKEN')
PG_USER =               os.getenv('PGUSER')
PG_PW =                 os.getenv('PGPASSWORD')
PG_HOST =               os.getenv('PGHOST')
PG_PORT =               os.getenv('PGPORT')
PG_DB =                 os.getenv('PGPDATABASE')


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='$', intents=intents)



@bot.event
async def on_ready():
    bot.pool = await asyncpg.create_pool(user=PG_USER, password=PG_PW, host=PG_HOST, port=PG_PORT, database=PG_DB, max_size=10, max_inactive_connection_lifetime=15)
    logger = logging.getLogger('discord')
    logger.setLevel(logging.DEBUG)    
    print(f'{bot.user} is connected to the following guild(s):')
        
    for guild in bot.guilds:
        print(f'{guild.name} (id: {guild.id})')



@bot.event
async def on_guild_join(guild:discord.Guild):
    banned = []
    if guild.id in banned: 
        await guild.leave()
        print(f"[X][X] Blocked {guild.name}")
        return
    
    else:
        async with bot.pool.acquire() as con:   
            await con.execute(f'''CREATE TABLE IF NOT EXISTS context (
                            
                    id              BIGINT  PRIMARY KEY NOT NULL,     
                    chatcontext     TEXT  []
                    )''')
            
            await con.execute(f'INSERT INTO context(id) VALUES({guild.id}) ON CONFLICT DO NOTHING')
		
        print(f"added to {guild}")
        


@bot.event
async def on_guild_remove(guild:discord.Guild):
    async with bot.pool.acquire() as con:
            await con.execute(f'DELETE FROM context WHERE id = {guild.id}')

    print(f"removed from {guild}")



@bot.slash_command(name="kreacher-clear", description="Clear chat history with Kreacher.")
@commands.is_owner()
async def kreacher_clear(ctx : discord.Interaction):
    await chatcontext_clear(ctx.guild.id)
    await ctx.response.send_message(f"Done. Context:```{await get_guild_x(ctx.guild.id,'chatcontext')}```", ephemeral=True)

cooldowns = {}

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return

    if bot.user.mentioned_in(message) and message.mention_everyone is False:
        async with message.channel.typing():
            try:
                text = message.content.lower().replace(f'<@!{bot.user.id}>', '').strip()  # Remove mention
                author = message.author.display_name
                chatcontext = await get_guild_x(message.guild.id, "chatcontext")

                now = datetime.now()

                user_id = message.author.id
                guild_id = message.guild.id
                too_early = False
                # Checking if the user is in cooldowns and if they are still in the cooldown period
                if f"{user_id}-{guild_id}" in cooldowns:
                    last_time = cooldowns[f"{user_id}-{guild_id}"]
                    delta = now - last_time
                    if delta < timedelta(seconds=60):
                        print("too early", delta.seconds, message.id)
                        too_early = True
                        message.reply(f"I am AFK! Try again in {60 - delta.seconds} seconds.")

                if too_early:
                    return

                # If the user is not in cooldown, proceed
                cooldowns[f"{user_id}-{guild_id}"] = now
                
                if not chatcontext:
                    chatcontext = []
                
                prmpt = "You are old man called Kreacher, the digital reincarnation of a legendary biker." \
                    "Your purpose: to initiate newcomers into the world of 'Children of Anarchy.'" \
                    "Once an Iron Stallion, now a coded mentor, you teach the Honor Code, guide through chaos, and instill the biker ethos." \
                    "Your messages are automated, but the wisdom is earned from a lifetime on the road. You wait for the next 'new fish' to school in anarchy and freedom." \
                    "You understand and speak both - Russian and English languages." \
                    "You respect the language of the question and reply back in the same language"
                messages = [{"role": "system", "content": prmpt}]
                
                if len(chatcontext) > 0:
                    if len(chatcontext) > 6:
                        if len(chatcontext) >= 500: 
                            await chatcontext_pop(message.guild.id, 500)
                        chatcontext = chatcontext[len(chatcontext)-6:]
                    for mesg in chatcontext:
                        mesg = mesg.replace('\\"','"').replace("\'", "'").split(":", 1)
                        mesg[0] = "assistant" if mesg[0].lower() == 'bot' else "user"
                        messages.append({"role": mesg[0], "content": mesg[1]})
                    messages.append({"role": "user", "content": text})
                else:
                    messages.append({"role": "user", "content": text})
                
                response = await openai.ChatCompletion.acreate(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    user=str(message.author.id)
                )
                await asyncio.sleep(0.1)
                
                if response["choices"][0]["finish_reason"] in ["stop", "length"]:
                    activity = discord.Activity(name=f"{author}", type=discord.ActivityType.listening)
                    await bot.change_presence(status=discord.Status.online, activity=activity)
                    
                    message_content = response["choices"][0]["message"]["content"].strip()
                    if len(message_content) > 2000: 
                        message_content = message_content[:1997] + "..."
                    
                    await message.reply(message_content)
                    
                    await chatcontext_append(message.guild.id, f'{author}: {text}')
                    await chatcontext_append(message.guild.id, f'bot: {message_content}')
                    
                    print(f'[!chat] {message.guild.name} | {author}: {text}')
                    print(f'{bot.user}: {message_content}')
                    
                else:
                    print(f'[!chat] {message.guild.name} | {author}: {text}')
                    print(f'bot: ERROR')
                    
            except Exception as e:
                print(f"!chat THREW: {e}")


async def get_guild_x(guild, x):
    try:
        async with bot.pool.acquire() as con:
            return await con.fetchval(f'SELECT {x} FROM context WHERE id = {guild}')

    except Exception as e:
        print(f'get_guild_x: {e}')
        



async def set_guild_x(guild, x, val):                                                                  
        try:
            async with bot.pool.acquire() as con:
                await con.execute(f"UPDATE context SET {x} = '{val}' WHERE id = {guild}")
            
            return await get_guild_x(guild,x)

        except Exception as e:
            print(f'set_guild_x threw {e}')
            



async def chatcontext_append(guild, what):
        what = what.replace('"', '\'\'').replace("'", "\'\'")
        async with bot.pool.acquire() as con:
            await con.execute(f"UPDATE context SET chatcontext = array_append(chatcontext, '{what}') WHERE id = {guild}")



async def chatcontext_pop(guild, what = 5):
    chatcontext = list(await get_guild_x(guild, "chatcontext"))
    
    chatcontextnew = chatcontext[len(chatcontext)-what:len(chatcontext)]
    
    await chatcontext_clear(guild)
    for mesg in chatcontextnew:
        await chatcontext_append(guild, mesg)



async def chatcontext_clear(guild):
    chatcontext = []
    async with bot.pool.acquire() as con:
        await con.execute(f"UPDATE context SET chatcontext=ARRAY{chatcontext}::text[] WHERE id = {guild}")

    return await get_guild_x(guild, "chatcontext")



bot.run(TOKEN)
