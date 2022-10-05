#!/usr/bin/env python
from requests.api import get
import asyncio
import websocket
import json
import time
from functools import partial
import logging
import os, sys
import threading

class coin:
    def __init__(self, name):
        self.ticker = name.upper()
        self.message_sequence_id = 0
        self.message_buffer = []
        self.received_orders = []
        self.orderBook = {'bids':{}, 'asks':{}}
        self.trades = {'bought':{}, 'sold':{}} # in respect to the aggresor / taker behaviour - e.g market order to buy would be a 'bought event'
        self.got_orderbook_snapshot = False
        self.last_trade = []
        self.retreive_orderbook_pause_event = threading.Event()

    
    def get_orderbook_snapshot(self):
        self.retreive_orderbook_pause_event.wait(0.5) # nonblocking pause for 0.5 secs
        url = "https://api.exchange.coinbase.com/products/"+ self.ticker +"/book?level=3"
        headers = {"Accept": "application/json"}
        response = get(url=url, headers=headers)
        if response.ok:
            logger.info(f'Succesfully retrieved orderbook for {self.ticker}')
            orderbook_response = response.json()
            self.message_sequence_id = orderbook_response['sequence']
            for orders in orderbook_response['bids']:
                self.orderBook['bids'].update({orders[2]:[float(orders[0]), float(orders[1])]})
            for orders in orderbook_response['asks']:
                self.orderBook['asks'].update({orders[2]:[float(orders[0]), float(orders[1])]})
            # new messages may come in while we are processing old ones so we cant just loop over the buffer and process them
            # we must take the first element of the buffer, process it, remove it and move on until no more are left
            logger.debug(f"Processing message buffer.  Length of message buffer: {len(self.message_buffer)}")
            while len(self.message_buffer) > 0:
                logger.debug(f'message buffer length: {len(self.message_buffer)} ')
                if self.message_buffer[0]['sequence'] <= self.message_sequence_id:
                    logger.debug(f'Popped message with sequence id:{self.message_buffer[0]["sequence"]} - snapshot sequence id: {self.message_sequence_id} ')
                    self.message_buffer.pop(0)
                else:
                    logger.debug(f'Processing order in buffer - msg sequence: {self.message_buffer[0]["sequence"]} - ordbook sequence: {self.message_sequence_id} ')
                    self.process_message(self.message_buffer[0], True)
                    logger.debug(f'Removing processed message.')
                    self.message_buffer.pop(0)
            logger.debug(f"Done processing message buffer. Verifying length of message buffer is 0 - {'True' if len(self.message_buffer) == 0 else 'False' }")
            self.got_orderbook_snapshot = True
        else:
            logger.error(f'Error retieving order book. Status code : {str(response.status_code)} -- Reason : {response.reason}')
        self.retreive_orderbook_pause_event.clear()
    
    def process_message(self, message, *buffer_message):
        if self.got_orderbook_snapshot is False and not buffer_message: # need this buffer message check or else well just keep adding messages we intend to proces to the end of buffer
            logger.debug(f'appending with sequence_id {message["sequence"]} to buffer')
            self.message_buffer.append(message)
        else:
            # check messages are coming in correctly
            if message['sequence'] != self.message_sequence_id +   1:
                logger.error(f'message out of order - last sequence # applied: {self.message_sequence_id} - current message sequence #: {message["sequence"]}')
                return
            # ✔ confirmed received order - goes into matching engine
            if message['type'] == 'received':
                # !!! good location to track market orders (aggressive taker behavuior) vs limit orders
                self.received_orders.append(message)
                logger.debug(f'new order {message["order_id"]} being placed into "received but not yet open (RNYO)" state')
            # ✔  order moves from incoming order to orderbook  - e.g. whatever wasnt filled comes out of amtching engine onto orderbook
            elif message['type'] == 'open':
                logger.debug(f'Moving order# {message["order_id"]} from received state onto orderbook')
                # remove from "received but not yet open (RNYO)" state
                try:
                    order_location = [msg['order_id'] for msg in self.received_orders].index(message['order_id'])
                    self.received_orders.pop(order_location)
                except:
                    logger.warn(f'Couldnt find/remove order# {message["order_id"]} from "received but not yet open (RNYO)" state')
                # add to orderbook
                self.orderBook['asks' if message['side'] == 'sell' else 'bids'][message['order_id']] = [float(message['price']) , float(message['remaining_size'])]
            # ✔ order is no longer on the order book or in the "received but not yet open (RNYO)" state
            elif message['type'] == 'done':
                logger.debug(f'Order {message["order_id"]} finished reason: {message["reason"]} - removing from "received but not yet open (RNYO)" state and/or orderbook')
                try:
                    order_location = [msg['order_id'] for msg in self.received_orders].index(message['order_id'])
                    self.received_orders.pop(order_location)
                    logger.debug(f'{message["order_id"]} removed from "received but not yet open (RNYO)" state ')
                except:
                    if message['order_id'] in  self.orderBook['asks' if message['side'] == 'sell' else 'bids']:
                        del  self.orderBook['asks' if message['side'] == 'sell' else 'bids'][message['order_id']]
                        logger.debug(f'{message["order_id"]} removed from orderbook ')
                    else:
                        logger.warn(f'order was not found in orderbook or "received but not yet open (RNYO)" state')
                # !!!! need to log cancelled orders somehow for the machne learning model
                if message['reason'] == 'canceled':
                    pass
            # ✔ A trade occurred between two orders
            # this will only be used to log trades as the done messages should take care of maintaining orderbook
            # it can be used to create up to date candle sticks - sell this indicates the maker was a sell order and the match is considered an up-tick. A buy side match is a down-tick.
            elif message['type'] == 'match':
                # log the trade
                logger.debug(f'trade occured between {message["maker_order_id"]} and {message["taker_order_id"]} ')
                aggresor_side = 'bought' if message['side'] == 'sell' else 'sold'
                self.trades[aggresor_side][float(message['price'])] = message['size']
                self.last_trade = [message['price'], message['size']]
            # ✔ change an order - from what i understand only happens due to self trade prevention but can also happen to order on orderbook although not sure how this is accomplished 
            elif message['type'] == 'change':
                try:
                    order_location = [msg['order_id'] for msg in self.received_orders].index(message['order_id'])
                    if self.received_orders[order_location]['size'] != message['old_size']:
                        logger.warn(f'order sizes for change message for {message["order_id"]} do not match up; original size:{self.received_orders[order_location]["size"]} - message "old size":{ message["old_size"]}')
                    elif self.received_orders[order_location]['price'] != message['price']:
                        logger.warn(f'order prices for change message for {message["order_id"]} do not match up; original price:{self.received_orders[order_location]["price"]} - message price:{ message["price"]}')
                    else:
                        self.received_orders[order_location]['size'] = message['new_size']
                        logger.debug(f'Changed order {message["order_id"]} size from {message["old_size"]} to {message["new_size"]}')
                except:
                    logger.debug(f"change order was not found in \"received but not yet open (RNYO)\" state, checking orderbook ")
                    if message['order_id'] in self.orderBook['asks' if message['side'] == 'sell' else 'bids']:
                        if self.orderBook['asks' if message['side'] == 'sell' else 'bids'][message['order_id']] == message['old_size']:
                            logger.debug(f'Updating orderbook order {message["order_id"]} size from {message["old_size"]} to {message["new_size"]}')
                            self.orderBook['asks' if message['side'] == 'sell' else 'bids'][message['order_id']] = {float(message['price']) : float(message['new_size'])}
                        else:
                            logger.error(f'Orderbook change message old_size {message["old_size"]} does not match with what is in our orderbook {self.orderBook["asks" if message["side"] == "sell" else "bids"][message["order_id"]]}')
                    else:
                        logger.warn(f"Order refrenced for change ({message['order_id']}) does not exist in either orderbook or \"received but not yet open (RNYO)\" state")
            # a stop order is triggered and another marekt/limit order takes its place
            elif message['type'] == 'activate':
                # !!!!!!!!!!! neeed to implement this  for the machne learning model
                logger.debug(f'received an activate order message - someones stop loss was triggered')
            else:
                logger.error(f'incoming message not handled correctly.  Message: {message}')
            # but not matter the message we have to keep track to make sure we didnt miss one
            self.message_sequence_id = message['sequence']
        # received
        # open
        # done
        # match
        # change
        # activate
        # if len(self.message_buffer)== 0: self.livelog()

    def livelog(self):
        UP = "\x1B[3A"
        CLR = "\x1B[0K"
        best_bid = max([ord[0] for ord in (self.orderBook['bids'][ord_id] for ord_id in self.orderBook['bids'])])
        best_ask = min([ord[0] for ord in (self.orderBook['asks'][ord_id] for ord_id in self.orderBook['asks'])])
        print('\n\n')
        print(f'{UP*2}Recieved orders: {len(self.received_orders)}{CLR}\n{[msg["order_id"] for msg in self.received_orders]}{CLR}\nBest bid:{best_bid} Best ask:{best_ask} last trade:{self.last_trade if len(self.last_trade) == 2 else "no trades yet"}{CLR}')


def on_message(ws, message, securities):
    msg = json.loads(message)
    try:
        if 'product_id' in msg:
            securities[msg['product_id']].process_message(msg)
        elif msg['type'] == 'subscriptions':
            logger.info(f"Successfully subscribed to {msg['channels'][0]['product_ids']}")
        else:
            print(f"message seems to have unexpected schema.  Message: {message}\nparsed message: {msg}")
            logger.warn(f"message seems to have unexpected schema.  Message: {message}\nparsed message: {msg}")
    except Exception as e:
        print(f'Error: {e}\nMessage not being handled correctly: {message}\nparsed message: {msg}\ntype:{msg} product id? {"True" if "product_id" in msg else "False"}')
        logger.error(f'Error: {e}\nMessage not being handled correctly: {message}\nparsed message: {msg}\ntype:{msg} product id? {"True" if "product_id" in msg else "False"}')

def on_error(ws, error):
    logger.error(f"Error occured: {error}")

def on_close(ws, close_status_code, close_msg):
    logger.info(f"Websocket connection closed - close_status_code : {close_status_code} close_msg: {close_msg} ")

def on_open(ws, securities):
    logger.info("Opened websocket connection")
    products = []
    for security in securities.values():
        products.append(security.ticker)
        retreive_orderbook_snapshot = threading.Thread(target=security.get_orderbook_snapshot, name=('get_'+security.ticker+'_orderbook_thread'), daemon=True)
        retreive_orderbook_snapshot.start()
    subscription_request = {'type':'subscribe', 'product_ids':products, 'channels':['full']}
    ws.send(json.dumps(subscription_request))

def main():
    #-----------------------------------------------------------------------------------------------------------------------
    # websocket.enableTrace(True)
    # wss://ws-feed.exchange.coinbase.com
    # coinbase is different than binance - they require a connection and then a subscribe message
    # they also do it differently (were going to use l2 channel - https://docs.cloud.coinbase.com/exchange/docs/websocket-channels#the-level2-channel )
    # we subscribe
    # they send a message with the current orderbook 
    # subsequent messages are updates to the orderbook
    # ALSO: going to need to utilize full/heartbeat channel to ensure were getting messages in order and none are missed
    # ws = websocket.WebSocketApp("wss://api.gemini.com/v1/marketdata/BTCUSD", on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    # ws.run_forever()
    #-----------------------------------------------------------------------------------------------------------------------
    securities = {'BTC-USD': coin("BTC-USD")}
    # for security in securities:
    #     securities[security].get_orderbook_snapshot()
    
    ws = websocket.WebSocketApp("wss://ws-feed.exchange.coinbase.com", on_open=partial(on_open, securities=securities), on_message=partial(on_message, securities=securities), on_error=on_error, on_close=on_close)
    # print(f'2 - thread count: {threading.active_count()}\nActive threads: {threading.enumerate()}')
    listen_for_msg_thread = threading.Thread(target = ws.run_forever, name='WebSocketAppThread', daemon=True)
    listen_for_msg_thread.start()
    # print(f'3 - thread count: {threading.active_count()}\nActive threads: {threading.enumerate()}')
    # pause until key is pressed
    try:
        # print(f'4 - thread count: {threading.active_count()}\nActive threads: {threading.enumerate()}')
        input("\n\n\nPress enter to continue\n")
    except SyntaxError:
        pass


if __name__ == "__main__":
    if os.path.exists("vars.env") and os.getenv('USE_ENV_FILE','False') == 'True':
        from dotenv import load_dotenv
        load_dotenv()
    #websocket.enableTrace(True)
    log_level = os.getenv('LOGLEVEL','Debug').upper()    # highest level of information that we should log
    logger = logging.getLogger()
    # logger.setLevel(logging.DEBUG)
    logger.setLevel(logging.getLevelName(log_level))
    stdout_handler = logging.StreamHandler(sys.stdout)
    # stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setLevel(logging.getLevelName(log_level))
    stdout_handler.setFormatter(logging.Formatter('%(asctime)s : %(levelname)s : %(message)s'))
    # logger.addHandler(stdout_handler)
    file_handler = logging.FileHandler('coinbase_log')
    file_handler.setLevel(logging.getLevelName(logging.DEBUG))
    file_handler.setFormatter(logging.Formatter('%(asctime)s : %(levelname)s : %(message)s'))
    logger.addHandler(file_handler)
    main()


# // Request
# // Subscribe to ETH-USD and ETH-EUR with the level2, heartbeat and ticker channels,
# // plus receive the ticker entries for ETH-BTC and ETH-USD
# {
#     "type": "subscribe", 
#     "product_ids": [ "ETH-USD", "ETH-EUR"],
#     "channels": [ "level2", "heartbeat", { "name": "ticker", "product_ids": [ "ETH-BTC", "ETH-USD" ] }]
# }