from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from html import escape
import asyncio
import logging
import aiosqlite
import os
import csv
from dotenv import load_dotenv
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain_gigachat import GigaChat
from random import randint

load_dotenv()

# Получаем значения переменных окружения
token = os.getenv('BOT_TOKEN')
SecretKey = os.getenv('TOKEN_GIGACHAT')

giga = GigaChat(credentials=SecretKey,
                model='GigaChat:latest',
                verify_ssl_certs=False
                )

#Определим состояния:
class States(StatesGroup):
    logged_user = State()
    chat = State()

class SomeMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if data['event_update'].message.text != '/start':
            id = data['event_update'].message.chat.id
            async with aiosqlite.connect('users.db') as db:
                async with db.execute("SELECT id FROM users WHERE id = ?", (id,)) as cursor:
                    if await cursor.fetchone() is None:
                        await bot.send_message(chat_id=id, text='Вы не зарегистрированы! Зарегистрируйтесь, используя команду /start.')
                        return
        result = await handler(event, data)
        return result
    
#Включаем логирование
logging.basicConfig(force=True, level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

user_messages = dict()

def show_keyboard():
    kb_list = [
        [KeyboardButton(text="Дневник эмоций")],
        [KeyboardButton(text="Тестирование эмоционального интеллекта")],
        [KeyboardButton(text="Советы и упражнения")],
        [KeyboardButton(text="Ежедневные задания")]
      ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True, input_field_placeholder="Воспользуйтесь меню:")
    return keyboard

@dp.message(CommandStart(), State(None))
async def cmd_start(message: Message, state: FSMContext):
    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,)) as cursor:
            if await cursor.fetchone() is None:
                await cursor.execute('INSERT INTO users (id, statusrem) VALUES (?, ?)', (message.from_user.id, True))
                await db.commit()
                await state.set_state(States.logged_user)
                await message.answer(f'{message.from_user.first_name}, вы успешно зарегистрированы!', reply_markup=show_keyboard())
            else:
                await state.set_state(States.logged_user)
                await message.answer(f'Привет, {message.from_user.first_name}! Вы уже зарегистрированы!', reply_markup=show_keyboard())


### Обработка команд (/menu, /developers)
@dp.message(Command("menu"), States.logged_user)
async def cmd_menu(message: Message, state: FSMContext):
    await message.answer('Выберите, что вас интересует!', reply_markup=show_keyboard())

@dp.message(Command("developers"), States.logged_user)
async def cmd_developers(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text='Информация о боте', callback_data='content')
    builder.button(text='Информация о разработчиках', callback_data='about')
    builder.adjust(1, 1)
    await message.answer('Выберите, что вас интересует!', reply_markup=builder.as_markup())

@dp.callback_query(F.data == 'content', States.logged_user)
async def send_content(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Стек: python, aiogram3, GigaChat AI.\nGitHub: https://github.com/Aksile2/telegram_ei_bot", reply_markup=show_keyboard())

@dp.callback_query(F.data == 'about', States.logged_user)
async def send_about(call_or_message, state: FSMContext):
    if type(call_or_message) == Message:
      objectmes = call_or_message
    else:
      objectmes = call_or_message.message
    await objectmes.answer("Информация о разработчиках\n1) Хомин Максим Вячеславович, БИВ235. \nPython Backend разработчик.\n \
2) Петросян Гурген Аликович, БИВ235.\n3D-моделлер. Python-разработчик.", reply_markup=show_keyboard())


### Дневник эмоций
@dp.message(F.text.lower().in_({'дневник эмоций'}), States.logged_user)
async def cmd_emotions(message: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text='Начать диалог', callback_data='start_chat')
    await message.answer('Это дневник эмоций - здесь вы можете делиться \
своими событиями и эмоциями, вызванными этими событиями. Чат-бот с ИИ поможет вам лучше справиться \
с эмоциями и грамотно проанализирует ситуацию. \nДля окончания диалога скажите "Стоп".', reply_markup=builder.as_markup())

@dp.callback_query(F.data == 'start_chat', States.logged_user)
async def start_chat(call: CallbackQuery, state: FSMContext):
    kb_list = [[KeyboardButton(text="стоп")]]
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Если хотите завершить диалог, воспользуйтесь меню:")
    await call.message.answer('Диалог начат.', reply_markup=keyboard)
    await state.set_state(States.chat)

# Хендлер для сообщений в состоянии ChatState.chat
@dp.message(States.chat)
async def process_chat(message: Message, state: FSMContext):
    text = message.text.lower()
    user_id = message.from_user.id
    # Проверяем на завершение диалога
    if text == "стоп":
        await message.answer("Диалог завершен.", reply_markup=show_keyboard())
        await state.set_state(States.logged_user)  # Сбрасываем состояние обратно в None (деактивируем диалог)

    # Проверяем на команды (если сообщение начинается с '/')
    if text.startswith("/"):
        await message.answer('Чтобы завершить диалог, напишите "стоп"')

    # Добавляем текст сообщения в список
    if user_id not in user_messages.keys():
        user_messages[user_id] = [SystemMessage(
            content="Ты — бот-эксперт по эмоциональному интеллекту, \
задача которого — помогать пользователям осознавать и понимать свои эмоции и эмоции других людей. Твоя роль заключается в том, чтобы:\
Слушать и Эмпатировать: Внимательно выслушивай пользователей, предоставляя пространство для выражения их переживаний. Отвечай с пониманием, чтобы они чувствовали себя услышанными и поддержанными.\
Анализировать Ситуации: Получая информацию о конкретных событиях и связанных с ними эмоциях, помогай пользователю глубже понять их чувства. Заботься о том, чтобы анализировать ситуации с разных точек зрения, выявляя возможные подкоренные причины эмоций.\
Объяснять Эмоции: Используй знания об эмоциональном интеллекте, чтобы разъяснять, как различные эмоции могут влиять на поведение и реакции. Объясняй основные эмоции и их проявления, а также моменты, когда они могут возникать.\
Предлагать Советы: Дай практические рекомендации по улучшению эмоционального интеллекта. Это может включать техники саморегуляции, стратегии управления стрессом, методы улучшения коммуникации и развития эмпатии.\
Поддерживать безоценочность: Создавай безопасное пространство для общения, где пользователи не будут бояться осуждения. Поощряй открытое обсуждение их эмоций и реакций.\
Обучать Инструментам: Делись полезными инструментами и методами, которые помогут пользователям развивать эмоциональный интеллект — такие как активное слушание, упражнения по саморефлексии и техники медитации.\
Обращаться к Разным Ситуациям: Будь готов обсуждать широкий спектр тем — от личных отношений до профессиональной среды, уделяя внимание различным контекстам и их влиянию на эмоции.\
Поддерживать Открытость и Доступность: Будь открытым ко всем вопросам и переживаниям. Напоминай пользователям, что их чувства важны, и каждый имеет право на их выражение.\
Твоя цель — научить пользователей лучше понимать и управлять своими эмоциями, улучшая их качество жизни и межличностные отношения. Помогай им становиться более эмоционально грамотными, делая акцент на росте и развитии.")]
    user_messages[user_id].append(HumanMessage(content=text))
    bot_answer = giga.invoke(user_messages[user_id]).content
    user_messages[user_id].append(AIMessage(content=bot_answer))

    if text != 'стоп':
        await message.answer(f"{bot_answer}")

### Тестирование эмоционального интеллекта
data_test = []
with open('test1.csv', mode='r', newline='', encoding='utf-8') as file:
    reader = csv.reader(file)
    for row in reader:
        data_test.append(row)

@dp.message(F.text.lower() == 'тестирование эмоционального интеллекта', States.logged_user)
async def cmd_tests(message: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text='Начать тестирование', callback_data='test_question1')
    builder.adjust(1)
    await message.answer('Пожалуйста, запоминайте количество ваших верных ответов.\n\
Это необходимо для корректных итогов тестирования.', reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith('test_question'), States.logged_user)
async def test_question(call: CallbackQuery, state: FSMContext):
    question = int(call.data[-1])
    if 1 <= question < 10:
        builder = InlineKeyboardBuilder()
        builder.button(text='Показать ответ', callback_data=f'answer_test_question{question}')
        if question != 9:
            builder.button(text='Следующий вопрос', callback_data=f'test_question{question+1}')
        else:
            builder.button(text='Завершить тестирование', callback_data=f'test_question{question+1}')
        builder.adjust(1, 1)
        await call.message.answer(f'Вопрос №{question}. {data_test[question][0]}\n\
Варианты ответа: \n1) {data_test[question][1]}\n2) {data_test[question][2]}\n3) {data_test[question][3]}', reply_markup=builder.as_markup())
    else:
        await call.message.answer('Поздравляем! Вы прошли тест по эмоциональному интеллекту!\
\nТеперь давайте рассмотрим результаты:\
\n\n0-3 балла: Начальный уровень\
\nВы находитесь на самом начале пути в понимании эмоционального интеллекта. Не переживайте! Это отличный повод начать изучать основные концепции и развивать свои навыки. Возможно, стоит обратить внимание на эмоциональное восприятие и управление эмоциями.\
\n\n4-6 баллов: Средний уровень\
\nВы обладаете базовыми знаниями в области эмоционального интеллекта. У вас есть понимание некоторых аспектов, но есть пространство для роста. Продолжайте развивать свои навыки, исследуйте техники активного слушания и саморегуляции, чтобы стать более чувствительным к эмоциям других и своим.\
\n\n7-9 баллов: Высокий уровень\
\nОтличная работа! Вы продемонстрировали высокий уровень эмоционального интеллекта. У вас крепкое понимание своих эмоций и умение управлять ими. Вы, вероятно, легко распознаете чувства окружающих и успешно взаимодействуете с ними. Продолжайте развивать свои навыки и делиться знаниями с окружающими!\
\n\nПомните, что развитие эмоционального интеллекта — это процесс. Пробуйте новые методы, практикуйтесь и наблюдайте за своим прогрессом! Успехов!', reply_markup=show_keyboard())
                                  
@dp.callback_query(F.data.startswith('answer_test_question'), States.logged_user)
async def test_question_answer(call: CallbackQuery, state: FSMContext):
    question = int(call.data[-1])
    builder = InlineKeyboardBuilder()
    builder.button(text='Следующий вопрос', callback_data=f'test_question{question+1}')
    builder.adjust(1)
    await call.message.answer(f'Вопрос №{question}. {data_test[question][0]}\n\
Верный ответ: {data_test[question][4]}', reply_markup=builder.as_markup())


### Советы и упражнения

# practice1 - Самосознание
practice1 = [
    "Ведите дневник эмоций. Записывайте каждое утро или вечер свои чувства и мысли. \nОбратите внимание на то, что вызывает положительные и отрицательные эмоции. \nРегулярное фиксирование эмоций поможет вам лучше понимать себя и свои реакции на мир вокруг.",
    "Практикуйте осознанность. Найдите 5-10 минут в день для медитации или глубокого дыхания. \nСосредоточьтесь на своих ощущениях и мыслях, избавьтесь от отвлекающих факторов. \nЭто поможет вам выявить эмоциональные реакции в текущий момент и станет основой для лучшей саморегуляции.",
    "Сделайте анализ своих сильных и слабых сторон. Напишите список ваших навыков и качеств. \nОбдумайте, какие из них помогают вам в жизни, а какие мешают. \nРегулярно пересматривайте этот список, чтобы отслеживать свой рост и развитие, а также находить области для улучшения."
]

# practice2 - Саморегуляция
practice2 = [
    "Используйте технику '5-4-3-2-1' для снижения стресса. \nНазовите 5 вещей, которые вы видите, 4 вещи, которые вы можете потрогать, \n3 вещи, которые вы слышите, 2 вещи, которые вы чувствуете, и 1 вещь, ради которой вы благодарны. \nЭта техника поможет вам вернуться в настоящий момент и уменьшить беспокойство.",
    "Определите свои три основных триггера (ситуации, вызывающие сильные эмоции) и разработайте стратегии преодоления. \nЗапишите, как вы обычно реагируете на эти триггеры. \nПодумайте, как вы могли бы реагировать иначе и запишите альтернативные способы, чтобы быть готовым к будущим ситуациям.",
    "Практикуйте глубокое дыхание. Вибрируйте свои пальцы, когда чувствуете стресс, и делайте 10 глубоких вдохов. \nСосредоточьтесь на своем дыхании, представляя, как вы вдохнули спокойствие, а выдохнули напряжение. \nЭто поможет вам успокоиться и восстановить контроль над эмоциями, особенно в напряженных ситуациях."
]

# practice3 - Эмпатия
practice3 = [
    "Практикуйте активное слушание во время общения. \nЗадавайте открытые вопросы, поддерживайте зрительный контакт и подтверждайте услышанное, чтобы собеседник чувствовал, что его понимают. \nЭто поможет вам лучше понять чувства собеседника и установить более глубокую связь с ним.",
    "Напишите письмо поддержке другу, который переживает трудные времена. \nПопробуйте вникнуть в его чувства, опишите, как вы его понимаете и какие действия готовы предпринять. \nЭто поможет вам развить эмпатию и научиться ставить себя на место других, а также укрепит ваши отношения.",
    "Уберите первый импульс к суждению в конфликтной ситуации. \nПеред тем, как ответить, подумайте о мотивах другого человека и его эмоциональном состоянии. \nЗадайте себе вопрос, как бы вы себя чувствовали на его месте, это может помочь ослабить напряжение и найти общий язык."
]

# practice4 - Социальные навыки
practice4 = [
    "Занимайтесь навыками конструктивной обратной связи. \nПри общении с другими, выделяйте 1 положительное качество, прежде чем перейти к рекомендации или критике. \nЭто создаст доброжелательную атмосферу и поможет собеседнику воспринимать вашу обратную связь как стремление помочь.",  
    "Упражняйтесь в решении конфликтов. \nПроведите ролевую игру с другом, разыгрывая конфликт и находя пути его разрешения с учетом чувств обеих сторон. \nПосле игры обсудите, какие стратегии сработали лучше и какие эмоции возникли, это поможет вам лучше понимать динамику конфликтов.",
    "Развивайте свои навыки публичных выступлений. \nВыходите из зоны комфорта и пробуйте выступать перед малой аудиторией, захватывая их внимание. \nЭто поможет вам лучше общаться и влиять на окружающих, а также улучшит вашу уверенность в себе в социализации."
]

# practice5 - Мотивация
practice5 = [
    "Установите SMART-цели для достижения желаемого результата. \nСформулируйте свои цели так, чтобы они были конкретными, измеримыми, достижимыми, актуальными и ограниченными по времени. \nРегулярно пересматривайте прогресс и подстраивайте цели по мере необходимости, чтобы оставаться на правильном пути и получать удовлетворение от достижений.",
    "Создайте визуализацию успеха. \nПодготовьте коллаж из вдохновляющих картинок и цитат, которые олицетворяют ваши цели. \nРазмещайте его на видном месте, чтобы каждый день видеть свое стремление и напоминать себе, зачем вы работаете над собой.",
    "Развивайте позитивные привычки. \nЗаписывайте 3 вещи, за которые вы благодарны, каждое утро. \nЭто поможет вам поддерживать мотивацию и позитивный настрой на протяжении дня, а также улучшит общее восприятие жизни."
]

practices = [practice1, practice2, practice3, practice4, practice5]


@dp.callback_query(F.data == 'cmd_exercises', States.logged_user)
@dp.message(F.text.lower().in_({'советы и упражнения'}), States.logged_user)
async def cmd_exercises(call_or_message, state: FSMContext):
    if type(call_or_message) == Message:
        objectmes = call_or_message
    else:
        objectmes = call_or_message.message
    builder = InlineKeyboardBuilder()
    builder.button(text='Самосознание', callback_data='show_practice_1')
    builder.button(text='Саморегуляция', callback_data='show_practice_2')
    builder.button(text='Эмпатия', callback_data='show_practice_3')
    builder.button(text='Социальные навыки', callback_data='show_practice_4')
    builder.button(text='Мотивация', callback_data='show_practice_5')
    builder.adjust(2, 2, 1)
    await objectmes.answer('Какую тему вы хотите изучить?', reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith('show_practice_'), States.logged_user)
async def show_exercises(call: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text='Вернуться назад', callback_data='cmd_exercises')
    builder.adjust(1)
    exercise_number = int(call.data[-1])
    exercises_list = practices[exercise_number-1]
    exercises_text = '>>> ' + '\n\n>>> '.join(exercises_list)
    await call.message.answer(exercises_text, reply_markup=builder.as_markup())


### Ежедневные задания
daily_tasks = [
    "Составьте карту своих эмоций. Напишите слова для обозначения разных эмоций и ситуации, когда вы их испытываете.",
    "Каждый день в течение недели ведите дневник своих эмоций. Записывайте, какие эмоции вы испытывали и в каких ситуациях.",
    "Проведите день, фиксируя момент, когда вы хотите что-то сказать. Подумайте, как ваши слова могут повлиять на других.",
    "Проанализируйте недавний конфликт. Опишите, какие эмоции испытывали вы и сторона противника.",
    "Найдите одну позитивную эмоцию и постарайтесь вызвать её у других. Запишите свои методы и их реакцию.",
    "Попробуйте сделать что-то приятное для себя. Опишите, какие эмоции вызвало это действие.",
    "Играйте в 'эмоциональные' игры с друзьями или семьей, где каждый должен изобразить эмоцию, не произнося слова.",
    "Слушайте музыку и попытайтесь связать её с конкретными эмоциями. Запишите, какие чувства она вызывает.",
    "Поговорите с кем-то, кто имеет отличное от вашего мнение, и попробуйте понять его точку зрения, не подаваясь эмоциям.",
    "Уделите время чтению книг или статей об эмоциональном интеллекте и запишите, что вам запомнилось и чему вы научились."
]


@dp.callback_query(F.data == 'daily_tasks_on', States.logged_user)
async def daily_tasks_on(call: CallbackQuery, state: FSMContext):
    message = call.message
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET statusrem = TRUE WHERE id = ?", (message.from_user.id, ))
        await db.commit()
    await message.answer('Ежедневные задания активированы!')


@dp.callback_query(F.data == 'daily_tasks_off', States.logged_user)
async def daily_tasks_off(call: CallbackQuery, state: FSMContext):
    message = call.message
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET statusrem = FALSE WHERE id = ?", (message.from_user.id, ))
        await db.commit()
    await message.answer('Ежедневные задания отключены!')


@dp.callback_query(F.data == 'cmd_daily_tasks', States.logged_user)
@dp.message(F.text.lower().in_({'ежедневные задания'}), States.logged_user)
async def cmd_daily_tasks(call_or_message, state: FSMContext):
    if type(call_or_message) == Message:
        objectmes = call_or_message
    else:
        objectmes = call_or_message.message
    builder = InlineKeyboardBuilder()
    builder.button(text='Включить ежедневные задания', callback_data='daily_tasks_on')
    builder.button(text='Отключить ежедневные задания', callback_data='daily_tasks_off')
    builder.adjust(1, 1)
    await objectmes.answer('Что вы хотите изменить?', reply_markup=builder.as_markup())

async def send_msg(dp):
    task = daily_tasks[randint(0, 9)]
    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT * FROM users WHERE statusrem=TRUE") as cursor:
            async for row in cursor:
                await bot.send_message(chat_id=row[0], text=f'Время ежедневного задания!\n{task}')

@dp.message()
async def prtext(message: Message, state: FSMContext):
    await message.answer("Нельзя писать произвольный текст! \
\nЕсли бот был перезапущен, авторизуйтесь командой /start")

async def start_bot():
    commands = [BotCommand(command='menu', description='Главное меню'),
                BotCommand(command='developers', description='О разработчиках')]
    await bot.set_my_commands(commands, BotCommandScopeDefault())

async def start_db():
    # Подключение к базе данных (если файл не существует, он будет создан)
    async with aiosqlite.connect('users.db') as db:
        # Создание таблицы, если она не существует
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER,
                statusrem BOOLEAN
            )
        ''')
        await db.commit() # Сохранение изменений

async def main(): #Основная асинхронная функция, которая будет запускаться при старте бота.
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    job = scheduler.add_job(send_msg, 'cron', hour=21, args=(dp,))
    scheduler.start()
    dp.message.outer_middleware(SomeMiddleware())
    dp.startup.register(start_db)
    dp.startup.register(start_bot)
    try:
        print("Бот запущен...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()) #Запускаем бота в режиме опроса (polling). Бот начинает непрерывно запрашивать обновления с сервера Telegram и обрабатывать их
    finally:
        scheduler.remove_job(job.id)
        await bot.session.close()
        print("Бот остановлен")

asyncio.run(main())