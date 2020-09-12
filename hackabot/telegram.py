import collections
import logging
import yaml
import threading
import subprocess, json
from pathlib import Path
from threading import Lock
from typing import Any, DefaultDict

import requests
import telebot
from telebot import types
import granula

logger = logging.getLogger('telegram')

money = {}
exp = {}
curr_case = {}

def get_full_name(user: telebot.types.User) -> str:
    name = user.first_name or ''
    if user.last_name:
        name += f' {user.last_name}'
    if user.username:
        name += f' @{user.username}'
    return name


def run_bot(config_path: str):
    config = granula.Config.from_path(config_path)
    locks: DefaultDict[Any, Lock] = collections.defaultdict(threading.Lock)
    token = config['telegram']['key']
    # load texts to response in quest
    button_text_path = config['telegram']['button_texts']
    with open(button_text_path, 'r') as yml_button_texts_file:
        button_texts = yaml.load(yml_button_texts_file, Loader=yaml.FullLoader)

    # load text of rules
    rules_path = config['telegram']['rules_text']
    with open(rules_path, 'r') as yml_rules_file:
        rules_text = yaml.load(yml_rules_file, Loader=yaml.FullLoader)


    bot = telebot.TeleBot(token)

    def _send(message: telebot.types.Message, response: str, keyboard = None):
        if keyboard is None:
            bot.send_message(chat_id=message.chat.id,
                             text=response,
                             parse_mode='html')
        else:
            bot.send_message(chat_id=message.chat.id,
                             text=response,
                             parse_mode='html',
                             reply_markup=keyboard)

    @bot.message_handler(commands=['start'])
    def _start(message: telebot.types.Message):
        with locks[message.chat.id]:
            guy = message.from_user.id
            print(guy)
            curr_case[guy] = -1
            money[guy] = 0
            exp[guy] = 0
            response = button_texts['start_text']
            keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            answers = []
            for i in button_texts['start_answers'].keys():
                answers.append(types.KeyboardButton(text=button_texts['start_answers'][i]['button_text']))
            keyboard.add(*answers)

            _send(message, response, keyboard)

    @bot.message_handler(commands=['rules'])
    def _rules(message: telebot.types.Message):
        with locks[message.chat.id]:

            response = rules_text['rules']

            _send(message, response)

    @bot.message_handler(commands=['FindMerchant'])
    def _find_merchant(message: telebot.types.Message):
        print("MERCHANT TEXT")
        print(message.text)
        item_name = message.text.replace('/FindMerchant', '').strip()
        if len(item_name) == 0:
            item_name = 'хлеб'
        else:
            item_name = item_name.split()[0]
        with locks[message.chat.id]:
            response_prefix = f'Вот где вы можете купить {item_name}' + '\n'

            site_path = 'https://api-common-gw.tinkoff.ru/search/api/v1/search_merchants'
            header_content = "'Content-Type: application/json'"
            # TODO here should be user geoposition
            data_raw_dict = {
                'geo_query':
                    {
                        'bottom_right': {
                            'lat': 55.73741399385868,
                            'lon': 37.56961595778349
                        },
                        'top_left': {
                            "lat": 55.742244061297384,
                            "lon": 37.56546389822844
                        }
                    },
                'query': item_name,
                'count': 5
            }

            query = f"curl --location --request POST '{site_path}' " + \
                    f"--header {header_content} " + \
                    f"--data-raw '{json.dumps(data_raw_dict, indent=2, ensure_ascii=False)}'"

            proc = subprocess.Popen(query, stdout=subprocess.PIPE, shell=True)
            (out, err) = proc.communicate()

            print(f'##### OUT {out}')
            print(f'####### ERR: {err}')

            response_suffix = ''
            out = out.decode('utf-8')
            out = out.replace('null', '""')
            out = out.replace('true', 'True')
            out = out.replace('false', 'False')
            out = eval(out)
            for ix, item in enumerate(out['search_result']['hits']):
                response_suffix += '\t'.join([str(ix + 1), item['mcc'][0] + ':', item['address']])
                response_suffix += '\n'

            response = f'{response_prefix}{response_suffix}'

            _send(message, response)

    def _maybe_you(username: str) -> str:
        return f'А может ты пидар, {username}'

    def _send_response(message: telebot.types.Message):
        print(f'current message: {message}')
        print(curr_case)
        response = None
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else '<unknown>'
        print(user_id)
        keyboard = None
        with locks[chat_id]:
            try:
                case = None
                prev_node = curr_case[user_id]
                if prev_node == -1:
                    block = 'start_answers'
                else:
                    block = 'answers_' + str(prev_node)
                for i in button_texts[block].keys():
                    if button_texts[block][i]['button_text'] == message.json['text']:
                        case = int(i[-1])
                        if button_texts[block][i]['next_node'] == 'None':
                            curr_case[user_id] = None
                        else:
                            curr_case[user_id] = int(button_texts[block][i]['next_node'])
                        money[user_id] = button_texts[block][i]['tinks']
                        exp[user_id] = button_texts[block][i]['exp']
                        if button_texts[block][i]['respose']:
                            response = button_texts[block][i]['respose'] + '\n' + button_texts['text_'+ str(curr_case[user_id])]
                        elif curr_case[user_id] > 0:
                            response = button_texts['text_' + str(curr_case[user_id])]
                        else:
                            response = None
                keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                answers = []
                print(curr_case[user_id], type(curr_case[user_id]))
                if curr_case[user_id] > -1:
                    for i in button_texts['answers_' + str(curr_case[user_id])].keys():
                        answers.append(types.KeyboardButton(text = button_texts['answers_'+ str(curr_case[user_id])][i]['button_text']))
                #else:
                #    response = None
                keyboard.add(*answers)


            except Exception as e:
                logger.exception(e)
                response = 'Произошла ошибка'

            if response is None:
                response = 'Ответа нет'

            _send(message, response, keyboard)

    @bot.message_handler()
    def send_response(message: telebot.types.Message):  # pylint:disable=unused-variable
        try:
            _send_response(message)
        except Exception as e:
            logger.exception(e)

    logger.info('Telegram bot started')
    bot.polling(none_stop=True)


def main():
    config_path = Path(__file__).parent / 'config.yaml'
    run_bot(config_path)


if __name__ == '__main__':
    while True:
        try:
            main()
        except requests.RequestException as e:
            logger.exception(e)
