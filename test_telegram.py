"""
Script test hàm send_telegram_message từ btc.py
Không cần kết nối MT5, chỉ test gửi Telegram
"""

import sys
from pathlib import Path

# Import config
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

try:
    import configbtc
    from configbtc import *
except ImportError:
    print("⚠️  File configbtc.py không tìm thấy!")
    sys.exit(1)

import requests
import logging

# Setup logging đơn giản
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def send_telegram_message(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Test hàm gửi Telegram (giống như trong btc.py)
    
    Args:
        bot_token: Token của Telegram Bot
        chat_id: Chat ID để nhận thông báo
        message: Nội dung tin nhắn cần gửi
        
    Returns:
        True nếu gửi thành công, False nếu thất bại
    """
    if not bot_token or not chat_id:
        logger.error("❌ Telegram chưa được cấu hình (thiếu BOT_TOKEN hoặc CHAT_ID)")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        logger.info(f"📤 Đang gửi thông báo Telegram...")
        logger.info(f"   URL: {url}")
        logger.info(f"   Chat ID: {chat_id}")
        
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        
        result = response.json()
        if result.get('ok'):
            logger.info(f"✅ Đã gửi thông báo Telegram thành công!")
            logger.info(f"   Message ID: {result.get('result', {}).get('message_id', 'N/A')}")
            return True
        else:
            logger.error(f"❌ Gửi thất bại: {result.get('description', 'Unknown error')}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"⚠️ Không thể gửi thông báo Telegram: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Lỗi khi gửi Telegram: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TEST HÀM SEND_TELEGRAM_MESSAGE")
    print("=" * 60)
    
    # Lấy config từ configbtc.py
    bot_token = TELEGRAM_BOT_TOKEN if 'TELEGRAM_BOT_TOKEN' in dir() else ""
    chat_id = TELEGRAM_CHAT_ID if 'TELEGRAM_CHAT_ID' in dir() else ""
    
    print(f"\n📋 Cấu hình:")
    print(f"   Bot Token: {'✅ Đã cấu hình' if bot_token else '❌ Chưa cấu hình'}")
    print(f"   Chat ID: {'✅ Đã cấu hình' if chat_id else '❌ Chưa cấu hình'}")
    
    if not bot_token or not chat_id:
        print("\n❌ Vui lòng cấu hình TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong configbtc.py")
        sys.exit(1)
    
    # Test message 1: Message đơn giản
    print("\n" + "=" * 60)
    print("📤 Test 1: Gửi message đơn giản")
    print("=" * 60)
    
    test_message_1 = "🧪 <b>TEST TELEGRAM</b>\n\nĐây là tin nhắn test từ bot BTC Trader!"
    success_1 = send_telegram_message(bot_token, chat_id, test_message_1)
    
    if success_1:
        print("✅ Test 1: PASSED")
    else:
        print("❌ Test 1: FAILED")
    
    # Test message 2: Message với format giống lệnh thực tế
    print("\n" + "=" * 60)
    print("📤 Test 2: Gửi message format lệnh BUY (giống như trong bot)")
    print("=" * 60)
    
    test_message_2 = (
        f"🟢 <b>LỆNH MỚI: BUY BTCUSD (TEST)</b>\n\n"
        f"📊 <b>Thông tin lệnh:</b>\n"
        f"   • Ticket: <code>12345</code>\n"
        f"   • Volume: <b>0.01</b> lots\n"
        f"   • Giá vào: <b>65000.00</b>\n"
        f"   • SL: <b>63000.00</b> (2000 points)\n"
        f"   • TP: <b>68000.00</b> (3000 points)\n"
        f"   • Risk: <b>100.00</b> (1.0%)\n\n"
        f"📈 <b>Thông tin tài khoản:</b>\n"
        f"   • Equity: <b>10000.00</b>\n"
        f"   • Balance: <b>10000.00</b>\n"
        f"   • Lệnh hôm nay: 1/100\n\n"
        f"💡 <b>Lý do:</b>\nRSI oversold; MACD bullish momentum; Strong Uptrend"
    )
    success_2 = send_telegram_message(bot_token, chat_id, test_message_2)
    
    if success_2:
        print("✅ Test 2: PASSED")
    else:
        print("❌ Test 2: FAILED")
    
    # Test message 3: Message với format lệnh SELL
    print("\n" + "=" * 60)
    print("📤 Test 3: Gửi message format lệnh SELL")
    print("=" * 60)
    
    test_message_3 = (
        f"🔴 <b>LỆNH MỚI: SELL BTCUSD (TEST)</b>\n\n"
        f"📊 <b>Thông tin lệnh:</b>\n"
        f"   • Ticket: <code>12346</code>\n"
        f"   • Volume: <b>0.01</b> lots\n"
        f"   • Giá vào: <b>65000.00</b>\n"
        f"   • SL: <b>67000.00</b> (2000 points)\n"
        f"   • TP: <b>62000.00</b> (3000 points)\n"
        f"   • Risk: <b>100.00</b> (1.0%)\n\n"
        f"📈 <b>Thông tin tài khoản:</b>\n"
        f"   • Equity: <b>10000.00</b>\n"
        f"   • Balance: <b>10000.00</b>\n"
        f"   • Lệnh hôm nay: 2/100\n\n"
        f"💡 <b>Lý do:</b>\nRSI overbought; MACD bearish momentum"
    )
    success_3 = send_telegram_message(bot_token, chat_id, test_message_3)
    
    if success_3:
        print("✅ Test 3: PASSED")
    else:
        print("❌ Test 3: FAILED")
    
    # Tổng kết
    print("\n" + "=" * 60)
    print("📊 KẾT QUẢ TỔNG KẾT")
    print("=" * 60)
    
    total_tests = 3
    passed_tests = sum([success_1, success_2, success_3])
    
    print(f"✅ Passed: {passed_tests}/{total_tests}")
    print(f"❌ Failed: {total_tests - passed_tests}/{total_tests}")
    
    if passed_tests == total_tests:
        print("\n🎉 TẤT CẢ TEST PASSED! Hàm send_telegram_message hoạt động tốt.")
    else:
        print("\n⚠️ Có một số test failed. Vui lòng kiểm tra lại cấu hình Telegram.")
    
    print("\n💡 Lưu ý: Nếu bạn nhận được tin nhắn trên Telegram, nghĩa là hàm hoạt động đúng!")
    print("=" * 60)

