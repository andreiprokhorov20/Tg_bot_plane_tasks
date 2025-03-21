import telebot
from telebot import types
from pymongo import MongoClient
from datetime import datetime
from dateutil import parser  # Для парсинга дат
from bson import ObjectId

TOKEN = '7968336951:AAEEdd0gI4lV6unza548cnz19Tfo_AwmcXc'
bot = telebot.TeleBot(TOKEN)

# Подключение к MongoDB
client = MongoClient('mongodb://localhost:27017/')  # Если БД на другом сервере - укажите свой URL
db = client.task_manager  # Создаем/выбираем базу данных
tasks_collection = db.tasks  # Коллекция для хранения задач

@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        '➕ Добавить задачу',
        '📝 Список задач',
        '❌ Удалить задачу',
        '✏️ Редактировать задачу',
        '✅ Изменить статус'
    ]
    markup.add(*buttons)
    
    # Создаем запись о пользователе при первом запуске
    user_data = {
        'user_id': message.chat.id,
        'first_launch': datetime.now()
    }
    db.users.update_one(
        {'user_id': message.chat.id},
        {'$setOnInsert': user_data},
        upsert=True
    )
    
    bot.send_message(
        message.chat.id,
        "Привет! Я твой планировщик задач.\nВыбери действие:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '➕ Добавить задачу')
def add_task(message):
    msg = bot.send_message(
        message.chat.id,
        "Введите задачу и дату в формате:\n"
        "Купить молоко / 2024-03-20 18:00"
    )
    bot.register_next_step_handler(msg, process_task_input)
    
def process_task_input(message):
    try:
        task_text, deadline_str = message.text.split(' / ', 1)
        deadline = parser.parse(deadline_str)  # Парсим дату из строки
        
        # Создаем документ задачи
        task = {
            'user_id': message.chat.id,
            'text': task_text,
            'deadline': deadline,
            'created_at': datetime.now(),
            'is_completed': False
        }
        
        # Вставляем задачу в коллекцию
        result = tasks_collection.insert_one(task)
        bot.send_message(
            message.chat.id, 
            f"✅ Задача '{task_text}' добавлена!\nID задачи: {result.inserted_id}"
        )
        
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный формат! Используйте:\n"
            "Текст задачи / ГГГГ-ММ-ДД ЧЧ:ММ"
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка: {str(e)}"
        )

@bot.message_handler(func=lambda message: message.text == '📝 Список задач')
def show_tasks(message):
    try:
        now = datetime.now()
        tasks = list(tasks_collection.find({'user_id': message.chat.id}))
        
        if not tasks:
            bot.send_message(message.chat.id, "📭 Список задач пуст!")
            return

        # Разделяем задачи на категории
        overdue = []
        completed = []
        in_progress = []

        for task in tasks:
            if task['is_completed']:
                completed.append(task)
            else:
                delta = task['deadline'] - now
                if delta.days < 0:
                    overdue.append(task)
                else:
                    in_progress.append(task)

        # Сортируем задачи внутри категорий
        overdue.sort(key=lambda x: x['deadline'])
        in_progress.sort(key=lambda x: x['deadline'])

        # Формируем ответ
        response = []
        
        if overdue:
            response.append("\n🔴 Просроченные задачи:")
            for task in overdue:
                delta = now - task['deadline']
                response.append(
                    f"▫️ {task['text']}\n"
                    f"   ID: {task['_id']}\n"
                    f"   Просрочено на: {delta.days} дней\n"
                    f"   Исходный дедлайн: {task['deadline'].strftime('%d.%m.%Y %H:%M')}"
                )
                response.append("")

        if completed:
            response.append("\n🟢 Выполненные задачи:")
            for task in completed:
                response.append(
                    f"▫️ {task['text']}\n"
                    f"   ID: {task['_id']}\n"
                    f"   Дедлайн: {task['deadline'].strftime('%d.%m.%Y %H:%M')}"
                )
                response.append("")

        if in_progress:
            response.append("\n🟡 Активные задачи:")
            for task in in_progress:
                delta = task['deadline'] - now
                hours, remainder = divmod(delta.seconds, 3600)
                minutes = remainder // 60
                time_left = f"{delta.days}д {hours}ч {minutes}м"
                
                response.append(
                    f"▫️ {task['text']}\n"
                    f"   ID: {task['_id']}\n"
                    f"   Дедлайн: {task['deadline'].strftime('%d.%m.%Y %H:%M')}\n"
                    f"   Осталось времени: {time_left}"
                )
                response.append("")

        if not response:
            bot.send_message(message.chat.id, "📭 Список задач пуст!")
            return

        # Отправляем частями если сообщение слишком длинное
        full_response = "\n".join(response)
        if len(full_response) > 4096:
            for x in range(0, len(full_response), 4096):
                bot.send_message(message.chat.id, full_response[x:x+4096])
        else:
            bot.send_message(message.chat.id, full_response)

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == '✏️ Редактировать задачу')
def edit_task_prompt(message):
    msg = bot.send_message(message.chat.id, "Введите ID задачи для редактирования:")
    bot.register_next_step_handler(msg, process_edit_id)

def process_edit_id(message):
    try:
        task_id = ObjectId(message.text.strip())
        msg = bot.send_message(message.chat.id, "Введите новый текст задачи:")
        bot.register_next_step_handler(msg, lambda m: process_edit_text(m, task_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: Некорректный ID задачи")

def process_edit_text(message, task_id):
    try:
        new_text = message.text.strip()
        result = tasks_collection.update_one(
            {'_id': task_id, 'user_id': message.chat.id},
            {'$set': {'text': new_text}}
        )
        
        if result.modified_count > 0:
            bot.send_message(message.chat.id, "✅ Текст задачи успешно обновлен!")
        else:
            bot.send_message(message.chat.id, "❌ Задача не найдена или нет прав для редактирования")
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == '✅ Изменить статус')
def toggle_status_prompt(message):
    msg = bot.send_message(message.chat.id, "Введите ID задачи для изменения статуса:")
    bot.register_next_step_handler(msg, process_toggle_status)

def process_toggle_status(message):
    try:
        task_id = ObjectId(message.text.strip())
        task = tasks_collection.find_one({'_id': task_id, 'user_id': message.chat.id})
        
        if not task:
            bot.send_message(message.chat.id, "❌ Задача не найдена")
            return
            
        new_status = not task['is_completed']
        tasks_collection.update_one(
            {'_id': task_id, 'user_id': message.chat.id},
            {'$set': {'is_completed': new_status}}
        )
        
        status_text = "✅ Выполнена" if new_status else "⏳ В процессе"
        bot.send_message(message.chat.id, f"Статус задачи обновлен: {status_text}")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")


@bot.message_handler(func=lambda message: message.text == '❌ Удалить задачу')
def delete_task(message):
    msg = bot.send_message(
        message.chat.id,
        "Введите дату для удаления задач (ГГГГ-ММ-ДД):"
    )
    bot.register_next_step_handler(msg, process_delete_input)

def process_delete_input(message):
    try:
        date_str = message.text.strip()
        date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Удаляем задачи по дате и user_id
        result = tasks_collection.delete_many({
            'user_id': message.chat.id,
            'deadline': {'$gte': date.replace(hour=0, minute=0, second=0), '$lt': date.replace(hour=23, minute=59, second=59)}
        })
        
        if result.deleted_count > 0:
            bot.send_message(message.chat.id, f"✅ Удалено {result.deleted_count} задач на {date_str}!")
        else:
            bot.send_message(message.chat.id, "❌ Задач на эту дату не найдено!")
            
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД."
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

bot.polling()
