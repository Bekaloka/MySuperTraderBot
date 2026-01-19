import telebot
import ccxt
import pandas_ta as ta
import pandas as pd
import time
import os
import logging
from threading import Thread
from datetime import datetime

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
CHECK_INTERVAL = 900  # 15 минут в секундах

# Валидация переменных окружения
if not TOKEN or not CHAT_ID:
    raise ValueError("Не установлены TELEGRAM_TOKEN или TELEGRAM_CHAT_ID")

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = telebot.TeleBot(TOKEN)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

class TradingBot:
    def __init__(self):
        self.last_signal = None
        self.is_running = False
    
    def get_signal(self):
        """Получение торгового сигнала на основе SuperTrend"""
        try:
            # Загружаем свечи
            bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Проверка на пустые данные
            if df.empty:
                logger.warning("Получены пустые данные с биржи")
                return None
            
            # Расчет SuperTrend
            supertrend = ta.supertrend(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                length=10,
                multiplier=3.0
            )
            
            if supertrend is None or supertrend.empty:
                logger.warning("Не удалось рассчитать SuperTrend")
                return None
            
            # Получаем последнее значение направления тренда
            last_direction = supertrend.iloc[-1]['SUPERTd_10_3.0']
            current_price = df.iloc[-1]['close']
            
            signal_data = {
                'direction': 'BUY 🟢' if last_direction == 1 else 'SELL 🔴',
                'price': current_price,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            logger.info(f"Сигнал: {signal_data['direction']} по цене {current_price}")
            return signal_data
            
        except ccxt.NetworkError as e:
            logger.error(f"Ошибка сети при получении данных: {e}")
            return None
        except ccxt.ExchangeError as e:
            logger.error(f"Ошибка биржи: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при получении сигнала: {e}", exc_info=True)
            return None
    
    def format_signal_message(self, signal_data):
        """Форматирование сообщения с сигналом"""
        return (
            f"📊 <b>{SYMBOL}</b>\n"
            f"⚡️ Сигнал: <b>{signal_data['direction']}</b>\n"
            f"💰 Цена: <code>{signal_data['price']:.2f}</code> USDT\n"
            f"🕐 Время: {signal_data['timestamp']}"
        )
    
    def auto_check(self):
        """Автоматическая проверка сигналов"""
        self.is_running = True
        logger.info("Автоматическая проверка запущена")
        
        while self.is_running:
            try:
                current_signal = self.get_signal()
                
                if current_signal:
                    # Отправляем уведомление только при изменении сигнала
                    if self.last_signal is None or current_signal['direction'] != self.last_signal['direction']:
                        message = f"🔔 <b>НОВЫЙ СИГНАЛ!</b>\n\n{self.format_signal_message(current_signal)}"
                        bot.send_message(CHAT_ID, message, parse_mode='HTML')
                        self.last_signal = current_signal
                        logger.info(f"Отправлено уведомление о новом сигнале: {current_signal['direction']}")
                
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле auto_check: {e}", exc_info=True)
                time.sleep(60)  # Короткая пауза при ошибке
    
    def stop(self):
        """Остановка автоматической проверки"""
        self.is_running = False
        logger.info("Автоматическая проверка остановлена")

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
trading_bot = TradingBot()

# --- ОБРАБОТЧИКИ КОМАНД ---
@bot.message_handler(commands=['start'])
def start(message):
    welcome_text = (
        "👋 <b>Добро пожаловать в торгового бота!</b>\n\n"
        f"📈 Отслеживаемая пара: <code>{SYMBOL}</code>\n"
        f"⏱ Таймфрейм: <code>{TIMEFRAME}</code>\n"
        f"📊 Индикатор: SuperTrend (10, 3.0)\n\n"
        "<b>Доступные команды:</b>\n"
        "/status - текущий сигнал\n"
        "/info - информация о боте\n"
        "/help - справка"
    )
    bot.reply_to(message, welcome_text, parse_mode='HTML')
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

@bot.message_handler(commands=['status'])
def status(message):
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные...")
        signal_data = trading_bot.get_signal()
        
        if signal_data:
            response = trading_bot.format_signal_message(signal_data)
            bot.send_message(message.chat.id, response, parse_mode='HTML')
        else:
            bot.send_message(
                message.chat.id,
                "⚠️ Не удалось получить сигнал. Попробуйте позже."
            )
    except Exception as e:
        logger.error(f"Ошибка в команде /status: {e}", exc_info=True)
        bot.send_message(
            message.chat.id,
            f"❌ Произошла ошибка: {str(e)}"
        )

@bot.message_handler(commands=['info'])
def info(message):
    info_text = (
        f"ℹ️ <b>Информация о боте</b>\n\n"
        f"Символ: <code>{SYMBOL}</code>\n"
        f"Таймфрейм: <code>{TIMEFRAME}</code>\n"
        f"Интервал проверки: <code>{CHECK_INTERVAL // 60} минут</code>\n"
        f"Статус: {'🟢 Активен' if trading_bot.is_running else '🔴 Остановлен'}\n"
        f"Последний сигнал: <code>{trading_bot.last_signal['direction'] if trading_bot.last_signal else 'Нет данных'}</code>"
    )
    bot.reply_to(message, info_text, parse_mode='HTML')

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "📖 <b>Справка</b>\n\n"
        "Бот анализирует рынок криптовалют используя индикатор SuperTrend "
        "и отправляет сигналы на покупку/продажу.\n\n"
        "<b>Как это работает:</b>\n"
        "• Бот проверяет рынок каждые 15 минут\n"
        "• При изменении сигнала вы получаете уведомление\n"
        "• 🟢 BUY - сигнал на покупку\n"
        "• 🔴 SELL - сигнал на продажу\n\n"
        "<b>Команды:</b>\n"
        "/status - узнать текущий сигнал\n"
        "/info - информация о боте\n"
        "/help - эта справка"
    )
    bot.reply_to(message, help_text, parse_mode='HTML')

# --- ЗАПУСК ---
if __name__ == "__main__":
    try:
        logger.info("Запуск бота...")
        
        # Запуск автоматической проверки в отдельном потоке
        auto_check_thread = Thread(target=trading_bot.auto_check, daemon=True)
        auto_check_thread.start()
        
        # Отправка уведомления о запуске
        bot.send_message(
            CHAT_ID,
            f"✅ <b>Бот запущен!</b>\n"
            f"Отслеживаю {SYMBOL} на таймфрейме {TIMEFRAME}",
            parse_mode='HTML'
        )
        
        logger.info("Бот успешно запущен")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
        trading_bot.stop()
        bot.send_message(CHAT_ID, "🛑 Бот остановлен")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        try:
            bot.send_message(CHAT_ID, f"❌ Критическая ошибка: {str(e)}")
        except:
            pass
