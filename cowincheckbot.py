#!/usr/bin/env python3

import logging
from typing import Dict

from telegram import ReplyKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)
import requests
from datetime import date
import configparser

# Read configuration file. Config format available as dummy_config.ini
config = configparser.ConfigParser()        
config.read("config.ini")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

STATE, DISTRICT, PINCODE, DONE = range(4)
TG_MESSAGE_CHAR_LIMIT = 4096

done_markup = [
    ['Done'],
]

headers = {
    'User-Agent': config['API']['user-agent'] #User agent required in the header for public api to work.
}

def create_markup(choice, data) -> list:
    markup = []
    markup_str = ""
    i = 0
    t = []
    for a in data[choice+"s"]:
        markup_str = str(a[choice+'_id'])+". "+a[choice+'_name']
        t.append(markup_str)
        if (i%2) or i == len(data[choice+"s"])-1:
            markup.append(t.copy())
            t.clear()
        i = i+1
    return markup


def start(update: Update, context: CallbackContext) -> int:
    if(update.message.text == "New Search"):
        context.user_data.clear( )
    if('state_id' in context.user_data and 'district_id' in context.user_data):
        repeat_markup=[[context.user_data['state_name']+" : "+ context.user_data['district_name']], ['New Search', 'Done']]
        update.message.reply_text(
        "Do you want to repeat previous search? ",
        reply_markup=ReplyKeyboardMarkup(repeat_markup, one_time_keyboard=True, resize_keyboard=True),
        )
        return DISTRICT
    if('pincode' in context.user_data):
        repeat_markup=[["PINCODE: "+context.user_data['pincode']], ['New Search', 'Done']]
        update.message.reply_text(
        "Do you want to repeat previous search? ",
        reply_markup=ReplyKeyboardMarkup(repeat_markup, one_time_keyboard=True, resize_keyboard=True),
        )
        return STATE

    r = requests.get("https://cdn-api.co-vin.in/api/v2/admin/location/states", headers=headers)
    if(r.status_code != 200):
        send_as_markdown("API Error", update)
        return DONE
    
    states_data = r.json()
    state_markup = create_markup('state', states_data)

    update.message.reply_text(
        "Enter *PINCODE* or select *STATE*:",
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(state_markup, one_time_keyboard=True, resize_keyboard=True),
    )

    return STATE


def state_choice(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    context.user_data['state_id'], context.user_data['state_name'] = text.split(".")
    r = requests.get("https://cdn-api.co-vin.in/api/v2/admin/location/districts/"+context.user_data['state_id'], headers=headers)
    if(r.status_code != 200):
        send_as_markdown("API Error", update)
        return DONE

    districts_data = r.json()
    district_markup = create_markup('district', districts_data)
    update.message.reply_text(
        "Select district:",
        reply_markup=ReplyKeyboardMarkup(district_markup, one_time_keyboard=True, resize_keyboard=True),
    )
    return DISTRICT

def format_slots_output(centers):
    r = ""
    i=1
    available_centers = []
    # Filter centers with available_cpacity > 0
    for center in centers:
        for session in center['sessions']:
            if session['available_capacity']:
                if center not in available_centers:
                    available_centers.append(center)
    # Prepare the markup for output                
    for center in available_centers:
        if(i!=1):
            r+="\n"
        r+=str(i)+"\. *`"+center['name']+"`* "+str(session['min_age_limit'])+"\+ _"+center['fee_type']+"_\n"
        for session in center['sessions']:
            if session['available_capacity']:
                r+="\t\t`"+session['date']+"` "+session['vaccine']+" `"+str(session['available_capacity'])+"` slots\n"
        i+=1
    return r

def filter_by_pincode(centers, pincode):
    new_center = []
    for center in centers:
        if center['pincode'] == pincode:
            new_center.append(center)
    return new_center

def split_text(message):
    split_pos = []
    newline_pos = 0
    last_pos = 0
    for i in range(1, len(message)):
        if message[i] == '\n':
            newline_pos = i
        if i%(TG_MESSAGE_CHAR_LIMIT-1) == 0:
            split_pos.append((last_pos, newline_pos))
            last_pos = newline_pos
    split_pos.append((last_pos, len(message)-1))
    
    split_list = []
    for a,b in split_pos:
        split_list.append(message[a:b])
    return split_list

def send_as_markdown(message, update):
    update.message.reply_text(
            message,
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(done_markup, one_time_keyboard=True, resize_keyboard=True)
    )
    return

def send_instruction(update):
    update.message.reply_text(
            "Visit https://selfregistration.cowin.gov.in/ to book your slots.\nHappy vaccination!",
            reply_markup=ReplyKeyboardMarkup(done_markup, one_time_keyboard=True, resize_keyboard=True)
    )
    return

def send_info(update, date):
    update.message.reply_text(
            "Slots for next *7* days from *"+date+"* :",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(done_markup, one_time_keyboard=True, resize_keyboard=True)
    )
    return


def district_choice(update: Update, context: CallbackContext) -> int:
    today = date.today().strftime("%d/%m/%Y")
    text = update.message.text
    if not 'district_id' in context.user_data:
        context.user_data['district_id'], context.user_data['district_name'] = text.split(".")
    r = requests.get("https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict?district_id="+context.user_data['district_id']+"&date="+today, headers=headers)
    if(r.status_code != 200):
        send_as_markdown("API Error", update)
        return DONE
        
    centers = r.json()['centers']
    center_list = format_slots_output(centers)
    if len(center_list) <= TG_MESSAGE_CHAR_LIMIT:
        if not len(center_list):
            send_as_markdown("No slots available", update)
        else:
            send_info(update, today)
            send_as_markdown(center_list, update)
            send_instruction(update)
        return DONE
    else:
        context.user_data['centers'] = centers
        update.message.reply_text(
            "Too many results! Enter pincode to filter:",
        )
        return PINCODE

def direct_pincode_choice(update: Update, context: CallbackContext) -> int:
    today = date.today().strftime("%d/%m/%Y")
    text = update.message.text
    if not 'pincode' in context.user_data:
        context.user_data['pincode'] = text.strip()
    r = requests.get("https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByPin?pincode="+context.user_data['pincode']+"&date="+today, headers=headers)
    if(r.status_code != 200):
        send_as_markdown("API Error", update)
        return DONE
        
    centers = r.json()['centers']
    center_list = format_slots_output(centers)
    if len(center_list) <= TG_MESSAGE_CHAR_LIMIT:
        if not len(center_list):
            send_as_markdown("No slots available", update)
        else:
            send_info(update, today)
            send_as_markdown(center_list, update)
            send_instruction(update)
        return DONE
    else:
        message_chunks = split_text(center_list)
        if(len(message_chunks)):
            send_info(update, today)    
        for message in message_chunks:
            if len(message):
                send_as_markdown(message, update)
        send_instruction(update)
        return DONE

        
def pincode_choice(update: Update, context: CallbackContext) -> int:
    today = date.today().strftime("%d/%m/%Y")
    pincode = int(update.message.text)
    if(context.user_data['centers']):
        center_list = format_slots_output(filter_by_pincode(context.user_data['centers'], pincode))

    if len(center_list) <= TG_MESSAGE_CHAR_LIMIT:
        if not len(center_list):
            send_as_markdown("No slots available", update)
        else:
            send_info(update, today)
            send_as_markdown(center_list, update)
            send_instruction(update)
        return DONE
    else:
        # Split messages it TG_MESSAGE_CHAR_LIMIT sized chunks
        message_chunks = split_text(center_list)
        if(len(message_chunks)):
            send_info(update, today)    
        for message in message_chunks:
            if len(message):
                send_as_markdown(message, update)
        send_instruction(update)
        return DONE


def done(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        f"Thank you !\n\nIf you want to start a new search, Press /start again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END




def main() -> None:
    tg_config = config['TELEGRAM']
    # Create the Updater and pass it your bot's token.
    updater = Updater(tg_config['token'])

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Add conversation handler with the states CHOOSING, TYPING_CHOICE and TYPING_REPLY
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STATE: [
                MessageHandler(
                    Filters.regex('^\d+\.\s[\s\w]+$'), state_choice
                ),
                MessageHandler(
                    Filters.regex('^\d{6}$'), direct_pincode_choice
                ),
                MessageHandler(
                    Filters.regex('^PINCODE: \d{6}$'), direct_pincode_choice
                ),
                MessageHandler(
                    Filters.regex('^New Search$'), start
                ),
                MessageHandler(
                    Filters.regex('^Done$'), done
                )
            ],
            DISTRICT: [
                MessageHandler(
                    Filters.regex('^\d+\.\s[\s\w]+$'), district_choice
                ),
                MessageHandler(
                    Filters.regex('^[\s\w]+\s:\s[\s\w]+$'), district_choice
                ),
                MessageHandler(
                    Filters.regex('^New Search$'), start
                ),
                MessageHandler(
                    Filters.regex('^Done$'), done
                )
            ],
            PINCODE: [
                MessageHandler(
                    Filters.regex('^\d{6}$'), pincode_choice
                )
            ],
            DONE: [
                MessageHandler(
                    Filters.regex('^Done$'),done
                )
            ],
        },
        fallbacks=[MessageHandler(Filters.regex('^Start$'), start)],
    )

    dispatcher.add_handler(conv_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()

