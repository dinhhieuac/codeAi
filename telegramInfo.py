import requests
import sys

def get_chat_id(token):
    """
    Get the Chat ID from the latest message sent to the bot using the Telegram Bot API.
    
    Args:
        token (str): The Telegram Bot Token.
        
    Returns:
        str or int: The Chat ID if found, else None.

        XAU INFO : XAU8509480492:AAFgxCgdAsrd80xJ5H6e_vVOg-NBzTivfBU
        BTCUSD INFO : 8171919458:AAEMKOHsFJee7MSs2QW1-EI85EBof-yZ1zw
        ETHUSD INFO : 8293920688:AAEV7_JEt-AV1rEI2idDXrm9YLZV3pJWBKI

        EURUSD INFO : EURUSD8509480492:AAFgxCgdAsrd80xJ5H6e_vVOg-NBzTivfBU
        GBPUSD INFO : GBPUSD8509480492:AAFgxCgdAsrd80xJ5H6e_vVOg-NBzTivfBU
        TUYEN INFO : 6546177543:AAGJ1yb_s6_WWrk0KtO8ioJe6pfkT9KNpqE
    """
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("ok"):
            results = data.get("result", [])
            if results:
                # Get the last message update
                last_update = results[-1]
                
                # Check for message or edited_message
                if 'message' in last_update:
                    chat_id = last_update['message']['chat']['id']
                    chat_type = last_update['message']['chat']['type']
                    user = last_update['message']['from'].get('username', 'Unknown')
                    print(f"✅ Found Chat ID: {chat_id}")
                    print(f"   Type: {chat_type}")
                    print(f"   User: @{user}")
                    return chat_id
                elif 'my_chat_member' in last_update:
                     # This happens when bot is added to a channel/group
                    chat_id = last_update['my_chat_member']['chat']['id']
                    chat_title = last_update['my_chat_member']['chat'].get('title', 'Unknown')
                    print(f"✅ Found Chat ID (Channel/Group): {chat_id}")
                    print(f"   Title: {chat_title}")
                    return chat_id
            else:
                print("⚠️ No updates found. Please send a message to your bot first!")
                return None
        else:
            print(f"❌ API Error: {data.get('description')}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    print("--- Telegram Chat ID Finder ---")
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        token = input("Enter your Telegram Bot Token: ").strip()
    
    if token:
        get_chat_id(token)
    else:
        print("Token is empty.")
