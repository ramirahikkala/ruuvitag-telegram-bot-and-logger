from cgitb import text
import logging
import re

from pexpect import TIMEOUT
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from ruuvitag_sensor.ruuvi import RuuviTagSensor

import json
import sqlite3

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Jag känner en bot, hon heter Anna, Anna, heter hon")

TIMEOUT = 2

# Dictionary of macs and names of sensors
MACS= {}

def get_ruuvi_data():
    # List of macs of sensors which data will be collected
    # If list is empty, data will be collected for all found sensors
    # get_data_for_sensors will look data for the duration of timeout_in_sec
    ruuvi_data = RuuviTagSensor.get_data_for_sensors([m['MAC'] for m in MACS], TIMEOUT)

    for m in MACS:
        if m['MAC'] in ruuvi_data:
            ruuvi_data[m['MAC']] = m.pop('name')
    
    return ruuvi_data

def to_json(ruuvi_data: dict) -> str:
    """Converts the given Ruuvi data into JSON.
    
    Parameters
    ----------
    ruuvi_data : dict
        A dictionary containing the Ruuvi data
    
    Returns
    -------
    str
        A JSON string containing the Ruuvi data
    """
    
    return json.dumps(ruuvi_data, indent=4, sort_keys=True)

def to_json(ruuvi_data):
    
    return json.dumps(ruuvi_data, indent=4, sort_keys=True)


async def full(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        
        datas = get_ruuvi_data()
        text = to_json(datas)
        
    except Exception as e:
        text = "Ei saatu dataa. Exception: " + str(e) + " " + str(type(e))
        logging.error(e)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        datas = get_ruuvi_data()           

        # Get only temperature from data
        for mac in datas:
            datas[mac] = datas[mac]['temperature']


        text = to_json(datas)     
        
    except Exception as e:
        text = "Ei saatu dataa. Exception: " + str(e) + " " + str(type(e))
        logging.error(e)        

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def heating_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('dbdata/heatcontrol.sqlite')
    c = conn.cursor()
    c.execute('SELECT * FROM hour_prices ORDER BY DateTime DESC LIMIT 24')
    data = c.fetchall()

    pretty_data = [' '.join(map(str,tups)) for tups in data]

    pretty_data = json.dumps(pretty_data, indent=4, sort_keys=True)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=str(pretty_data))
    
    conn.close()

### Timer

async def alarm(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the alarm message."""
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"Beep! {job.data} seconds are over!")


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    if context is not None and context.job_queue is not None:
        current_jobs = context.job_queue.get_jobs_by_name(name)
        if not current_jobs:
            return False
        for job in current_jobs:
            job.schedule_removal()
    return True


async def set_timer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a job to the queue."""
    chat_id = update.effective_message.chat_id
    try:
        # args[0] should contain the time for the timer in seconds
        due = float(context.args[0])
        if due < 0:
            await update.effective_message.reply_text("Sorry we can not go back to future!")
            return

        job_removed = remove_job_if_exists(str(chat_id), context)
        context.job_queue.run_repeating(alarm, due, chat_id=chat_id, name=str(chat_id), data=due)

        text = "Timer successfully set!"
        if job_removed:
            text += " Old one was removed."
        await update.effective_message.reply_text(text)

    except (IndexError, ValueError):
        await update.effective_message.reply_text("Usage: /set <seconds>")


async def unset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the job if the user changed their mind."""
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = "Timer successfully cancelled!" if job_removed else "You have no active timer."
    await update.message.reply_text(text)


### Timer end

def main():
    # Read settings file
    with open('settings.json') as json_file:
        settings = json.load(json_file)
    
    token = settings['telegram_token']

    global MACS
    MACS = settings['MACs']

    application = ApplicationBuilder().token(token).build()
    
    application.add_handler(CommandHandler('full', full))
    application.add_handler(CommandHandler('l', temperature))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('h', heating_data))
    application.add_handler(CommandHandler("set", set_timer))
    application.add_handler(CommandHandler("unset", unset))

    
    application.run_polling()



if __name__ == '__main__':
    main()
