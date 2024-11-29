import telebot
import json
from .database import DataBase
from datetime import datetime
import threading
import time

class ReminderScheduler:
    def __init__(self, bot, database):
        self.bot = bot
        self.database = database
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while self.running:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.check_reminders(current_time)
            time.sleep(1)  #тик в сек хз как на большом объеме будет

    def check_reminders(self, current_time):
        query = """
            SELECT id_reminder, id_user, name_reminder, text_reminder FROM reminders
            WHERE date_reminder <= %s
        """
        reminders = self.database.read_database(query=query, params=(current_time,))
        
        for reminder in reminders:
            reminder_id, id_user, name_reminder, text_reminder = reminder
            
            user_query = "SELECT chat_id FROM users WHERE id_user = %s"
            user_data = self.database.read_database(query=user_query, params=(id_user,))
            
            if user_data:
                chat_id = user_data[0][0]
                try:
                    self.bot.send_message(chat_id, f"Напоминание: {name_reminder}\nОписание: {text_reminder}")
                except telebot.apihelper.ApiTelegramException as e:
                    print(f"Ошибка при отправке сообщения пользователю {id_user}: {e}")

                delete_query = "DELETE FROM reminders WHERE id_reminder = %s"
                self.database.insert_database(query=delete_query, params=(reminder_id,))
            else:
                print(f"Пользователь с id_user {id_user} не найден.")

    def stop(self):
        self.running = False
        self.thread.join()

class ReminderBot():
    def __init__(self):
        with open(r'other_files\config.json') as cfg:
            data = json.load(cfg) 
        self.bot = telebot.TeleBot(data['token'])
        self.database = DataBase(data['db_name'], data['user'], data['password'], data['host'])
        self.user_states = {}
        self.reminder_dict = {}
        self.reminder_scheduler = ReminderScheduler(self.bot, self.database)

    def handler_commands(self):
        @self.bot.message_handler(commands=['start'])
        def start(message):
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            button_view_reminder = telebot.types.KeyboardButton(text='Посмотреть напоминания')
            button_create_reminder = telebot.types.KeyboardButton(text='Создать напоминание')
            markup.row(button_create_reminder)
            markup.row(button_view_reminder)
            welcome_text = (
                f"<b>Привет, {message.from_user.first_name}!</b>\n"
                "Я ваш личный помощник, который поможет вам управлять напоминаниями.\n"
                "С помощью меня вы можете:\n"
                "- <b>Создавать</b> новые напоминания, чтобы не забыть важные дела.\n"
                "- <b>Просматривать</b> текущие напоминания.\n"
                "Просто выберите нужный вариант из меню ниже, и я помогу вам!"
            )

            #добавление нового пользователя в бд, чтоб дубликатов не было, проверку сделал
            ids_users = self.database.read_database(query="select chat_id from users where chat_id = %s", params=(message.chat.id ,))
            if not ids_users:
                self.database.insert_database(query="insert into users (id_user, chat_id) values (default, %s)", params=(message.chat.id ,))

            self.bot.send_message(message.chat.id, text=welcome_text, reply_markup=markup, parse_mode='HTML')

        @self.bot.message_handler(func=lambda message: message.text == 'Посмотреть напоминания')
        def view_reminder(message):
            markup = telebot.types.InlineKeyboardMarkup()
            query = """
                select id_reminder, name_reminder, text_reminder, date_reminder from reminders
                where id_user = %s
            """
            id_user = self.database.read_database(query='SELECT id_user FROM users WHERE chat_id = %s', params=(message.chat.id,))[0][0]
            data_reminder = self.database.read_database(query=query, params=(id_user, ))
            for data in data_reminder:
                markup.add(telebot.types.InlineKeyboardButton(text=data[1], callback_data=data[0]))
                print(data)
            self.bot.send_message(message.chat.id, 'Напоминания:', reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data.isdigit()) 
        def callback_query(call):
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(text='Удалить', callback_data=f'delete {call.data}'))
            id_user = self.database.read_database(query='SELECT id_user FROM users WHERE chat_id = %s', params=(call.message.chat.id,))[0][0]
            query = """
                select name_reminder, text_reminder, date_reminder from reminders
                where id_user = %s and id_reminder = %s
            """
            name_reminder, text_reminder, date_reminder = self.database.read_database(query=query, params=(id_user, call.data))[0]
            text_message = f"<b>Название:</b>\n{name_reminder}\n<b>Описание:</b>\n{text_reminder}\n<b>Время - </b>{date_reminder}"
            self.bot.send_message(call.message.chat.id, text=text_message, parse_mode='HTML', reply_markup=markup)

        #Дек для удаление напоминания по каллбэку
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('delete '))
        def delete_reminder(call):
            reminder_id = call.data.split(' ')[1]
            
            query = """
                DELETE FROM reminders
                WHERE id_reminder = %s
            """
            self.database.insert_database(query=query, params=(reminder_id, ))
            
            self.bot.answer_callback_query(call.id, text="Напоминание удалено.")
            
            view_reminder(call.message)

        #Создание напоминания
        @self.bot.message_handler(func=lambda message: message.text == 'Создать напоминание')
        def view_reminder(message):
            self.user_states[message.chat.id] = 'create_reminder_name'
            self.bot.send_message(message.chat.id, 'Напиши название напоминания:')
        
        #получаем имя
        @self.bot.message_handler(func=lambda message: self.user_states.get(message.chat.id) == 'create_reminder_name')
        def get_name_reminder(message):
            name = message.text
            if len(name) < 100:
                self.reminder_dict[message.chat.id] = {'name':name, 'text':None, 'date':None} 
                self.bot.send_message(message.chat.id, 'Теперь напиши текст напоминания:')
                self.user_states[message.chat.id] = 'create_reminder_text'
            else:
                self.bot.send_message(message.chat.id, 'Название слишком большое\nНе больше 100 символов')
        
        #получаем текст
        @self.bot.message_handler(func=lambda message: self.user_states.get(message.chat.id) == 'create_reminder_text')
        def get_text_reminder(message):
            self.reminder_dict[message.chat.id]['text'] = message.text
            self.bot.send_message(message.chat.id, 'Теперь введи время в данном формате\n<b>2024-12-31 23:59:00</b>', parse_mode='HTML')
            self.user_states[message.chat.id] = 'create_reminder_date'
        
        #получаем date-time
        @self.bot.message_handler(func=lambda message: self.user_states.get(message.chat.id) == 'create_reminder_date')
        def get_date_reminder(message):
            date_input = message.text.strip()
            try:
                date_time = datetime.strptime(date_input, '%Y-%m-%d %H:%M:%S')
                
                self.reminder_dict[message.chat.id]['date'] = date_time.strftime('%Y-%m-%d %H:%M:%S')

                query = '''
                    INSERT INTO reminders (id_reminder, id_user, name_reminder, text_reminder, date_reminder)
                    VALUES (default, %s, %s, %s, %s)
                '''
                params = (
                    self.database.read_database(query='SELECT id_user FROM users WHERE chat_id = %s', params=(message.chat.id,))[0][0],
                    self.reminder_dict[message.chat.id]['name'], 
                    self.reminder_dict[message.chat.id]['text'],
                    self.reminder_dict[message.chat.id]['date']
                )

                self.database.insert_database(query=query, params=params)
                self.bot.send_message(message.chat.id, 'Напоминание создано')
                del self.reminder_dict[message.chat.id]
                del self.user_states[message.chat.id]

            except ValueError:
                self.bot.send_message(message.chat.id, 'Неправильный ввод, введите дату-время в формате\n<b>2023-11-02 15:30:00</b>', parse_mode='HTML')
            
    def run(self):
        self.handler_commands()
        self.bot.polling(non_stop=True)
        