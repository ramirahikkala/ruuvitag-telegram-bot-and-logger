from cgitb import text
import logging

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
    macs = [m['MAC'] for m in MACS]
    # get_data_for_sensors will look data for the duration of timeout_in_sec
    return RuuviTagSensor.get_data_for_sensors(macs, TIMEOUT)

def replace_mac_with_name(datas):    

    text = json.dumps(datas, indent=4, sort_keys=True)
    
    for m in MACS:
        text = text.replace(m['MAC'], m['name'])
    
    return text


async def full(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        
        datas = get_ruuvi_data()
        text = replace_mac_with_name(datas)
        
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

        text = replace_mac_with_name(datas)     
        
    except:
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

def main():
    # Read settings file
    with open('settings.json') as json_file:
        settings = json.load(json_file)
    
    token = settings['telegram_token']

    MACS = settings['macs']

    application = ApplicationBuilder().token(token).build()
    
    application.add_handler(CommandHandler('full', full))
    application.add_handler(CommandHandler('l', temperature))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('h', heating_data))
    
    application.run_polling()



if __name__ == '__main__':
    main()
