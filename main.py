import numpy as np
#import bokeh

from requests.api import get
#import makerTakerOrderBookGraphs #type: ignore -this comment makes pylint ignore unresolved import error- file is importable
from websocket import WebSocketApp
import websocket
from functools import partial
import json
import threading
import time
from timeit import default_timer as timer #this is used to time tasks remove for production
import fnmatch # needed for string wildcard matching
import re # string matching regular expression library
import keyboard
import os
import argparse

# tradeAlarmPrice = {'upperLimit':None,'lowerLimit':None, 'audibleAlarm':False, 'textAlarm':False, 'lastAlarm':None}
# #parse arguments (if there were any) to skip using manual entry
# parser = argparse.ArgumentParser(description=' \n Warning: if you pass one argument you must pass all which you want as manual entry is skipped.')
# parser.add_argument('-l','--lolim', dest='lowerLimit', type=str, help='The lower limit at which an alarm should sound.') #can also use dest='lolim' to name the argument 
# parser.add_argument('-u','--uplim', dest='upperLimit', type=str, help='The upper limit at which an alarm should sound') #luckily python smart and already inferred this
# parser.add_argument('-a','--alarm', action='store_true', help='Will set audible alarm if present.') 
# parser.add_argument('-t','--text', action='store_true', help='Will send text message alert if present.')
# args = parser.parse_args()
# if args.lowerLimit != None: tradeAlarmPrice['lowerLimit'] = args.lowerLimit
# if args.upperLimit != None: tradeAlarmPrice['upperLimit'] = args.upperLimit
# if args.alarm == True: tradeAlarmPrice['audibleAlarm'] = True
# if args.text == True: tradeAlarmPrice['textAlarm'] = True

messageCounter=0

class coin:
    def __init__(self, name, groupAmt):
        self.coin = name.lower()
        self.symbol = name.lower() + "usdt"
        self.streams = [self.symbol + "@aggTrade", self.symbol + "@depth@1000ms"]
        self.SnapShotRecieved = False
        self.last_uID = 0
        self.eventTime = 0
        self.tradeSigFig = groupAmt   # this should be changed into a function that determines the grouping so that there are 5 significant figures for grouping eg, 40000 = 1 , 25 = 0.001 , 3 = 0.0001 , 0.99 = 0.00001
        self.ordBookBuff = []
        self.orderBook = {'bids':[], 'asks':[]}
        self.trades = {'bought':[[],[]], 'sold':[[],[]]}
        print(f'symbol : {self.symbol} \nstreams: {self.streams}')


    def updateOrderBook(self, side, update):
        price, quantity = update
        # price exists: remove or update local order
        for i in range(0, len(self.orderBook[side])):
            if price == self.orderBook[side][i][0]:
                # quantity is 0: remove
                if float(quantity) == 0:
                    # print('removing from orderbook')
                    #we need a try clause here as documentation states "Receiving an event that removes a price level that is not in your local order book can happen and is normal." which can cause issues
                    try:
                        self.orderBook[side].pop(i)
                    except:
                        pass
                    return
                else:
                    # quantity is not 0: update the order with new quantity
                    # print('updating orderbook')
                    self.orderBook[side][i] = update
                    return
        # price not found: add new order
        if float(quantity) != 0:
            self.orderBook[side].append(update)
            if side == 'asks':
                self.orderBook[side] = sorted(self.orderBook[side])  # asks prices in ascendant order
            else:
                self.orderBook[side] = sorted(self.orderBook[side], reverse=True)  # bids prices in descendant order
            # maintain side depth <= 1000
            if len(self.orderBook[side]) > 1000:
                self.orderBook[side].pop(len(self.orderBook[side]) - 1)
        # print('updated orderbook')
        #print(f"updated orderbook \nbids :\n{self.orderBook['bids'][:,25]}\nasks :\n{self.orderBook['asks'][:,25]}")

    def addTrade(self, tradeData, messageCount):
    # def addTrade(self, tradeData):
        #print(f"trade data:\n{tradeData}")
        # round all trades up to predetermined sigfigs
        price = float(tradeData['p']) - (float(tradeData['p']) % self.tradeSigFig) + self.tradeSigFig
        # if self.SnapShotRecieved == True:
        #     print(f"grouped {'sell ' if tradeData['m'] == True else 'buy ' }  trade {messageCount} {tradeData['p']} into  {price} ") # ↓ ↑
        # if buyer is market maker then this trade was a sell
        if tradeData['m'] == True:
            try:
                i = self.trades['sold'][0].index(price)
                self.trades['sold'][1][i] += float(tradeData['q'])
                #print(f"1 adding {tradeData['q']} to sell price {price}")
            except:
                self.trades['sold'][0].append(price)
                self.trades['sold'][1].append(float(tradeData['q']))
            #print(self.trades['sold'])
        else:
            try:
                i = self.trades['bought'][0].index(price)
                self.trades['bought'][1][i] += float(tradeData['q'])
                #print(f"3 adding {tradeData['q']} to buy price {price}")
            except:
                self.trades['bought'][0].append(price)
                self.trades['bought'][1].append(float(tradeData['q']))
    
    def setTimeStamp(self, eventTime):
        self.eventTime = eventTime
        print(f"event time set to {eventTime}")

    def logData(self):
        filename = 'db/' + str(self.eventTime) + '.txt'
        # print(f'creating file : {filename}')
        # file = open(filename, 'w')
        #file.write('trades:\n')
        with open(filename, 'w') as file:
            print('trades:\nbought:', file=file)
            #print(self.trades, file=file)

            # for sales in self.trades['bought']:
            #     print(sales, file=file)
            # print('sold:', file=file)
            # for sales in self.trades['sold']:
            #     print(sales, file=file)

            for sales in list(map(list, zip(*self.trades['bought']))):
                print(sales, file=file)
            print('sold:', file=file)
            for sales in list(map(list, zip(*self.trades['sold']))):
                print(sales, file=file)

            print('\norderbook:\nbids:', file=file)
            #print(self.orderBook, file=file)
            for ords in self.orderBook['bids']:
                print(ords, file=file)
            print('asks:', file=file)
            for ords in self.orderBook['asks']:
                print(ords, file=file)
            

        #file.write('\norderbook:\n')
        #file.close()

    #-------------------------------------

    '''Per the API () 
    listen to orderbook updates and log them, after a small delay get a snapshot of the current orderbook 
    and remove any updates that happened before the snapshot was taken and then apply any updates/messages
    that occured after the snapshot '''
    def bufferCleanup(self):
        while self.ordBookBuff[0]['u'] <= self.last_uID: #ordBookBuff[0]['u'] != None and
            print(f"deleting - eventtime: {self.ordBookBuff[0]['E']}  -  U ID : {self.ordBookBuff[0]['U']}   -   u ID : {self.ordBookBuff[0]['u']}")
            del self.ordBookBuff[0]
            if len(self.ordBookBuff) == 0:
                break
        print(f"new length : {len(self.ordBookBuff)} \n")
        if len(self.ordBookBuff) >= 1 :
            print(f"first UID left in buffer {self.ordBookBuff[0]['U']} -  last uID in buffer : {self.ordBookBuff[-1]['u']}")
            print(f" buffer size : {len(self.ordBookBuff)}")
            updateInd = 0
            for eachUpdate in self.ordBookBuff:
                print(f" performing update # {updateInd + 1}")
                last_uID = eachUpdate['u']
                for eachBid in eachUpdate['b']:
                    self.updateOrderBook('bids', eachBid)
                for eachAsk in eachUpdate['a']:
                    self.updateOrderBook('asks', eachAsk)
            self.ordBookBuff = []
        else:
            print("nothing left in buffer - taking next available message frame \n")
    
    def getOrderBookSnapshot(self):
        API_endpoint = 'https://api.binance.com'  # url of api server
        getObjectEndpoint = 'api/v3/depth'
        parameterNameSymbol = 'symbol'
        parameterValueSymbol = self.symbol.upper()
        parameterNameLimit = 'limit'
        parameterValueLimit = '1000'
        orderBookURL = f'{API_endpoint}/{getObjectEndpoint}?{parameterNameSymbol}={parameterValueSymbol}&{parameterNameLimit}={parameterValueLimit}'  # /{orderbookDepth}
        orderBookEncoded = get(orderBookURL) #import requests   then this line becomes request.get(orderBookURL)
        if orderBookEncoded.ok: #process it if we get a response of ok=200
            rawOrderBook = orderBookEncoded.json() #returns a dataframe ----also has code to return lists of dictionaries with bids and prices
            print(f'\nSuccesfully retreived order book!\n') 
            #dictOrderBook = {'bids':  rawOrderBook['bids'],'asks': rawOrderBook['asks']}
            #get rid of all updates to order book in our orberbook changes buffer that occured before we got our snapshot
            self.orderBook.update(bids = rawOrderBook['bids'], asks = rawOrderBook['asks'])
            self.last_uID = rawOrderBook['lastUpdateId']
            self.SnapShotRecieved = True
            self.bufferCleanup()
            #return {"orderBook" : {'bids':  rawOrderBook['bids'],'asks': rawOrderBook['asks']}, "uID" : rawOrderBook['lastUpdateId']}
        else:
            print('Error retieving order book.') #RESTfull request failed 
            print('Status code : '+ str(orderBookEncoded.status_code))
            print('Reason : '+ orderBookEncoded.reason)
            #return None

    # need this for storage 
    # currently we have 2 lists in bought/sold one with price and other quantity and index relates them this makes searching for and adding to a price easier/quicker but for storing we need to transpose into a list of [price, quantity] lists
    # def transpose(self, lst):
    #     transposed = list(map(list, zip(*lst)))
    #     return transposed
    # and this sorts the array/list self.orderBook[side] = sorted(self.orderBook[side], reverse=True)



# def priceAlarm(price):
#     if (price <= tradeAlarmPrice['lowerLimit'] or price >= tradeAlarmPrice['upperLimit']) and (tradeAlarmPrice['lastAlarm']==None or tradeAlarmPrice['lastAlarm']+420 < time.time()):
#       tradeAlarmPrice['lastAlarm'] = time.time() #reset last time we played an alarm
#       f="alarm-sound.mp3"
#       os.system(f)

# {"stream":"btcusdt@depth@1000ms","data":{"e
def on_message(ws, message, SecuritiesRef):
    global messageCounter
    messaged = json.loads(message)
    CoinObj = SecuritiesRef[messaged['stream'].partition('usdt')[0]]
    # print(f"message recieved for coin: {getattr(CoinObj, coin)}")
    # print(f"message recieved for coin: {getattr(CoinObj, 'coin')}")
    if fnmatch.fnmatch(messaged['stream'], "*@depth@1000ms") :
        messageCounter=0
        # print(f"orderbook update for {getattr(CoinObj, 'coin')} ") #{getattr(CoinObj, 'SnapShotRecieved')}
        if CoinObj.SnapShotRecieved == False:
            #print('not received')
            CoinObj.ordBookBuff.append(messaged['data'])
            print('appending message to buffer')
        else:
            print(f"orderbook update for {getattr(CoinObj, 'coin')} with eventtime : {messaged['data']['E']}")
            CoinObj.setTimeStamp(messaged['data']['E'])
            for eachUpdate in messaged['data']['b']:
                CoinObj.updateOrderBook('bids', eachUpdate)
            for eachUpdate in messaged['data']['a']:
                CoinObj.updateOrderBook('asks', eachUpdate)
            CoinObj.logData()
    #elif messaged['stream'] == 'btcusdt@aggTrade':
    elif fnmatch.fnmatch(messaged['stream'], "*@aggTrade"):
        messageCounter+=1
        #print(f"Trade occured for {getattr(CoinObj, 'coin')} - trades since orderbook update: {messageCounter}")
        CoinObj.addTrade(messaged['data'], messageCounter)
        # priceAlarm(messaged['data']['p'])
    else:      #the catch all statement that lets us know we dun fucked up
        print('You fucked something up.')



def on_error(ws, error):
    print(error)

def on_close(ws):
    print("closed connection")

def on_open(ws, url):
    print(f'opened connection to : {url} \n')


def main():
    # websocket.enableTrace(True) # <-- for debugging websocket library/stream

    # instantiating objects for various securities
    btc = coin("BTC", 1)
    # ada = coin("ADA"); eth = coin("ETH"); dot = coin("DOT", 0.001)

    # list of objects that will be used to create the base uri endpoint and subscribe to thei relative streams
    # Securities = {'btc':btc, 'ada':ada, 'eth':eth, 'dot':dot}
    Securities = {'btc':btc}
    #Securities = {'dot':dot}

    # genertate the base url
    uriEndpoint = "wss://stream.binance.com:9443"
    streams = []    # streams = ('btcusdt@aggTrade','btcusdt@depth@100ms',)

    for coinobjects in Securities.values():
        for points in coinobjects.streams:
            streams.append(points)
    if len(streams) <= 1 :
        uriEndpoint += '/ws/' + streams[0]
    else:
        uriEndpoint += '/stream?streams='
        for index, item in enumerate(streams):
            uriEndpoint +=  item
            if index-1 < len(streams)-2:
                uriEndpoint += '/'
    print(f"uri endpoint : {uriEndpoint}")

    # debug
    messageCounter = 0

    ws = WebSocketApp(uriEndpoint, on_open=partial(on_open, url=uriEndpoint), on_message=partial(on_message, SecuritiesRef=Securities), on_error=on_error, on_close=on_close) #, on_ping=on_ping
    listeningForMessages = threading.Thread(target = ws.run_forever, daemon=True) #threading.Thread(target = ws.run_forever, daemon=True, kwargs={'ping_interval':300, 'ping_timeout':10, 'ping_payload':'pong'})
    listeningForMessages.start()
    #need to allow buffer to fill up alittle in order to get snapshot and then apply correct updates/mesages to orderbook as per API documentation
    time.sleep(2)

    for coinObjects in Securities.values():
        coinObjects.getOrderBookSnapshot()

    keyboard.wait('esc')

    ws.close()
    listeningForMessages.join()
    print(f"active threads (should be 1) : {threading.active_count()}")
    exit(0)

if __name__ == "__main__":
    main()