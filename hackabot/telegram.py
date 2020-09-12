import collections
import logging
import yaml
import threading
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

    def _maybe_you(username: str) -> str:
        return f'А может ты пидар, {username}'

    def _send_response(message: telebot.types.Message):
        print(f'current message: {message}')
        chat_id = message.chat.id
        user_id = str(message.from_user.id) if message.from_user else '<unknown>'

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
