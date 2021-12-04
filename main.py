import numpy as np
from requests.api import get
from websocket import WebSocketApp
from functools import partial
import json
import threading
import time
import fnmatch # needed for string wildcard matching
import keyboard
from pymongo import MongoClient
from pprint import pprint


class coin:
    def __init__(self, name, groupAmt, DBConn):
        self.coin = name.lower()
        self.symbol = name.lower() + "usdt"
        self.streams = [self.symbol + "@aggTrade", self.symbol + "@depth@1000ms"]
        self.SnapShotRecieved = False
        self.last_uID = 0
        self.eventTime = 0
        self.tradeSigFig = groupAmt   # this should be changed into a function that determines the grouping so that there are 5 significant figures for grouping eg, 40000 = 1 , 25 = 0.001 , 3 = 0.0001 , 0.99 = 0.00001
        self.ordBookBuff = []
        self.orderBook = {'bids':{}, 'asks':{}}
        self.trades = {'bought':{}, 'sold':{}}
        self.DBConn = DBConn[self.symbol]
        # print(f'symbol : {self.symbol} \nstreams: {self.streams}')
        # time.sleep(2)
        # self.getOrderBookSnapshot()
    
    def updateOrderBook(self, message):
        if message['U'] > self.last_uID + 1:
            print(f"ERROR {self.symbol} updateID for {message['E']} was not what was expected - last_uID logged: {self.last_uID} | uID (first event) of this message : {message['U']} - difference : {float(message['U']) - self.last_uID}")
            self.SnapShotRecieved = False
            self.orderBook = {'bids':{}, 'asks':{}}
            time.sleep(2)
            self.getOrderBookSnapshot()
        self.eventTime = message['E']
        self.last_uID = message['u']
        for side in ['a','b']:
            bookSide = 'bids' if side == 'b' else 'asks'
            counter = 0
            for update in message[side]:
                counter += 1
                if float(update[1]) == 0:
                    #we need a try clause here as documentation states "Receiving an event that removes a price level that is not in your local order book can happen and is normal." which can cause issues
                    try:
                        del self.orderBook[bookSide][float(update[0])]
                    except:
                        pass
                else:
                    self.orderBook[bookSide].update({float(update[0]): float(update[1])})
        # not entirely sure why but it seems when the orderbook grows bigger than 1000 on either side we need to remove the highest ask and lowest bid in order to keep orders from one side flowing into the other
            counter = 0
            while len(self.orderBook[bookSide]) > 1000:
                counter += 1
                # print(f"{counter} - deleting {bookSide} side of orderbok which contained {min(self.orderBook['bids'], key=self.orderBook['bids'].get) if side == 'b' else max(self.orderBook['asks'], key=self.orderBook['asks'].get)}")
                del self.orderBook[bookSide][(min(self.orderBook['bids'], key=self.orderBook['bids'].get)) if side == 'b' else (max(self.orderBook['asks'], key=self.orderBook['asks'].get))]
        if max(self.orderBook['bids'], key=self.orderBook['bids'].get) > min(self.orderBook['asks'], key=self.orderBook['asks'].get) :
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!ERROR!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(f"max bid : { (max(self.orderBook['bids'], key=self.orderBook['bids'].get))} - min ask : {min(self.orderBook['asks'], key=self.orderBook['asks'].get)}")
        self.logData()

    def addTrade(self, tradeData): # 
        # round all trades up to predetermined sigfigs
        price = float(tradeData['p']) - (float(tradeData['p']) % self.tradeSigFig) + self.tradeSigFig
        # if buyer is market maker then this trade was a sell
        if tradeData['m'] == True:
            # print(f'-{self.coin} sell- {tradeData["E"]} - {tradeData["p"]} is updating {price} by adding {tradeData["q"]} to {self.trades["sold"][price] if price in self.trades["sold"] else 0} to get {(self.trades["sold"][price] if price in self.trades["sold"] else 0) + float(tradeData["q"])}')
            self.trades['sold'].update({price:((self.trades["sold"][price] if price in  self.trades["sold"] else 0) + float(tradeData["q"]))})
        else:
            # print(f'-{self.coin} buy- {tradeData["E"]} - {tradeData["p"]} is updating {price} by adding {tradeData["q"]} to {self.trades["bought"][price] if price in  self.trades["bought"] else 0} to get {(self.trades["bought"][price] if price in  self.trades["bought"] else 0) + float(tradeData["q"])}')
            self.trades['bought'].update({price:((self.trades["bought"][price] if price in self.trades["bought"] else 0) + float(tradeData["q"]))})

    def logData(self):
        filename = 'db/' + self.coin + str(self.eventTime) + '.txt'
        # at this point we wrap up all events between last function call (orderbook update) and now (this function call / orderbook update), put them in a temporary object, clear the logging object and log the original (temporary/old) data
        with open(filename, 'w') as file:
            # print('trades:\nbought:', file=file)            
            # for price, amount in self.trades['bought'].items() : #self.trades['bought'].items()   # toLog['bought'].items()
            #     print(f"{price} : {amount}", file=file)
            # print('sold:', file=file)
            # for price, amount in self.trades['bought'].items() :   
            #     print(f"{price} : {amount}", file=file)
            # print('\norderbook:\nbids:', file=file)
            # for price, amount in self.orderBook['bids'].items(): #self.trades['bought'].items()
            #     print(f"{price} : {amount}", file=file)
            # print('asks:', file=file)
            # for price, amount in self.orderBook['asks'].items():  
            #     print(f"{price} : {amount}", file=file)
            # and here the entire thing would be JSON encoded and logged - need to figure out it orderbook and trades are a dictionary or tuple/list or some variant there of
            print(json.dumps({ "_id" : self.eventTime, 'trades': self.trades, 'orderbook': self.orderBook}), file=file)
        self.trades = {'bought':{}, 'sold':{}}

    def mongolog(self):
        insertData = { "_id" : self.eventTime, "trades" : self.trades,  "orberbook" : self.orderBook }
        try:
            result=self.DBConn.insert_one(insertData)
            print(f"Inserted : \n {result}")
        except Exception as e:
            print(f"Already inserted\Error occured : \n {e}")
    
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
            print(f'\nSuccesfully retreived order book for  {self.symbol}!\n')
            # we dont really want any incoming orderbook updates to interrupt (re)setting the orderbook so we lock the thread for this portion
            with threading.Lock():
                #get rid of all updates to order book in our orberbook changes buffer that occured before we got our snapshot
                for orders in rawOrderBook['bids']:
                    self.orderBook['bids'].update({float(orders[0]): float(orders[1])})
                for orders in rawOrderBook['asks']:
                    self.orderBook['asks'].update({float(orders[0]): float(orders[1])})
                self.last_uID = rawOrderBook['lastUpdateId']
                self.SnapShotRecieved = True
                #----update buffer section-------- may need to be broken back out if we decide to make all coins orderbook requests in one api call
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
                        print(f" performing update for # {updateInd + 1} for {self.symbol}")
                        self.last_uID = eachUpdate['u']
                        self.updateOrderBook(eachUpdate)
                    self.ordBookBuff = []
                else:
                    print("nothing left in buffer - taking next available message frame \n")
                #------------------------------
        else:
            print('Error retieving order book.') #RESTfull request failed 
            print('Status code : '+ str(orderBookEncoded.status_code))
            print('Reason : '+ orderBookEncoded.reason)

def on_message(ws, message, SecuritiesRef):
    messaged = json.loads(message)
    #print(messaged)
    CoinObj = SecuritiesRef[messaged['stream'].partition('usdt')[0]]
    if fnmatch.fnmatch(messaged['stream'], "*@depth@1000ms") :
        if CoinObj.SnapShotRecieved == False:
            CoinObj.ordBookBuff.append(messaged['data'])
            print('appending message to buffer')
        else:
            print(f"orderbook update for {getattr(CoinObj, 'coin')} with eventtime : {messaged['data']['E']} - last recorded ID {CoinObj.last_uID} - message: first UID: {messaged['data']['U']}  last uID : {messaged['data']['u']} ")
            CoinObj.updateOrderBook(messaged['data'])
    elif fnmatch.fnmatch(messaged['stream'], "*@aggTrade"):
        CoinObj.addTrade(messaged['data']) #, messaged['E']
    else:      #the catch all statement
        print('Incoming message being handled incorrectly.')

def on_error(ws, error):
    print(error)

def on_close(ws):
    print("closed connection")

def on_open(ws, url):
    print(f'opened connection to : {url} \n')

def main():
    # mongoDB connection object which we will use to log to database
    client = MongoClient('192.168.1.254:27017', username='mainworker', password='qwdgBm4vP5P5AkhS', authSource='orderbook&trades', authMechanism='SCRAM-SHA-256')
    DBConn = client['orderbook&trades']

    # instantiating objects for various securities - list of objects that will be used to create the base uri endpoint and subscribe to their relative streams
    Securities = {'btc':coin("BTC", 1, DBConn), 'ada':coin("ADA", 0.0001, DBConn), 'eth':coin("ETH", 0.1, DBConn), 'dot':coin("DOT", 0.001, DBConn)} # 10,000-100,000 : 1 \ 1,000-10,000 : 0.1 \ 100-1000 : 0.01 \ 10-100 : 0.001 \ 1-10 : 0.0001
    # genertate the base url from list of objects/securities
    uriEndpoint = "wss://stream.binance.com:9443"
    streams = []
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



    # websocket for handling updates
    ws = WebSocketApp(uriEndpoint, on_open=partial(on_open, url=uriEndpoint), on_message=partial(on_message, SecuritiesRef=Securities), on_error=on_error, on_close=on_close) #, on_ping=on_ping
    listeningForMessages = threading.Thread(target = ws.run_forever, daemon=True) #threading.Thread(target = ws.run_forever, daemon=True, kwargs={'ping_interval':300, 'ping_timeout':10, 'ping_payload':'pong'})
    listeningForMessages.start()
    #need to allow buffer to fill up alittle in order to get snapshot and then apply correct updates/mesages to orderbook as per API documentation
    time.sleep(2)
    for coinObjects in Securities.values():
        coinObjects.getOrderBookSnapshot()
    # we basically wait here until we press esc
    keyboard.wait('esc')
    ws.close()
    listeningForMessages.join()
    exit(0)

if __name__ == "__main__":
    main()