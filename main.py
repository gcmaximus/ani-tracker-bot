import configparser
import sqlite3
from typing import Final
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

config = configparser.ConfigParser()
config.read('config.ini')
TOKEN: Final = config['botinfo']['token']
BOT_USERNAME: Final = config['botinfo']['bot_username']

# # Helper
# def checkArgs

# Commands

# /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hi! I am a bot that notifies you of new anime episodes based on your anime list. Run /help for a list of commands to get started.')

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('''You may add animes into your list, and if it is airing, I will let you know when a new episode is released! Please see below for commands:
    /help - Provides commands
    /list - View anime list
    /add [anime] - Add new anime to list
    /remove - Remove anime from list''')

# /list
async def view_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT anime_name FROM anime_lists WHERE user_id = ?', (user_id, ))
    anime_list = c.fetchall()
    conn.close()

    await update.message.reply_text(anime_list)

# /add
async def add_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    query = ' '.join(context.args)
    print(f'Searched for {query}')

    if not query.isalnum():
        print('Invalid anime name')
        await update.message.reply_text('Please enter a valid anime name.')
        return



    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT INTO anime_lists (user_id, anime_name) VALUES (?,?)', (user_id, query,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f'{query} added into your list!')

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


if __name__ == '__main__':
    print('Starting bot...')
    app = Application.builder().token(TOKEN).build()

    # Connect to database
    print('Initialising database...')
    db_name =  'database.db'
    conn = sqlite3.connect(db_name,check_same_thread=False)
    c = conn.cursor()
    print('Connected to database!')

    # # Create "users" table
    # sql = '''CREATE TABLE IF NOT EXISTS users (
    #             user_id INTEGER PRIMARY KEY,
    #             username TEXT
    #         )'''
    # c.execute(sql)

    # Create "anime_lists" table

    sql = '''CREATE TABLE IF NOT EXISTS anime_lists (
                user_id INTEGER,
                anime_name TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
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
    # app.add_handler(CommandHandler('remove', remove_anime_command))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    # Errors
    app.add_error_handler(error)

    # Polls the bot
    print('Polling...')
    app.run_polling(poll_interval=3)