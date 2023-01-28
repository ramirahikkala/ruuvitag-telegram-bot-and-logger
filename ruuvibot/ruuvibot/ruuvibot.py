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
MAC_IN = 'F2:9F:28:C0:09:3E'
MAC_OUT = 'C3:E8:BC:6E:13:8D'

async def full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # List of macs of sensors which data will be collected
    # If list is empty, data will be collected for all found sensors
    mac_in = 'F2:9F:28:C0:09:3E'
    mac_out = 'C3:E8:BC:6E:13:8D'
    macs = [mac_in, mac_out]
    # get_data_for_sensors will look data for the duration of timeout_in_sec
    

    datas = RuuviTagSensor.get_data_for_sensors(macs, TIMEOUT)

    text = json.dumps(datas, indent=4, sort_keys=True).replace('F2:9F:28:C0:09:3E', 'sisä').replace('C3:E8:BC:6E:13:8D', 'ulko')

    # Dictionary will have lates data for each sensor
    #print(datas['AA:2C:6A:1E:59:3D'])
    #print(datas['CC:2C:6A:1E:59:3D'])

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # List of macs of sensors which data will be collected
    # If list is empty, data will be collected for all found sensors
    mac_in = 'F2:9F:28:C0:09:3E'
    mac_out = 'C3:E8:BC:6E:13:8D'
    macs = [mac_in, mac_out]
    # get_data_for_sensors will look data for the duration of timeout_in_sec

    datas = RuuviTagSensor.get_data_for_sensors(macs, TIMEOUT)

    text = json.dumps(datas, indent=4, sort_keys=True).replace('F2:9F:28:C0:09:3E', 'sisä').replace('C3:E8:BC:6E:13:8D', 'ulko')

    if mac_in in datas and mac_out in datas:
        text = "Sisä: " + str(datas[mac_in]['temperature']) + ", ulko: " + str(datas[mac_out]['temperature'])
    elif mac_in in datas:
        text = "Sisä: " + str(datas[mac_in]['temperature'])
    elif mac_out in datas:
        text = "Ulko: " + str(datas[mac_out]['temperature'])

    # Dictionary will have lates data for each sensor
    #print(datas['AA:2C:6A:1E:59:3D'])
    #print(datas['CC:2C:6A:1E:59:3D'])

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

    MAC_IN = settings['indoor_mac']
    MAC_OUT = settings['outdoor_mac']

    application = ApplicationBuilder().token(token).build()
    
    application.add_handler(CommandHandler('full', full))
    application.add_handler(CommandHandler('l', temperature))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('h', heating_data))
    
    application.run_polling()



if __name__ == '__main__':
    main()
