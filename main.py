import configparser
import sqlite3
import requests
import secrets
import time
import asyncio
import threading
import schedule
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Final
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CallbackContext


# Fetch configurations
config = configparser.ConfigParser()
config.read('config.ini')
TOKEN: Final = config['botinfo']['token']
BOT_USERNAME: Final = config['botinfo']['bot_username']
MAL_CLIENT_ID: Final = config['mal']['client_id']
MAL_ACCESS_TOKEN: Final = config['mal']['access_token']

# Helper functions
async def fetch_anime_search_results(query, offset=0):
    auth_header = {
        "Authorization": "Bearer " + MAL_ACCESS_TOKEN
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.myanimelist.net/v2/anime?q={query}&limit=4&offset={offset}&nsfw=true', headers=auth_header) as response:
            results = await response.json()
    return results['data']

async def fetch_anime_info(anime_id):
    auth_header = {
        "Authorization": "Bearer " + MAL_ACCESS_TOKEN
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.myanimelist.net/v2/anime/{anime_id}?fields=id,title,start_date,synopsis,status,num_episodes,broadcast', headers=auth_header) as response:
            results = await response.json()
    return results

async def get_latest_episode(anime_id):
    anime_url = f'https://myanimelist.net/anime/{anime_id}'
    async with aiohttp.ClientSession() as session:
        async with session.get(anime_url) as response:
            page_content = await response.text()
    soup = BeautifulSoup(page_content, 'html.parser')
    a_tag = soup.find('a', string='Episodes')
    if a_tag:
        href = a_tag.get('href')
    else:
        return None

    async with aiohttp.ClientSession() as session:
        async with session.get(href) as response:
            page_content = await response.text()
    soup = BeautifulSoup(page_content, 'html.parser')
    episodes = soup.find_all('tr', {'class': 'episode-list-data'})
    return len(episodes)

# Command functions
# /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # TODO: set interval to 3600 (1hr)
    # TODO: prevent multiple of same job (user keeps entering /start)

    print('/start')


    await update.message.reply_text('Hi! I am a bot that notifies you of new anime episodes based on your anime list. Run /help for a list of commands to get started.')
    context.job_queue.run_repeating(check_new_episodes, interval=30,first=1.0,chat_id=update.message.chat_id)

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('''
You may add animes into your list, and if it is airing, I will let you know when a new episode is released! Please see below for commands:
    /help - Provides commands
    /list - View anime list
    /add [anime] - Add new anime to list
    /remove - Remove anime from list''')

# /list
async def view_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print('/list')
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT a.title, a.latest_episode, a.num_episodes FROM animes AS a, userlists AS u WHERE u.user_id = ? AND a.anime_id = u.anime_id', (user_id, ))
    anime_list = c.fetchall()
    conn.close()

    text = f"*{user_name}'s anime list*\n\n"

    if len(anime_list) == 0:
        text += "Your list is empty. Run the /add \[anime] command to start tracking animes!"

    else:
        count = 1
        for anime in anime_list:
            title, latest_episode, num_episodes = anime
            text += f"{count}. {title}\t\t({latest_episode}/{num_episodes})\n"
            count += 1



    await update.message.reply_text(text, parse_mode="Markdown")

# /add [anime]
async def add_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    query = '+'.join(context.args)
    # print(f'Searched for {query}')

    if len(query.strip()) < 3 or len(query.strip()) > 50:
        print('Invalid anime name')
        await update.message.reply_text('Run /add [anime] to search for animes to add to your list.\nEnsure your input is 3-50 characters long.')
        return
    
    if '_' in query:
        print('Invalid anime name')
        await update.message.reply_text('Your input cannot contain the underscore ( _ ) character.')
        return

    # access_token = get_mal_access_token()
    
    # TODO: implement refresh token stuff 1 month ltr if access token expire 

    results = await fetch_anime_search_results(query)

    # Display 4 results
    buttons = []
    for result in results:
        # print(result)
        anime_title = result['node']['title']
        anime_id = result['node']['id']
        buttons.append([InlineKeyboardButton(anime_title, callback_data=f"add_{query}_{anime_id}_0")])

    # Button to fetch next 4 results
    buttons.append([InlineKeyboardButton("Next", callback_data=f"offset_{query}_4")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text('Select the correct anime:', reply_markup=reply_markup)
    
# /remove 
async def remove_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    '''Remove a specific or all animes from list'''

    user_id = update.message.from_user.id
    remove_id = ''.join(context.args)
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT a.title,a.anime_id FROM animes AS a, userlists AS u WHERE u.user_id = ? AND a.anime_id = u.anime_id', (user_id, ))
    anime_list = c.fetchall()
    conn.close()

    # Check if 'ALL'
    if remove_id == 'ALL':
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('DELETE FROM userlists WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

        await update.message.reply_text('Your list has been successfully cleared!', parse_mode="Markdown")

    else:
        # Check if valid number
        try:
            remove_id = int(remove_id)
            if remove_id < 1:
                raise Exception
            remove_arrid = remove_id - 1
            remove_anime_name, remove_anime_id = anime_list[remove_arrid]
            # print(remove_anime_name, remove_anime_id)
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            c.execute('DELETE FROM userlists WHERE user_id = ? AND anime_id = ?', (user_id, remove_anime_id,))
            conn.commit()
            conn.close()

            await update.message.reply_text(f'*{remove_anime_name}* successfully removed from your list!', parse_mode="Markdown")

        except:

            if len(anime_list) == 0:
                text = "Your list is empty."
            else:
                text = "*Which anime would you like to remove from your list?*\nReply with /remove \[number], or /remove ALL to clear the list.\n\n"
                count = 1
                for anime in anime_list:
                    text += f"{count}. {anime[0]}\n"
                    count += 1

            await update.message.reply_text(text, parse_mode="Markdown")

# Check for new episodes
async def check_new_episodes(context: ContextTypes.DEFAULT_TYPE):
    print('Checking for new episode...')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Only check the animes from the database which the user has

    c.execute('SELECT a.anime_id, a.title, a.num_episodes, a.latest_episode FROM animes AS a, userlists AS u WHERE a.anime_id = u.anime_id AND a.status != "finished_airing"')
    results = c.fetchall()
    print(results)
    # print(results)
    conn.close()

    for anime in results:
        # print(anime)
        id, title, num_episodes, latest_episode_db = anime
        latest_episode_online = await get_latest_episode(id)


        # if id == 55791:
        #     latest_episode_online = 13

        # print(latest_episode_online, latest_episode_db)

        # No new episode
        if latest_episode_online <= latest_episode_db:
            print(f'[{title}]: NO new episode')
            continue
        
        # New episode
        print(f'[{title}]: New episode')
        status = 'currently_airing'

        notification = f'Episode {latest_episode_online} of *{title}* has been released!'

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Anime ended, remove from database
        if num_episodes == latest_episode_online:
            print(f'{title} ended')
            status = 'finished_airing'
            notification += '\nThis anime has ended!'
            c.execute('DELETE FROM animes WHERE anime_id = ?',(id,))

            # NOT SURE WHY FOREIGN KEY NOT WORKING, DELETE MANUALLY FROM userlists FIRST
            
            c.execute('DELETE FROM userlists WHERE anime_id = ?', (id,))
            conn.commit()
            conn.close()

        else:
            # Ongoing anime, update database
            c.execute('UPDATE animes SET status = ?, latest_episode = ? WHERE anime_id = ?', (status, latest_episode_online,id,))
            conn.commit()
            conn.close()
            # conn.commit()

            # c.execute('SELECT user_id FROM userlists WHERE anime_id = ?', (id,))
            # users = c.fetchall()


        # conn.commit()
        # conn.close()

        # Notify all users with the anime
        # for user in users:
        await context.bot.send_message(context.job.chat_id, text=notification,parse_mode="Markdown")

            

# Callback query handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    query = update.callback_query
    query_data = query.data
    # print(query_data)

    if query_data.startswith('offset_'):

        '''Retrieve queried animes at specified offset'''

        # print('NEXT')
        parts = query_data.split('_')
        search_query = parts[1]
        offset = int(parts[2])
        # print(parts)

        results = await fetch_anime_search_results(search_query, offset)
        buttons = []
        for result in results:
            anime_title = result['node']['title']
            anime_id = result['node']['id']
            buttons.append([InlineKeyboardButton(anime_title, callback_data=f"add_{search_query}_{anime_id}_{offset}"),])

        # Next Button
        buttons.append([InlineKeyboardButton("Next", callback_data=f"offset_{search_query}_{offset + 4}")])
        
        # Previous Button if not on first page
        if offset != 0:
            buttons[-1].insert(0, InlineKeyboardButton("Previous", callback_data=f"offset_{search_query}_{offset-4}"))

        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text('Select the correct anime:', reply_markup=reply_markup)


    elif query_data.startswith('add_'):

        '''Display selected anime info and asked to confirm'''

        parts = query_data.split('_')
        search_query = parts[1]
        anime_id = parts[2]
        offset = int(parts[3])

        # print('current offset:', offset)
        results = await fetch_anime_info(anime_id)
        # print(results)
        title = results['title']

        start_date = results['start_date']
        try:
            date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            start_date = date_obj.strftime("%d %B %Y")
        except:
            date_obj = datetime.strptime(start_date, '%Y-%m')
            start_date = date_obj.strftime("%B %Y")
        synopsis = results['synopsis']
        num_episodes = results['num_episodes']
        status = results['status'].title().replace('_',' ')
        # # print(status)
        try:
            broadcast_day = results['broadcast']['day_of_the_week'].title()
            # # print(broadcast_day)
            broadcast_time = results['broadcast']['start_time']
        except:
            broadcast_day = broadcast_time = None
        


        # Check if Finished Airing

        text = f'''
*{title}*

_{synopsis}_

Episodes: {num_episodes}
Start Date: {start_date}
Broadcast: Every {broadcast_day} at {broadcast_time} (JST)
Status: {status}

'''
        
        if status == 'Finished Airing':
            text += '*This show has finished airing. Please select an anime that is currently airing or has not been released.*'
            buttons = [[InlineKeyboardButton('OK', callback_data=f"offset_{search_query}_{offset}")]]
           
        else:
            
            # Check if user already has this anime in list
            
            conn = sqlite3.connect('database.db')
            c = conn.cursor()

            c.execute("SELECT * FROM userlists WHERE user_id = ? AND anime_id = ?", (user_id, anime_id,))
            result = c.fetchone()
            conn.close()
            if result is not None:
                text += '*This show is already in your list!*'
                buttons = [[InlineKeyboardButton('OK', callback_data=f"offset_{search_query}_{offset}")]]

            else:
                text += '*Is this the anime you want to track?*'
                buttons = [
                [InlineKeyboardButton('Yes', callback_data=f"cfm_add_{user_id}_{anime_id}"),
                InlineKeyboardButton('No', callback_data=f"offset_{search_query}_{offset}")]
                ]

                # print(user_id, anime_id)

        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text,parse_mode="Markdown",reply_markup=reply_markup)

    
    elif query_data.startswith('cfm_add_'):

        '''Add anime to database'''

        user_id = query_data.split('_')[2]
        anime_id = query_data.split('_')[3]

        

        # Add anime into "animes" table if not present

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        c.execute("SELECT * FROM animes WHERE anime_id = ?", (anime_id,))
        result = c.fetchone()
        # Get anime info
        anime_info = await fetch_anime_info(anime_id)
        title = anime_info['title']

        # Anime not in table
        if result is None:

            synopsis = anime_info['synopsis']
            start_date = anime_info['start_date']
            num_episodes = anime_info['num_episodes']
            status = anime_info['status']
            latest_episode = await get_latest_episode(anime_id)
            # print(status)
            try:
                broadcast_day = anime_info['broadcast']['day_of_the_week']
                # print(broadcast_day)
                broadcast_time = anime_info['broadcast']['start_time']
            except:
                broadcast_day = broadcast_time = None

            c.execute("INSERT INTO animes (anime_id, title, synopsis, start_date, num_episodes, latest_episode, status, broadcast_day, broadcast_time) VALUES (?,?,?,?,?,?,?,?,?)", (anime_id, title, synopsis, start_date, num_episodes, latest_episode, status, broadcast_day, broadcast_time, ))

        # Add entry to "userlists" table
        c.execute("INSERT INTO userlists (user_id, anime_id) VALUES (?,?)", (user_id, anime_id, ))
    
        conn.commit()
        conn.close()

        await query.edit_message_text(f'*{title}* has been added into your list!', parse_mode="Markdown")


# Responses

def handle_response(text: str) -> str:

    processed: str = text.lower()
    if 'hi' in processed:
        return 'hi'
    
    if 'caonima' in processed:
        return 'fuck u'
    
    return 'i do not understance'
    
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_type: str = update.message.chat.type    # group chat or private chat?
    text: str = update.message.text                 # incoming message

    print(f'User ({update.message.chat.id}) in {message_type}: "{text}"')

    if message_type == 'group':
        if BOT_USERNAME in text:
            new_text: str = text.replace(BOT_USERNAME, '').strip()
            response: str = handle_response(new_text)

        else:
            return
    else:
        response: str=handle_response(text)

    print('Bot:', response)
    await update.message.reply_text(response)

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')

def main():
    print('Starting bot...')
    app = Application.builder().token(TOKEN).build()

    # Connect to database
    print('Initialising database...')
    db_name =  'database.db'
    conn = sqlite3.connect(db_name,check_same_thread=False)
    c = conn.cursor()
    print('Connected to database!')


    
    
    # Create "animes" table
    sql = '''
    CREATE TABLE IF NOT EXISTS animes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anime_id INTEGER,
        title TEXT NOT NULL,
        synopsis TEXT,
        start_date DATE,
        num_episodes INTEGER,
        latest_episode INTEGER,
        status TEXT,
        broadcast_day TEXT,
        broadcast_time TIME
    )'''
    c.execute(sql)

    # Create "userlists" table

    sql = '''
    CREATE TABLE IF NOT EXISTS userlists (
        user_id INTEGER,
        anime_id INTEGER,
        FOREIGN KEY (anime_id) REFERENCES animes (anime_id) ON DELETE CASCADE
    )'''
    c.execute(sql)
    conn.commit()
    conn.close()

    print('Tables are ready!')

    # Commands
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('list', view_list_command))
    app.add_handler(CommandHandler('add', add_anime_command))
    app.add_handler(CommandHandler('remove', remove_anime_command))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    # Callback query handler
    app.add_handler(CallbackQueryHandler(button))

    # Errors
    app.add_error_handler(error)

    

    # Polls the bot
    print('Polling...')
    app.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()
    