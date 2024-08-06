import asyncio
import os
import re
import requests
import base64
import json
import math  

from requests.auth import HTTPDigestAuth
from typing import Final
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.api import Client
from solders.hash import Hash
from solana.transaction import Transaction
from solders.system_program import TransferParams, transfer

from pydantic import BaseModel, Field, field_validator # v2 needed
from bson import ObjectId
from typing import Optional, List
from pymongo import MongoClient

# custom module
from solanaHelper import SolanaHelper
from jupiter import JupiterHelper
from decimal import Decimal

load_dotenv()

dbURI = os.getenv("dbURI")
TOKEN = os.getenv("TOKEN")
# SHYFT_API_KEY = os.getenv("SHYFT_API_KEY")
mongoClient = MongoClient(dbURI)
db = mongoClient.telegram 
wallet_collection = db.wallet 

BOT_NAME: Final = '@crypto737263_bot'
chain_id = "solana"  # Change to the appropriate chain ID

last_call_back_type = ""


receiver_pub_key = None  # Initialize as None to handle the state
one_sol_in_lamports = 1000000000
sol_address = "So11111111111111111111111111111111111111112"
main_keyboard = [
    [
        {"text": "Buy Tokens", "callback_data": "buy_token"},
        {"text": "Positions", "callback_data": "positions"}
    ],
    [
        {"text": "Wallet", "callback_data": "wallet"},
        {"text": "Settings", "callback_data": "settings"},
    ],
    [
        {"text": "Transfer Token", "callback_data": "transfer_token"},
    ],
]

submenu_keyboard = [
    [
        InlineKeyboardButton("Generate Wallet", callback_data='generate_wallet'),
    ],
    [
        InlineKeyboardButton("Export Private Key", callback_data='export_private_key'),
        InlineKeyboardButton("Check Balance", callback_data='get_balance'),
    ],
    [
        InlineKeyboardButton("Withdraw SOL", callback_data='withdraw_sol'),
        InlineKeyboardButton("Send SOL", callback_data='send_sol'),
    ],
    [
        InlineKeyboardButton("Back", callback_data='back_to_main'),
    ]
]



class ChatData(BaseModel):
    def __init__(self, type, pubKey):
        self.callbackType = type
        self.pubKey = pubKey
    
    def setCallbackType(self, type):
        self.callbackType = type

    def setPubKey(self, pubKey):
        self.pubKey = pubKey
        


class UserModel(BaseModel):
    userId: int = Field(..., unique=True)
    privateKey: str
    publicKey: str
    keypair: str
    
    @field_validator('privateKey')
    def check_base64(cls, v):
        try:
            base64.b64decode(v)
            return v
        except Exception as e:
            raise ValueError("Invalid base64 encoded key")

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "userId": "3234323432",
                "privateKey": base64.b64encode(b'some_private_key').decode('utf-8'),
                "publicKey": "ptgjndf985544",
                "keypair": "sdfbsd8y8dsiu44",
            }
        }
        


def encode_key(key: bytes) -> str:
    return base64.b64encode(key).decode('utf-8')

def decode_key(encoded_key: str) -> bytes:
    return base64.b64decode(encoded_key)


async def insert_user(user_data: UserModel):
    try:
        # convert the Pydantic model to a dictionary
        wallet_dict = user_data.dict(by_alias=True)
        result = wallet_collection.insert_one(wallet_dict)
        print(f'User inserted with id: {result.inserted_id}')
    except Exception as e:
        print(f'Error inserting user: {e}')
        

async def get_user_by_userId(userId: int) -> Optional[UserModel]:
    try:
        wallet_dict = wallet_collection.find_one({"userId": userId})
        print('walleteddddd',wallet_dict)
        if wallet_dict:
            return UserModel(**wallet_dict)
    except Exception as e:
        print(f'Error getting user: {e}')
    return None

def get_users() -> list[UserModel]:
    try:
        users = []
        for user_dict in wallet_collection.find():
            users.append(UserModel(**user_dict))
        return users
    except Exception as e:
        print(f'Error getting all users: {e}')
        return []

async def update_user(userId: int, update_data: dict):
    try:
        result = await wallet_collection.update_one({"userId": userId}, {"$set": update_data})
        print('update_user result',result)
        if result.modified_count:
            print(f'User updated')
        else:
            print(f'No user found with userId: {userId}')
    except Exception as e:
        print(f'Error updating user: {e}')

def delete_user(userId: str):
    try:
        result = wallet_collection.delete_one({"userId": userId})
        if result.deleted_count:
            print(f'User deleted')
        else:
            print(f'No user found with userId: {userId}')
    except Exception as e:
        print(f'Error deleting user: {e}')




async def main_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = InlineKeyboardMarkup(main_keyboard)
    await update.message.reply_text('Hello! This is Crypto Bot.', reply_markup=reply_markup)


async def button_click_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_call_back_type
    query = update.callback_query
    chat_id = query.from_user.id
    await query.answer()
    callback_data = query.data
    last_call_back_type = callback_data



    if callback_data == 'wallet':
        submenu_reply_markup = InlineKeyboardMarkup(submenu_keyboard)
        context.chat_data["callbackType"] = callback_data
        await query.edit_message_text(text="Manage Wallet", reply_markup=submenu_reply_markup)
    elif callback_data == 'buy_token':
        context.chat_data["callbackType"] = callback_data
        await query.edit_message_text(text="Enter client address to continue:")
    elif callback_data == 'transfer_token':
        context.chat_data["callbackType"] = callback_data
        await query.edit_message_text(text="Enter token address to continue:")
    elif callback_data == 'positions':
        await query.edit_message_text(text="You clicked positions")
    elif callback_data == 'settings':
        await query.edit_message_text(text="You clicked settings")
    elif callback_data == 'back_to_main':
        main_reply_markup = InlineKeyboardMarkup(main_keyboard)
        await query.edit_message_text(text="Hello! This is Crypto Bot, how can I help.", reply_markup=main_reply_markup)
    elif callback_data == 'generate_wallet':
        print('generating wallet with chat id-',chat_id)
        print('type of chatid',type(chat_id))

        retrieved_user = await get_user_by_userId(int(chat_id))
        print('retrieved_user',retrieved_user)
        if (retrieved_user == None):
            keypair = Keypair()
            # private_key = str(keypair.secret())
            private_key = encode_key(keypair.secret())
            public_key = str(keypair.pubkey())
            keypairStr = str(keypair)
            
            new_user = UserModel(userId=chat_id, privateKey=private_key, publicKey=public_key, keypair = keypairStr)
            await insert_user(new_user)
            await send_message(chat_id, f"🎉 Wallet generated\n*Public Key*: _`{public_key}`_ \\(Tap to copy\\)", context)
        else:
            print('wallet already exist')
            await send_message(chat_id, f"A wallet is already created with your account\\.\nCurrently we support only one wallet per user\nYour *Public Key*: _`{retrieved_user.publicKey}`_ \\(Tap to copy\\)", context)
    elif callback_data == 'export_private_key':
        retrieved_user = await get_user_by_userId(int(chat_id))
        if(retrieved_user):
            # pk = decode_key(str(retrieved_user.privateKey))
            print('retrieved_user',retrieved_user)
            print('private key',retrieved_user.keypair)
            await send_message(chat_id, f"*Private Key*: _`{retrieved_user.keypair}`_ \\(Tap to copy\\)", context)
        else:
            await send_message(chat_id, f"You don\\'t have any wallet", context)
    elif callback_data == 'get_balance':
        retrieved_user = await get_user_by_userId(int(chat_id))
        if(retrieved_user):
            try:
                response = helper.getBalance(Pubkey.from_string(retrieved_user.publicKey))
                sol_bal = math.ceil((response.value / one_sol_in_lamports) * 100) / 100
                      
                sol_price_response = requests.get('https://api.raydium.io/v2/main/price')
                sol_price_response.raise_for_status()  # Check for HTTP errors
                data = sol_price_response.json()
                sol_price = data[sol_address]
                usd_bal =  math.ceil((sol_bal * sol_price) * 100) / 100
                print('sol_bal',sol_bal)
                print('sol_price',sol_price)
                print('usd_bal',usd_bal)
                
                message = (
                    f"*Wallet Balance*\n"
                    f"`{retrieved_user.publicKey}` _\\(Tap to copy\\)_ \n"
                    f"Balance: {escape_dots(sol_bal)} SOL  \\(\\💲{escape_dots(usd_bal)}\\)"
                )
                await send_message(chat_id, message, context)
            except requests.exceptions.HTTPError as http_err:
                print(f"HTTP error occurred: {http_err}")
            except Exception as err:
                print(f"Other error occurred: {err}")
        else:
            await send_message(chat_id, f"You don\\'t have any wallet", context)
    elif callback_data == 'send_sol':
        await send_message(chat_id, f"Enter receiver\\'s public key to send SOL to", context, None, callback_data)    
    elif callback_data == 'buy_0.1_sol':
        await send_message(chat_id, f"Buying 0\\.1 SOL", context)
    elif callback_data == 'buy_x_sol':
        await send_message(chat_id, f"Please enter the amount of SOL you want to swap:", context)    
    elif callback_data == 'sell_x_percent':
        await send_message(chat_id, f"Please enter the percentage you want to sell:", context)    


def get_token_info(token_address):
    try:
        api_url = f"https://api.dexscreener.io/latest/dex/tokens/{token_address}"
        response = requests.get(api_url)
        response.raise_for_status()  # Check for HTTP errors
        data = response.json()
        print('getTokenData',data)
        if data['pairs']:
            token_info = data['pairs'][0]  # Get the first pair information
            return {
                "name": token_info['baseToken']['name'],
                "symbol": token_info['baseToken']['symbol'],
                "price_usd": token_info.get('priceUsd', 'N/A'),
                "liquidity_usd": token_info.get('liquidity', {}).get('usd', 'N/A'),
                "fdv": token_info.get('fdv', 'N/A')
            }
        else:
            return None
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"Other error occurred: {err}")


def escape_dots(value):
    value_str = str(value)
    escaped_str = re.sub(r'\.', r'\\.', value_str)
    return escaped_str


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_call_back_type
    text = update.message.text
    response = f"{text}"
    chat_type = update.message.chat.type
    chat_id = update.message.chat.id
    tmpCallBackType = context.chat_data.get("callbackType", '') or ""
    tmpPubkey = context.chat_data.get("pubKey", '') or ""
    print('chat_type', chat_type, "tmpCallBackType>>>>>>>>>>>>",tmpCallBackType, "<<<<<<tmpPubkey>>>>>>>>>>", tmpPubkey)
    
    global receiver_pub_key

    if chat_type == "private":
        # Capture any word over 32 characters
        token_addresses = re.findall(r'\b\w{33,}\b', text)
        print('token_addresses-', token_addresses)
        
        # Regex to capture Solana public keys
        public_key_match = re.findall(r'\b[A-HJ-NP-Za-km-z1-9]{44}\b', text)
        print('public_key_match-', public_key_match)

        if public_key_match:
            public_key = public_key_match[0]
            print('-public_key', public_key)
            receiver_pub_key = public_key

            if(tmpCallBackType == "buy_token" or tmpCallBackType == "transfer_token"):
                await send_message(chat_id, f"Enter amount to proceed for token:" + public_key, context, None, tmpCallBackType, public_key)
            else:
                await send_message(chat_id, f"You have not selected transaction type for the specified pubkey:"+public_key, context, None, "", "")
            






            # await send_message(chat_id, f"Enter amount to proceed for token:" + public_key, context, None, tmpCallBackType, public_key)
        
        # The below code is commented as vineet(as of 1st Aug) didn't get what it does.
        # elif token_addresses:
        #     token_address = token_addresses[0]
        #     print('-address', token_address)
        #     token_info = get_token_info(token_address)
        #     if token_info:
        #         await send_token_info_and_swap_menu(chat_id, token_info, token_address, context)
        #     else:
        #         await send_message(chat_id, f"Token information not found for address: {token_address}", context)
        elif re.match(r'^\d*\.?\d+$', text):
            inputAmount = float(text)
            # amount = inputAmount * one_sol_in_lamports
            testAmount = 5000000000
            # amount = '{:f}'.format(inputAmount * one_sol_in_lamports)
            amount = int(inputAmount * one_sol_in_lamports)


            if(not(tmpCallBackType == "buy_token" or tmpCallBackType == "transfer_token")):
                await send_message(chat_id, f"You have not selected transaction type for the transaction" , context, None, tmpCallBackType, tmpPubkey)
                return
            
            if(not(re.findall(r'\b[A-HJ-NP-Za-km-z1-9]{44}\b', tmpPubkey) )):
                await send_message(chat_id, f"No public key has been setup for txn" + tmpPubkey, context, None, tmpCallBackType, tmpPubkey)
                return



            if(receiver_pub_key is not None):
                retrieved_user = await get_user_by_userId(int(chat_id))
                # print('retrieved_user in buy',retrieved_user)
                if(retrieved_user):
                    sender = Keypair.from_base58_string(retrieved_user.keypair)
                    receiver = Pubkey.from_string(receiver_pub_key)
                    if(tmpCallBackType == "transfer_token"):
                        txn = helper.transactionFun(sender, receiver, amount)
                        if(txn):
                            print('txn:-',txn)
                            await send_message(chat_id, f"[SOL](https://solscan.io/tx/{txn}?cluster=devnet) sent successfully", context)
                        else:
                            await send_message(chat_id, f"🔴 Insufficient Balance", context)
                    elif(tmpCallBackType == "buy_token"):
                        # need to work from here 

                        tmpJupiterHel = jupiterHelper.initializeJup(sender)
                        slippage = 100  # 1% slippage in basis points
                        jup_txn_id = await jupiterHelper.execute_swap(receiver, amount, slippage, sender)
                        if not jup_txn_id:
                            await send_message(chat_id, f"There is some technical issue while buying the token", context)
                        else:
                            await send_message(chat_id, f"[SOL](https://solscan.io/tx/{jup_txn_id}) buy successfully", context)
                        

                else:
                    await send_message(chat_id, f"You don\'t have any wallet to send SOL", context)
            else:
                await send_message(chat_id, f"Enter receiver\\'s public key", context)
        elif re.match(r'^\d+(\.\d+)?%$', text):
            percentage = float(text.strip('%'))
            print('percentage-', percentage)
            await send_message(chat_id, f"Percentage set to {escape_dots(percentage)}\\% SOL", context)
            # asyncio.run(handle_sell(chat_id, percentage))
        else:
            print('private chat replyback')
            await send_message(chat_id, response, context)
    else:
        print('-group replyback')
        await update.message.reply_text(response)


async def send_message(chat_id, message, context: ContextTypes.DEFAULT_TYPE, reply_keyboard=None, callbackType="", userFilledPubkey=""):
    print('-sendmsg chatId', chat_id,)
    print('-sendmsg text', message)

    context.chat_data["callbackType"] = callbackType
    context.chat_data["pubKey"] = userFilledPubkey

    await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_keyboard, disable_web_page_preview=True, parse_mode='MarkdownV2')


async def send_token_info_and_swap_menu(chat_id, token_info, token_address, context: ContextTypes.DEFAULT_TYPE):
    # global buy_flag
    buy_button_text = "----BUY ✅----" # if buy_flag else "BUY"
    sell_button_text = "----SELL 🔴----" # if not buy_flag else "SELL"

    # selected_option.setdefault(chat_id, {"buy": None, "sell": None})

    buy_0_1_sol_text = "0.1 SOL" # if selected_option[chat_id]["buy"] == "0.1_sol" else "0.1 SOL"
    buy_0_5_sol_text = "0.5 SOL" # if selected_option[chat_id]["buy"] == "0.5_sol" else "0.5 SOL"
    buy_1_sol_text = "1 SOL" # if selected_option[chat_id]["buy"] == "1_sol" else "1 SOL"

    sell_50_text = "Sell 50%" #if selected_option[chat_id]["sell"] == "50" else "Sell 50%"
    sell_100_text = "Sell 100%" #if selected_option[chat_id]["sell"] == "100" else "Sell 100%"
    sell_25_text = "Sell 25%" #if selected_option[chat_id]["sell"] == "25" else "Sell 25%"

    token_info_message = (
        f"{token_info['symbol']} \\- {token_info['name']} [📈](https://dexscreener.com/{chain_id}/{token_address})\n"
        f"`{token_address}` _\\(Tap to copy\\)_ \n\n"
        f"*Price \\(USD\\):* {escape_dots(token_info['price_usd'])}\n"
        # f"*Liquidity \\(USD\\):* {escape_dots(token_info['liquidity_usd'])}\n"
        f"*FDV:* {token_info['fdv']}\n"
        # f"__Choose an action__\\:"
    )

    reply_keyboard = InlineKeyboardMarkup([
        [
            {"text": buy_button_text, "callback_data": "toggle_buy_mode"}
        ],
        [
            {"text": buy_0_1_sol_text, "callback_data": "buy_0.1_sol"},
            {"text": buy_0_5_sol_text, "callback_data": "buy_0.5_sol"},
        ],
        [
            {"text": buy_1_sol_text, "callback_data": "buy_1_sol"},
            {"text": "Buy with X SOL", "callback_data": "buy_x_sol"}
        ],
        [
            {"text": sell_button_text, "callback_data": "toggle_sell_mode"}
        ],
        [
            {"text": sell_25_text, "callback_data": "sell_25_percent"},
            {"text": sell_50_text, "callback_data": "sell_50_percent"},
        ],
        [
            {"text": sell_100_text, "callback_data": "sell_100_percent"},
            {"text": "Sell X%", "callback_data": "sell_x_percent"}
        ],
        # [
        #     {"text": "Execute", "callback_data": "execute_trade"}
        # ]
    ])

    await send_message(chat_id, token_info_message, context, reply_keyboard)


# async def insert(chat_id):
#     retrieved_user = await get_user_by_userId(int(chat_id))
#     print('retrieved_user',retrieved_user)
    
#     if(retrieved_user==None):
#         print('------creating new user')
#         keypair = Keypair()
#         private_key = encode_key(keypair.secret())
#         public_key = str(keypair.pubkey())
#         keypairStr = str(keypair)
#         new_user = UserModel(userId=int(chat_id), privateKey=private_key, publicKey=public_key, keypair=keypairStr)
#         await insert_user(new_user)
#     else:
#         print('------user already exist')
    
# async def getAllUsers():    
#     all_users = get_users()
#     for user in all_users:
#         print('ecoded-pk',decode_key(str(user.privateKey)))
#         print('-------------------------')

# async def getUser(uid):    
#     retrieved_user = await get_user_by_userId(int(uid))
#     print('retrieved_user',retrieved_user)
#     print('pk',decode_key(str(retrieved_user.privateKey)))


def main():
    print('started bot')
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('main', main_command))
    app.add_handler(CallbackQueryHandler(button_click_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    global helper
    helper = SolanaHelper()
    global jupiterHelper
    jupiterHelper = JupiterHelper()
    solanaConnected = helper.client.is_connected()
    # global client
    # client =  Client("https://api.devnet.solana.com")
    # solanaConnected = client.is_connected()
    if(solanaConnected):
        print('solana Connected')
    else:
        print('failed solana Connecttion')
        
    # asyncio.run(insert(9999999999))
    # asyncio.run(getUser(9999999999))
    # asyncio.run(getAllUsers())
    
    print('polling---')
    app.run_polling(poll_interval=3)



if __name__ == '__main__':
    main()
