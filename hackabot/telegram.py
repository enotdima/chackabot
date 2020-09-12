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
    button_text_path = config['telegram']['button_texts']
    with open(button_text_path, 'r') as yml_button_texts_file:
        button_texts = yaml.load(yml_button_texts_file, Loader=yaml.FullLoader)
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

            response = button_texts['start_text']
            keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            answers = []
            for i in button_texts['start_answers'].keys():
                answers.append(types.KeyboardButton(text=button_texts['start_answers'][i]))
            keyboard.add(answers)

            _send(message, response, keyboard)

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
        chat_id = message.chat.id
        #user_id = str(message.from_user.id) if message.from_user else '<unknown>'

        with locks[chat_id]:
            try:
                response = button_texts['text_2']#message.json.text
                keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                answers = []
                for i in button_texts['answers_2'].keys():
                    answers.append(types.KeyboardButton(text = button_texts['answers_2'][i]))
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
