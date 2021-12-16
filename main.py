import numpy as np
from requests.api import get
from websocket import WebSocketApp
from functools import partial
import json
import threading
import time
import fnmatch # needed for string wildcard matching
from keyboard import wait as keyboardwait
from pymongo import MongoClient
from multiprocessing.managers import BaseManager
from datetime import datetime # dtime = datetime.now(); unixtime = time.mktime(dtime.timetuple()) -  datetime.utcfromtimestamp(messaged['E']/100).strftime('%Y-%m-%d %H:%M:%S')}

class RemoteOperations:
    def __init__(self, ws, securitiesRef, messageServer, DBConn):
        self.websocketConnection = ws
        self.securities = securitiesRef
        # were using BaseManager from multiprocessing library to incorporate inter process communication 
        # although it/we doesn't/aren't actually start a new process but instead using a thread to accomodate this
        # functionality we need a way to terminate this thread - we do thhis by setting a stop event that in turn teminates itself
        self.messageServer = messageServer
        self.DBConn = DBConn

    def addsecurity(self, newcoin, groupAmt, *pair):
        self.securities[newcoin] = coin(newcoin, groupAmt, self.DBConn)

    def test(self):
        print("Self test")
        rtnlist = []
        for items in self.securities.values():
            rtnlist.append(items.symbol)
        return {"websocket": type(self.websocketConnection), "coins": rtnlist}
    
    def terminate(self):
        print("Remote terminate command received")
        self.messageServer.stop_event.set()

class coin:
    def __init__(self, name, groupAmt, DBConn, sigTradeLim=10000):
        self.coin = name.lower()
        self.symbol = name.lower() + "usdt"
        # if name.lower().partition('usdt')[0] == 'usdt':
        #     self.symbol = name.lower() + "usdt"
        # else:
        #     self.symbol = name.lower()
        self.streams = [self.symbol + "@aggTrade", self.symbol + "@depth@1000ms"]
        self.SnapShotRecieved = False
        self.last_uID = 0
        self.eventTime = 0
        self.tradeSigFig = groupAmt   # this should be changed into a function that determines the grouping so that there are 5 significant figures for grouping eg, 40000 = 1 , 25 = 0.001 , 3 = 0.0001 , 0.99 = 0.00001
        self.ordBookBuff = []
        self.orderBook = {'bids':{}, 'asks':{}}
        self.trades = {'bought':{}, 'sold':{}}
        self.DBConn = DBConn[self.symbol]
        # self.DBConn = DBConn[self.symbol]
        # print(f'symbol : {self.symbol} \nstreams: {self.streams}')
        # time.sleep(2)
        # self.getOrderBookSnapshot()
        self.significantTradeLimit = sigTradeLim
        self.significantTradeEvents = [] 
        # we want to grab an orderbook snapshot every x seconds (30 min) unless a message error occurs (e.g. an incoming update has an unexpected updateID indicating we missed an update message)
        #  therefore we have a thread that just waits for the timer to run out or the event to be set and requests another snapshot
        self.snapshotTimerError = threading.Event()

    def updateOrderBook(self, message):
        if message['U'] > self.last_uID + 1:
            errormsg = f"ERROR {self.symbol} updateID for {message['E']} was not what was expected - last_uID logged: {self.last_uID} | uID (first event) of this message : {message['U']} - difference : {float(message['U']) - self.last_uID}"
            print(errormsg)
            self.logMessage(errormsg, priority=3)
            self.SnapShotRecieved = False
            self.orderBook = {'bids':{}, 'asks':{}}
            self.snapshotTimerError.set()
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
            errormesg = f"ERROR! - Orderbook ask/bid Overlap! \nmax bid : { (max(self.orderBook['bids'], key=self.orderBook['bids'].get))} - min ask : {min(self.orderBook['asks'], key=self.orderBook['asks'].get)}"
            self.logMessage(errormesg, priority=2)
            self.snapshotTimerError.set()
        self.mongolog()

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
        if float(tradeData['p']) * float(tradeData['q']) >= self.significantTradeLimit:
            self.significantTradeEvents.append({float(tradeData['p']): float(tradeData['q'])})
        
    def messageupdates(self, message):
        # because it saves space to only log updates rather than the entire orderbook we will turn the updates into a dictionary (because it is easier for us to handle than a list) 
        # that can then be applied to the orderbook at the previous timestamps condition
        updatedict = {}
        for sides in ["a","b"]:
            for update in message[sides]:
                updatedict.update({update[0]: float(update[1])})
        self.mongolog("update", updatedict)


    def logMessage(self, message, **priority):
        filename = 'db/' + self.coin + str(self.eventTime) + '.txt'
        # at this point we wrap up all events between last function call (orderbook update) and now (this function call / orderbook update), put them in a temporary object, clear the logging object and log the original (temporary/old) data
        with open(filename, 'a') as file:
            print(f"{datetime.now()} - {'' if priority.get('lvl') == None else  '- priority: '+str(priority['lvl'])} - {message}", file=file)
            # print(json.dumps({ "_id" : self.eventTime, 'trades': self.trades, 'orderbook': self.orderBook}), file=file)
        # self.trades = {'bought':{}, 'sold':{}}
        # self.significantTradeEvents = [] 
        # dtime = datetime.now(); unixtime = time.mktime(dtime.timetuple())
        # print(f"time right now: {dtime} corresponding unix timestamp : {unixtime}")
        # print(f"now backwards- unix timsetamp now: {unixtime} converted : {datetime.utcfromtimestamp(unixtime).strftime('%Y-%m-%d %H:%M:%S')}")

    def mongolog(self, messagetype, *update):
        ident =  str(time.mktime(datetime.now().timetuple())*1000)+("snapshot" if messagetype == "orderbooksnapshot" else "update")
        insertData = { "_id" : ident, "type": "snapshot" if messagetype == "orderbooksnapshot" else "update", "DateTime": datetime.utcnow(), "symbol": self.symbol, "trades" : self.trades,  "orberbook" : self.orderBook if messagetype == "orderbooksnapshot" else update} # convert fro;m timestamp to dat time: datetime.utcfromtimestamp(float(messaged['E'])/1000).strftime('%Y-%m-%d %H:%M:%S') 
        if len(self.significantTradeEvents) != 0:
            insertData.update({'significantTradeEvents': self.significantTradeEvents})
        try:
            result=self.DBConn.insert_one(insertData)
            print(f"Inserted : \n {result}")
        except Exception as e:
            print(f"Already inserted\Error occured : \n {e}")
        self.trades = {'bought':{}, 'sold':{}}
        self.significantTradeEvents = [] 
    
    def snapshotTimer(self):
        self.snapshotTimerError.wait(1800)
        getorderbook = threading.Thread(target= self.getOrderBookSnapshot, daemon=True)
        getorderbook.start()
        return

    def getOrderBookSnapshot(self):
        # time.sleep(1)
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
                # set/update orderbook to snapshot 
                self.trades = {'bought':{}, 'sold':{}} # need to reset the orderbook in case this is an update mid operation so were not leaving any old data behind in case it doesnt get updated
                for orders in rawOrderBook['bids']:
                    self.orderBook['bids'].update({float(orders[0]): float(orders[1])})
                for orders in rawOrderBook['asks']:
                    self.orderBook['asks'].update({float(orders[0]): float(orders[1])})
                self.last_uID = rawOrderBook['lastUpdateId']
                # we are getting 5000 long snapshot however websocket only updates top 1000 so we need to shorten it for storing local copy/processing
                # therefore we log the full 5000 long orderbook then shorten it down
                self.mongolog('orderbooksnapshot')
                pricelist = {'asks':  sorted(list(self.orderBook['asks'].keys())), 'bids': sorted(list(self.orderBook['bids'].keys()), reverse=True)}
                pricelist['asks'] = pricelist['asks'][1000:]
                pricelist['bids'] = pricelist['bids'][1000:]
                for side in ['asks', 'bids']:
                    for price in pricelist[side]:
                        del self.orderBook[side][price]
                #----update from buffer section-------- 
                # This section more than likely is only necessary for 100ms update stream - 1000ms = 1 sec and we can request and receive a snapshot within 1 sec comfortably
                # 100ms on the otherhand may cause some issues because we may have recieved an update to the snapshot that is newer than what is in the snapshot and if we dont't apply 
                # that update before the next incoming update our orderbook will be off we essentially skipped/missed an update
                while self.ordBookBuff[0]['u'] <= self.last_uID: #ordBookBuff[0]['u'] != None and
                    # print("current update in buffer has old data that is already incoroprated into orderbook snapshot")
                    # print(f"deleting buffer update for {self.coin} - eventtime: {self.ordBookBuff[0]['E']}  -  First update ID : {self.ordBookBuff[0]['U']}   -   last update ID : {self.ordBookBuff[0]['u']} - # of events in update : {float(self.ordBookBuff[0]['U'])-float(self.ordBookBuff[0]['u'])}")
                    del self.ordBookBuff[0]
                    if len(self.ordBookBuff) == 0:
                        break
                print(f"new length after removing unneccessary updates : {len(self.ordBookBuff)} \n")
                if len(self.ordBookBuff) >= 1 :
                    print(f"first UID left in buffer {self.ordBookBuff[0]['U']} -  last uID in buffer : {self.ordBookBuff[-1]['u']} - # of updates {float(self.ordBookBuff[0]['U'])-float(self.ordBookBuff[0]['u'])}")
                    print(f" buffer size : {len(self.ordBookBuff)}")
                    for ind, eachUpdate in enumerate(self.ordBookBuff):
                        print(f" performing update for # {ind} out of {len(self.ordBookBuff)} for {self.symbol}")
                        self.updateOrderBook(eachUpdate)
                    self.ordBookBuff = []
                # else:
                #     print("nothing left in buffer - taking next available/incoming message frame \n")
                self.SnapShotRecieved = True
                #------------------------------
            
        else:
            print(f'Error retieving order book. Status code : {str(orderBookEncoded.status_code)}\nReason : {orderBookEncoded.reason}') #RESTfull request failed 
        return

    def addSelfToStream(self, ws, msgtype):
        # msgtype "sub" for subscribing and "unsub" or anything else for unsubscribing
        message = {"method": "SUBSCRIBE" if msgtype == "sub" else "UNSUBSCRIBE", "params": self.streams, "id": 1 }
        ws.send(json.dumps(message))
        if msgtype == "sub":
            getsnapshot = threading.Thread(target=self.getOrderBookSnapshot, daemon=True)
            getsnapshot.start()

def on_message(ws, message, SecuritiesRef):
    messaged = json.loads(message)
    #print(messaged)
    CoinObj = SecuritiesRef[messaged['stream'].partition('usdt')[0]]
    if "stream" in messaged:
        if fnmatch.fnmatch(messaged['stream'], "*@depth@1000ms") :
            # although it should be possbile to recieve an update within the time period between orderbook updates from websocket stream best practice is to log any messages as well
            if CoinObj.SnapShotRecieved == False:
                CoinObj.ordBookBuff.append(messaged['data'])
                print('appending message to buffer')
            else:
                print(f"orderbook update for {getattr(CoinObj, 'coin')} with eventtime : {messaged['data']['E']} - last recorded ID {CoinObj.last_uID} - message: first UID: {messaged['data']['U']}  last uID : {messaged['data']['u']} ")
                # we will keep an up to date orderbook locally 
                CoinObj.updateOrderBook(messaged['data'])
                # it is more "efficient" or rather we can save a lot of disk space by only logging changes to the orderbook so we take the message data and send it to be conditioned and logged
                CoinObj.messageupdates(messaged['data'])
        elif fnmatch.fnmatch(messaged['stream'], "*@aggTrade"):
            CoinObj.addTrade(messaged['data']) #, messaged['E']
        else:      #the catch all statement
            print('Incoming message being handled incorrectly.')
    elif "result" in messaged:
        if messaged['result'] == None:
            print("Successfully (un)subscribed")
    else:
        print("Unexpected message handling")

def on_error(ws, error):
    print(error)

def on_close(ws, close_status_code, close_msg):
    print("closed websocket connection")

def on_open(ws, url):
    print(f'opened connection to : {url} \n')

def main():
    # mongoDB connection object which we will use to log to database - _NOTE: MongoClient creates 2 threads
    client = MongoClient('192.168.1.254:27017', username='mainworker', password='qwdgBm4vP5P5AkhS', authSource='orderbook&trades', authMechanism='SCRAM-SHA-256')
    DBConn = client['orderbook&trades']
    # instantiating objects for various securities - list of objects that will be used to create the base uri endpoint and subscribe to their relative streams
    # Securities = {'btc':coin("BTC", 1), 'ada':coin("ADA", 0.0001), 'eth':coin("ETH", 0.1), 'dot':coin("DOT", 0.001)} # 10,000-100,000 : 1 \ 1,000-10,000 : 0.1 \ 100-1000 : 0.01 \ 10-100 : 0.001 \ 1-10 : 0.0001
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
    # websocket for handling updates -  _NOTE: websocket creates 1 threads
    ws = WebSocketApp(uriEndpoint, on_open=partial(on_open, url=uriEndpoint), on_message=partial(on_message, SecuritiesRef=Securities), on_error=on_error, on_close=on_close) #, on_ping=on_ping
    listeningForMessages = threading.Thread(target = ws.run_forever, daemon=True) #threading.Thread(target = ws.run_forever, daemon=True, kwargs={'ping_interval':300, 'ping_timeout':10, 'ping_payload':'pong'})
    listeningForMessages.start()
    #-------------------------------------------------------------------------------------------------------------------------------
    # _NOTE: BaseManager creates 1 threads
    # # custom class - throws client exception : multiprocessing.managers.RemoteError: KeyError: 'RemoteOperations'
    # manager = RemoteManager(address=('', 12345), authkey=b'secret')
    # # no custom class
    manager = BaseManager(address=('', 12345), authkey=b'secret')
    #-------------
    server = manager.get_server()
    manager.register('RemoteOperations', partial(RemoteOperations, ws= ws,  securitiesRef=Securities, messageServer=server, DBConn= DBConn))
    #-------------------------------------------------------------------------------------------------------------------------------
    #need to allow buffer to fill up alittle in order to get snapshot and then apply correct updates/mesages to orderbook as per API documentation
    for coinObjects in Securities.values():
        snapshotthread = threading.Thread(target= coinObjects.getOrderBookSnapshot, daemon=True)
        snapshotthread.start()
    # we basically wait here until we press esc - _NOTE: Keyboard creates 2 threads
    try:
        server.serve_forever()
    except BaseException as e:
        print(f"closed out server with exception : {e}")
    ws.close()
    listeningForMessages.join()
    print(f"active threads J : {threading.active_count()}")
    exit(0)

if __name__ == "__main__":
    main()

