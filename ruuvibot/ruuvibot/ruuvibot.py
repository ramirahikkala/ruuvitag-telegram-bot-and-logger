from cgitb import text
import logging
import schedule
import datetime
import time
import threading
import datetime
from zoneinfo import ZoneInfo
import asyncio

from pexpect import TIMEOUT
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from ruuvitag_sensor.ruuvi import RuuviTagSensor

import json
import sqlite3

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Jag känner en bot, hon heter Anna, Anna, heter hon",
    )


TIMEOUT = 5

SETTINGS = {}
ACTIVE_ALARMS = {}


def get_ruuvi_data():
    # List of macs of sensors which data will be collected
    # If list is empty, data will be collected for all found sensors
    # get_data_for_sensors will look data for the duration of timeout_in_sec

    ruuvi_tags = {}
    logging.info("Getting data for sensors")
    for ruuvi in SETTINGS["ruuvitags"]:
        ruuvi_tags[ruuvi["MAC"]] = ruuvi

    logging.info("Getting data for sensors " + str(ruuvi_tags))

    ruuvi_data = RuuviTagSensor.get_data_for_sensors([m for m in ruuvi_tags], TIMEOUT)

    logging.info("Got data for sensors " + str(ruuvi_data))

    # Append the name of the sensor to the data
    for ruuvi_data_point in ruuvi_data:
        logging.info("Apending name for " + ruuvi_data_point)
        ruuvi_data[ruuvi_data_point]["name"] = ruuvi_tags[ruuvi_data_point]["name"]
        ruuvi_data[ruuvi_data_point]["temperature_calibrated"] = "{:.2f}".format(
            ruuvi_data[ruuvi_data_point]["temperature"]
            + ruuvi_tags[ruuvi_data_point]["temperatureOffset"]
        )

    logging.info("Writing data to database")
    # Store in sqlite
    conn = sqlite3.connect("dbdata/temperature.sqlite")
    c = conn.cursor()
    # Create table if it does not exist
    c.execute(
        "CREATE TABLE IF NOT EXISTS ruuvi (datetime text, name text, temperature real, temperature_calibrated real, humidity real, pressure real)"
    )
    for ruuvi_data_point in ruuvi_data.values():
        c.execute(
            "INSERT INTO ruuvi VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.datetime.now(ZoneInfo("Europe/Helsinki")).strftime("%Y-%m-%dT%H:%M:%S %Z"),
                ruuvi_data_point["name"],
                ruuvi_data_point["temperature"],
                ruuvi_data_point["temperature_calibrated"],
                ruuvi_data_point["humidity"],
                ruuvi_data_point["pressure"],
            ),
        )
        conn.commit()
    conn.close()

    logging.info("Returning data")
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
        import traceback

        text = (
            "Ei saatu dataa. Exception: "
            + str(e)
            + " "
            + str(type(e) + ", " + str(traceback.format_exc()))
        )
        logging.error(e)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Get the data from sqlite database for all sensors in settings
    conn = sqlite3.connect("dbdata/temperature.sqlite")
    c = conn.cursor()

    text = ""

    for ruuvi in SETTINGS["ruuvitags"]:
        c.execute(
            "SELECT * FROM ruuvi where name = ? ORDER BY datetime DESC LIMIT 1",
            (ruuvi["name"],),
        )
        data = c.fetchone()
        # Calculate the time since the last update
        time_since_update = datetime.datetime.now() - datetime.datetime.strptime(
            data[0], "%Y-%m-%dT%H:%M:%S %Z"
        )

        if time_since_update > datetime.timedelta(minutes=15):
            text += f"{data[1]}: {data[3]} °C  ({int(time_since_update / datetime.timedelta(minutes=1)) } minuuttia sitten) \n"
        else:
            text += f"{data[1]}: {data[3]} °C \n"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def heating_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("dbdata/heatcontrol.sqlite")
    c = conn.cursor()
    c.execute("SELECT * FROM hour_prices ORDER BY DateTime DESC LIMIT 24")
    data = c.fetchall()

    pretty_data = [" ".join(map(str, tups)) for tups in data]

    pretty_data = json.dumps(pretty_data, indent=4, sort_keys=True)

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=str(pretty_data)
    )

    conn.close()


### Timer


async def alarm(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the alarm message."""

    global ACTIVE_ALARMS
    job = context.job

    for temperatureMonitor in SETTINGS["temperatureMonitoring"]:
        ruuvi_data = get_ruuvi_data()
        if temperatureMonitor["name"] in ruuvi_data:
            temperature = ruuvi_data[temperatureMonitor["name"]]["temperature"]
            if temperature < temperatureMonitor["min"]:
                await send_alarm(
                    context,
                    job,
                    temperatureMonitor["name"],
                    f"Lämpötilahälytys '{temperatureMonitor['name']}' lämpötila on {temperature} astetta, hälytysraja on {temperatureMonitor['min']} astetta",
                )
            elif temperature > temperatureMonitor["max"]:
                await send_alarm(
                    context,
                    job,
                    temperatureMonitor["name"],
                    text=f"Lämpötilahälytys '{temperatureMonitor['name']}' lämpötila on {temperature} astetta, hälytysraja on {temperatureMonitor['max']} astetta",
                )
            else:
                if ACTIVE_ALARMS[temperatureMonitor["name"]] == True:
                    await context.bot.send_message(
                        job.chat_id,
                        text=f"Lämpötila palasi normaaliksi. '{temperatureMonitor['name']}'lämpötila on {temperature} astetta",
                    )
                ACTIVE_ALARMS[temperatureMonitor["name"]] = False


async def send_alarm(context, job, name, text):
    global ACTIVE_ALARMS
    if ACTIVE_ALARMS[name] == False:
        await context.bot.send_message(job.chat_id, text=text)
    ACTIVE_ALARMS[name] = True


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
        # Monitor once in a minute
        due = 60

        job_removed = remove_job_if_exists(str(chat_id), context)
        context.job_queue.run_repeating(
            alarm, due, chat_id=chat_id, name=str(chat_id), data=due
        )

        text = "Lämpötilamonotorointi päällä!"
        if job_removed:
            text += " Old one was removed."
        await update.effective_message.reply_text(text)

    except (IndexError, ValueError):
        await update.effective_message.reply_text("Error")


async def unset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the job if the user changed their mind."""
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = (
        "Timer successfully cancelled!" if job_removed else "You have no active timer."
    )
    await update.message.reply_text(text)


### Timer end


def main():
    global SETTINGS
    global ACTIVE_ALARMS

    # Read settings file
    with open("settings.json") as json_file:
        settings = json.load(json_file)

    token = settings["telegram_token"]

    SETTINGS = settings

    for alarm in SETTINGS["temperatureMonitoring"]:
        ACTIVE_ALARMS[alarm["name"]] = False

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("full", full))
    application.add_handler(CommandHandler("l", temperature))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("h", heating_data))
    application.add_handler(CommandHandler("set", set_timer))
    application.add_handler(CommandHandler("unset", unset))

    # Update ruuvi data every 5 minutes
    schedule.every(5).minutes.do(get_ruuvi_data)

    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(1)

    schedule_thread = threading.Thread(target=run_schedule, daemon=True, name="schedule_thread")
    schedule_thread.start()

    application.run_polling()

if __name__ == "__main__":
    main()
