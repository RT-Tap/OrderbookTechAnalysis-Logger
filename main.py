from requests.api import get
#from websocket import WebSocketApp
import websocket
from functools import partial
import json
import threading
import time
import fnmatch # needed for string wildcard matching
from pymongo import MongoClient
from multiprocessing.managers import BaseManager
from datetime import datetime # dtime = datetime.now(); unixtime = datetime.utcnow() -  datetime.fromtimestamp(messaged['E']/100).strftime('%Y-%m-%d %H:%M:%S')}
import os, sys

# handy function that allows us to go from utc to local and the original utc is timezone unaware
def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz=None)
    # convert from timestamp to date time: datetime.utcfromtimestamp(float(messaged['E'])/1000).strftime('%Y-%m-%d %H:%M:%S') 

def logMessage(message, **kwargs):
    # syslog levels ... 3 - error conditions exist, 4 - warning conditiosn exit, 5 - notice. normal but significant conditions exist, 6 - info informational messages, 7 - debug
    # syslog log templae: date - time - log level - Event - message
    if RUN_AS_SERVICE == True:
        loglvl = {'Error':journal.Priority.ERROR, 'Warning':journal.Priority.WARNING, 'Notice':journal.Priority.NOTICE, 'Info':journal.Priority.INFO, 'Debug':journal.Priority.DEBUG}
        journal.send(message=message, priority=loglvl[kwargs['priority']] )
    else:
        loglvl = dict(zip(['Error', 'Warning', 'Notice','Info', 'Debug'], range(3,8)))
        if loglvl[kwargs['priority']] <= (loglvl[LOGLEVEL] if isinstance(LOGLEVEL, str) else LOGLEVEL) :
            print(f"{datetime.now()} - {'loglvl: '+ kwargs['priority']} : {message}")

class RemoteOperations:
    def __init__(self, ws, securitiesRef, messageServer, DBConn, startTime):
        # here self.websocketConnection isn't actually the connection it is an object that contains the connection refrence along with other objects/refrences
        # python passes variables as refrences and so if we define the websocket as a specific refrence it wont update when we update it later on but 
        # by refrencing a wrapper object the refrence to the wrapper object never changes only the internal refence to the current websocket connection inside it changes 
        # therefore when we want to use the connection we still need to call it indirectly: ref: https://stackoverflow.com/questions/986006/how-do-i-pass-a-variable-by-reference
        self.websocketConnection = ws
        self.securities = securitiesRef
        # were using BaseManager from multiprocessing library to incorporate inter process communication 
        # although it/we doesn't/aren't actually start a new process but instead using a thread to accomodate this
        # functionality we need a way to terminate this thread - we do thhis by setting a stop event that in turn teminates itself
        self.messageServer = messageServer
        self.DBConn = DBConn
        self.startTime = startTime


    def addSecurity(self, newcoin, *pair):
        logMessage(f"Request to log  {newcoin}.", priority='Info')
        if len(pair) == 0:
            self.securities[newcoin.lower()] = coin(newcoin.upper(), self.DBConn)
            self.securities[newcoin.lower()].addSelfToStream(self.websocketConnection['websocket'])
        else:
            self.securities[(newcoin+pair).lower()] = coin((newcoin+pair).upper(), self.DBConn)
            self.securities[(newcoin+pair).lower()].symbol = (newcoin+pair).lower()
            self.securities[newcoin.lower()].addSelfToStream(self.websocketConnection['websocket'])
        return f"Successfully added {newcoin} to securities being logged."
    
    def removeSecurity(self, symbol):
        logMessage(f"Request to remove {symbol} from logging.", priority='Info')
        self.securities[symbol].removeSelfCheck = True
        self.securities[symbol].snapshotTimerError.set()
        self.securities[symbol].removeSelfFromStream(self.websocketConnection['websocket'])
        del self.securities[symbol]
        return f"Successfully removed {symbol} from being logged."
    
    def requestOrderbookSnapShot(self, symbol):
        if symbol == 'ALL':
            logMessage(f"Manual request for new/updated orderbook snapshot for ALL securities currently being logged", priority='Info')
            for security in self.securities:
                logMessage(f"Requesting new/updated orderbook snapshot for {security}", priority='Info')
                self.securities[security].snapshotTimerError.set()
        else:
            logMessage(f"Manual request for new/updated orderbook snapshot for {symbol}", priority='Info')
            self.securities[symbol.lower()].snapshotTimerError.set()
        return f'Seccessfully requested orderbook snapshot for {"ALL" if symbol == "ALL" else symbol}'
    
    def terminate(self):
        logMessage("Manual termination command received", priority='Info')
        self.messageServer.stop_event.set()
        return 'Terminating program'

    def listSecurities(self):
        return self.securities.keys()

    def connectionTest(self, gimme):
        logMessage(f"Remote connection test from:  {gimme} ", priority="Info")
        return "Success"

    def getThreadCount(self):
        logMessage(f'THREAD COUNT: {threading.active_count()} ', priority="Info")
        logMessage(f'ENUMERATED THREADS:{threading.enumerate()} ', priority="Info")
        return f'Actively running threads : { threading.active_count()}'
    
    def resetWebSocket(self):
        logMessage(f'received manual request to reset websocket connection', priority='Info')
        WSResetEvent.set()
        return "received request for websocket reset"
    
    def retrieveCurrentOrderbook(self, security):
        return json.dumps(self.securities[security].orderBook)

    def elapsedRunningTime(self):
        elapsedTime = datetime.now() - self.startTime
        elapsedSeconds = elapsedTime.total_seconds()
        minSec = divmod(elapsedSeconds, 60) # [ min, sec ]
        hourMin = divmod(minSec[0], 60) #[hour, min]
        dayHour = divmod(hourMin[0], 24) #[day, hour]
        return f'Running Since: {self.startTime} , Elapsed Time: {dayHour[0]} days {dayHour[1]} hours {hourMin[1]} minutes {minSec[1]} seconds'

class coin:
    def __init__(self, name, DBConn):
        self.coin = name.lower()
        self.symbol = name.lower() + "usdt"
        self.streams = [self.symbol + "@aggTrade", self.symbol + "@depth@"+orderbookUpdateFrequency+"ms"]
        self.SnapShotRecieved = False
        self.last_uID = 0
        self.eventTime = 0
        # this should be changed into a function that determines the grouping so that there are 5 significant figures for grouping eg, 40000 = 1 , 25 = 0.001 , 3 = 0.0001 , 0.99 = 0.00001, anything more isnt usefull
        # self.tradeSigFig = groupAmt   
        self.ordBookBuff = []
        self.orderBook = {'bids':{}, 'asks':{}}
        self.trades = {'bought':{}, 'sold':{}}
        self.DBConn = DBConn[self.symbol]
        self.significantTradeEvents = []
        # we want to grab an orderbook snapshot every x seconds (30 min) therefore we have a thread that just waits for the timer to run out or  unless a message error occurs 
        # e.g. an incoming update has an unexpected updateID indicating we missed an update message in which case we request earlier
        self.snapshotTimerError = threading.Event()
        self.currenSnapShotTimerThread = None
        # when deleting a security we want to end the orderbookErrorTimer thread but don't want to retrieve and orderbook so this will allow us to check if we are removing or not
        self.removeSelfCheck = False


    def updateOrderBook(self, message):
        if message['U'] > self.last_uID + 1:
            errormsg = f"ERROR {self.symbol} updateID for {message['E']} was not what was expected - last_uID logged: {self.last_uID} | uID (first event) of this message : {message['U']} - difference : {float(message['U']) - self.last_uID}"
            logMessage(errormsg, priority='Warning')
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
                    #we need a try clause here as binance documentation states "Receiving an event that removes a price level that is not in your local order book can happen and is normal." which can cause issues
                    try:
                        del self.orderBook[bookSide][float(update[0])]
                    except:
                        pass
                else:
                    self.orderBook[bookSide].update({float(update[0]): float(update[1])})
            # binance leaves removing the highest ask and lowest bid when the orderbook grows bigger than 1000 on either side in order to keep orders from one side flowing into the other
            counter = 0
            while len(self.orderBook[bookSide]) > 1000:
                counter += 1
                del self.orderBook[bookSide][(min(self.orderBook['bids'], key=self.orderBook['bids'].get)) if side == 'b' else (max(self.orderBook['asks'], key=self.orderBook['asks'].get))]
        if max(self.orderBook['bids'], key=self.orderBook['bids'].get) > min(self.orderBook['asks'], key=self.orderBook['asks'].get) :
            self.logMessage(f"ERROR! - Orderbook ask/bid Overlap! \nmax bid : { (max(self.orderBook['bids'], key=self.orderBook['bids'].get))} - min ask : {min(self.orderBook['asks'], key=self.orderBook['asks'].get)}", priority='Warning')
            self.snapshotTimerError.set()

    def defineTradeSignificantFigure(self,price):
        tradeSigFig = None
        if price / 10000 > 1 :
            tradeSigFig = 1
        elif price / 1000 > 1 :
            tradeSigFig = 0.1
        elif price / 100 > 1:
            tradeSigFig = 0.001
        elif price / 10 > 1:
            tradeSigFig = 0.0001
        elif price / 1 > 1:
            tradeSigFig = 0.00001
        elif price / 0.1 > 1:
            tradeSigFig = 0.000001
        elif price / 0.01 > 1:
            tradeSigFig = 0.0000001
        else:
            tradeSigFig = 0.00000001
        return tradeSigFig

    def addTrade(self, tradeData): # 
        tradeSigFig = self.defineTradeSignificantFigure(tradeData['p'])
        # round all trades up to figures that actually matter in order to group them
        price = float(tradeData['p']) - (float(tradeData['p']) % tradeSigFig) + tradeSigFig
        # if buyer is market maker then this trade was a sell
        if tradeData['m'] == True:
            self.trades['sold'].update({price:((self.trades["sold"][price] if price in  self.trades["sold"] else 0) + float(tradeData["q"]))})
        else:
            self.trades['bought'].update({price:((self.trades["bought"][price] if price in self.trades["bought"] else 0) + float(tradeData["q"]))})
        if float(tradeData['p']) * float(tradeData['q']) >= tradeSigFig:
            self.significantTradeEvents.update([str(tradeData['p']), float(tradeData['q'])])
        
    def messageupdates(self, message):
        # because it saves space to only log updates rather than the entire orderbook we will turn the updates into a dictionary (because it is easier for us to handle than a list) 
        # that can then be applied to the orderbook at the previous timestamps state(condition)
        updatedict = {"asks":{}, "bids":{}}
        for msgkey, logkey in {"a":"asks","b":"bids"}.items():
            for updates in message[msgkey]:
                updatedict[logkey].update({updates[0]: float(updates[1])})
        self.mongolog(updatedict)

    def mongolog(self, *update):
        return
        # ID of mongoDB entry relies on whether an update was provided - if not update is provided we log the orderbook as we just received a snapshot otherwise we log the update
        ident =  str(datetime.timestamp(datetime.utcnow())*1000)+("snapshot" if not update else "update")
        # We dont want any data changing while were logging it could cause us to loose track of updates
        with threading.Lock():
            # if no update was passed in then we are logging the orderbook as we just got a new snapshot
            if not update:
                # mongoDB requires all keys to be strings therefore we ned to condition orderbook in order to enter it
                conditionedOrderBook = {"asks":{}, "bids":{}}
                for sideKey, sideDict in self.orderBook.items():
                    for price, quantity in sideDict.items():
                        conditionedOrderBook[sideKey][str(price)] = quantity
            self.trades['bought'] = {str(key): value for key, value in self.trades['bought'].items()}
            self.trades['sold'] = {str(key): value for key, value in self.trades['sold'].items()}
            # if updates exist (has truthiness can just test with "if update") we log those if not then we log the conditioned orderbook
            insertData = { "_id" : ident, "type": "snapshot" if not update else "update", "DateTime": datetime.utcnow(), 'timstamp':datetime.timestamp(datetime.utcnow()), "symbol": self.symbol, "trades" : self.trades,  "orberbook" : conditionedOrderBook if not update else update[0]} # if no update was passed in then we are logging the orderbook as we just got a new snapshot
            # because were consolidating orders at realtively close to the same price points we also want to log any significant trade events that might be of interest when analyzing the data
            if len(self.significantTradeEvents) != 0:
                    insertData.update({'significantTradeEvents': self.significantTradeEvents})
            try:
                result=self.DBConn.insert_one(insertData)
                logMessage(f"Database insert success : {result}", priority='Debug')
            except Exception as e:
                logMessage(f"MongoDB insert error occured : {e}", priority='Error')
                logMessage(f"Tried to insert: {insertData}", priority='Debug')
            # clear trade tracking for next time interval
            self.trades = {'bought':{}, 'sold':{}}
            self.significantTradeEvents = [] 
    
    def snapshotTimer(self):
        logMessage(f"Snapshottimer started for: {self.symbol}", priority='Debug')
        # we want to refresh our orderbook every so often so a thread is created as a timer to wait 1800 seconds UNLESS unexpected behaviour occurs and snapshotTimerError flag is set from elsewhere 
        # we dont need to explicityl join threads - refrence: https://stackoverflow.com/questions/43983882/python-when-does-a-thread-terminate-oviously-not-immediately-at-return
        self.snapshotTimerError.wait(1800) # 1800 sec = 30 min
        if self.removeSelfCheck == False and exitRoutine == False:      # make sure we didnt want to remove this symbol from the websocket connection
            getorderbook = threading.Thread(target= self.getOrderBookSnapshot, name=(self.symbol+'-getsnapshotThread'), daemon=True) # create a thread that grabs a fresh orderbook snapshot
            getorderbook.start()

    def getOrderBookSnapshot(self):
        time.sleep(1) # allow some updates to buffer in
        API_endpoint = 'https://api.binance.com'  
        getObjectEndpoint = 'api/v3/depth'
        parameterNameSymbol = 'symbol'
        parameterValueSymbol = self.symbol.upper()
        parameterNameLimit = 'limit'
        parameterValueLimit = '5000'
        orderBookURL = f'{API_endpoint}/{getObjectEndpoint}?{parameterNameSymbol}={parameterValueSymbol}&{parameterNameLimit}={parameterValueLimit}'  
        logMessage(f'Retrieving orderbook for {self.symbol} from {orderBookURL}', priority='Info')
        orderBookEncoded = get(orderBookURL)
        if orderBookEncoded.ok: 
            rawOrderBook = orderBookEncoded.json() 
            logMessage(f'Succesfully retreived order book for  {self.symbol}', priority="Info")
            # we dont really want any incoming orderbook updates to interrupt (re)setting the orderbook so we lock the thread for this portion
            with threading.Lock():
                # need to reset the orderbook in case this is an update mid operation so were not leaving any old data behind in case it doesnt get updated
                self.trades = {'bought':{}, 'sold':{}} 
                for orders in rawOrderBook['bids']:
                    self.orderBook['bids'].update({float(orders[0]): float(orders[1])})
                for orders in rawOrderBook['asks']:
                    self.orderBook['asks'].update({float(orders[0]): float(orders[1])})
                self.last_uID = rawOrderBook['lastUpdateId']
                # we are getting 5000 long snapshot however websocket only updates top 1000 so we need to shorten it for storing local copy/processing
                # therefore we log the full 5000 long orderbook then shorten it down
                self.mongolog()
                pricelist = {'asks':  sorted(list(self.orderBook['asks'].keys())), 'bids': sorted(list(self.orderBook['bids'].keys()), reverse=True)}
                pricelist['asks'] = pricelist['asks'][1000:]
                pricelist['bids'] = pricelist['bids'][1000:]
                for side in ['asks', 'bids']:
                    for price in pricelist[side]:
                        del self.orderBook[side][price]
                # This section only necessary for 100ms update stream as we can request and receive a snapshot within 1 sec comfortably on the otherhand 100ms may cause some issues because we may have recieved
                #  an update that is newer than what is in the snapshot and if we dont't apply that update before the next incoming update our orderbook will be off
                logMessage(f'Applying buffered messages to {self.symbol} orderbook', priority='Debug')
                if len(self.ordBookBuff) >= 1: 
                    while self.ordBookBuff[0]['u'] <= self.last_uID:
                        logMessage(f"deleting buffer update already incoroprated into orderbook snapshot for {self.coin} - eventtime: {self.ordBookBuff[0]['E']}  -  First update ID : {self.ordBookBuff[0]['U']}   -   last update ID : {self.ordBookBuff[0]['u']} - # of events in update : {float(self.ordBookBuff[0]['U'])-float(self.ordBookBuff[0]['u'])}", priority='Debug')
                        del self.ordBookBuff[0]
                        if len(self.ordBookBuff) == 0:
                            break
                    logMessage(f"After removing unneccessary updates for {self.symbol}, new buffer length : {len(self.ordBookBuff)}", priority="Debug")
                    if len(self.ordBookBuff) >= 1 :
                        logMessage(f"{self.symbol} buffer : first UID left in buffer {self.ordBookBuff[0]['U']} -  last uID in buffer : {self.ordBookBuff[-1]['u']} - buffer size : {len(self.ordBookBuff)}", priority="Debug")
                        for ind, eachUpdate in enumerate(self.ordBookBuff):
                            logMessage(f"Performing update #{ind} out of {len(self.ordBookBuff)} on {self.symbol} buffer ", priority='Debug')
                            self.updateOrderBook(eachUpdate)
                        self.ordBookBuff = []
                    else:
                        logMessage("Nothing left in buffer - taking next available/incoming message frame.", priority='Debug')
                else:
                    logMessage("No update messages arrived while rertreiving orderbook snapshot. Taking next available/incoming message frame.", priority='Debug')
                self.SnapShotRecieved = True
                #------------------------------
            self.snapshotTimerError.clear()
            snapshotRequestTimer = threading.Thread(target=self.snapshotTimer, name=(self.symbol+'-orderbookSnapshotTimer'), daemon=True)
            snapshotRequestTimer.start()
            self.currenSnapShotTimerThread = snapshotRequestTimer
        else:
            logMessage(f'Error retieving order book. Status code : {str(orderBookEncoded.status_code)} -- Reason : {orderBookEncoded.reason}', priority='Error') 


    def addSelfToStream(self, ws):
        logMessage(f'Connecting websockets data stream for {self.symbol}', priority='Info')
        # msgtype "sub" for subscribing and "unsub" or anything else for unsubscribing
        message = {"method": "SUBSCRIBE", "params": self.streams, "id": 1 }
        ws.send(json.dumps(message))
        getsnapshot = threading.Thread(target=self.getOrderBookSnapshot, name=(self.symbol+'-getOrderbookSnapshotThread'), daemon=True)
        getsnapshot.start()
    
    def removeSelfFromStream(self, ws):
        logMessage(f'Disconnecting websockets data stream for {self.symbol}', priority='Info')
        message = {"method": "UNSUBSCRIBE", "params": self.streams, "id": 1 }
        ws.send(json.dumps(message))

def on_message(ws, message, SecuritiesRef):
    messaged = json.loads(message)
    CoinObj = SecuritiesRef[messaged['stream'].partition('usdt')[0]]
    if "stream" in messaged:
        if fnmatch.fnmatch(messaged['stream'], "*@depth@"+orderbookUpdateFrequency+"ms") :
            if CoinObj.SnapShotRecieved == False:
                # because we have to reset connection every 24 hours there will be a point where 2 websockets are open calling the same function, in that case we have to drop every duplicate
                # but because these messages come in at the same time we need to make sure we handle them one at a time sequentially so no race conditions occur
                with threading.Lock():
                    if len(CoinObj.ordBookBuff) == 0:
                        CoinObj.ordBookBuff.append(messaged['data'])
                        logMessage(f'Adding first element to update buffer for {CoinObj.symbol}', priority='Debug')
                    else:
                        if CoinObj.ordBookBuff[-1]['E'] != messaged['data']['E']:
                            CoinObj.ordBookBuff.append(messaged['data'])
                            logMessage(f'Adding to {CoinObj.symbol} update buffer', priority='Debug')
                        else:
                            logMessage(f'Dropping duplicate message for {CoinObj.symbol}', priority='Debug')
                logMessage(f'Appending message to buffer for {getattr(CoinObj, "coin")}', priority='Debug')
            else:
                logMessage(f"Received orderbook update for {getattr(CoinObj, 'coin')} - last recorded ID: {CoinObj.last_uID} -- Update = eventtime : {messaged['data']['E']}, first UID: {messaged['data']['U']},  last uID : {messaged['data']['u']} ", priority='Debug')
                # we will keep an up to date orderbook locally and log just the updates save a lot of disk space by only logging changes - therefore we keep this as 2 separate steps as well the update and the conditioning of data and log
                CoinObj.updateOrderBook(messaged['data'])
                CoinObj.messageupdates(messaged['data'])
        elif fnmatch.fnmatch(messaged['stream'], "*@aggTrade"):
            CoinObj.addTrade(messaged['data']) 
    else:
        logMessage(f"WebSocket (un)subscribed from stream, message : {messaged}", priority='Info' )
    # else:      #the catch all statement
    #     logMessage(f'Incoming message being handled incorrectly. Message: {messaged}', priority='Error')

def on_error(ws, error):
    # for some reason theres an error on every signle message so maybe check what type and just ignore the common ones
    pass
    #logMessage(f'Websocket connection error: {error}', priority='Error')

def on_close(ws, close_status_code, close_msg):
    if close_status_code or close_msg:
        logMessage(f"Server closed our websocket connection- close status code: {str(close_status_code)}, close message: {str(close_msg)}", priority='Notice')
    else:
        logMessage("Closed websocket connection", priority='Info')

def on_open(ws, url, Securities):
    logMessage(f'New websocket connection to : {url}', priority='Info')
    for coinObjects in Securities.values():
        snapshotthread = threading.Thread(target= coinObjects.getOrderBookSnapshot, name=(coinObjects.symbol+'-getOrderbookSnapshotThread') ,daemon=True)
        snapshotthread.start()

def on_ping(ws, message):
    logMessage(f'WebSocket ping recevied and automatic pong sent', priority='Info')

def createWebSocketURL(Securities):
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
    return uriEndpoint


def webSocketTimer(argDict):
    # unblocking wait - either timer runs out or we set WSResetEvent flag 
    WSResetEvent.wait(72000) # 72000 secs = 20 hours
    WSResetEvent.clear()
    logMessage(f"Resetting WebSocket connection", priority='Info')
    # set all messages to buffer while we close this connection and open a new one
    for eachCoin in argDict['securities']:
        argDict['securities'][eachCoin].removeSelfCheck = True # When the old snapshot loop is set to continue in next line it will terminate itself
        argDict['securities'][eachCoin].snapshotTimerError.set() # stop the old snapshot loop as a new one will be created in new websocket on_open
        argDict['securities'][eachCoin].SnapShotRecieved = False
    argDict['websocket'].close()
    argDict['oldWSthread'].join()
    # now that the old snapshot threads have exited we need to reset removeSelfCheck to false because we dont actually want to remove it
    for eachCoin in argDict['securities']:
        argDict['securities'][eachCoin].removeSelfCheck = False
    # no point inopeniong new connection when we want to exit
    if argDict['exitFlag'] != True:
        # open new connection before closing old one - opening new connection should also take care of firing off snapshot timer thread
        uriEndpoint = createWebSocketURL(argDict['securities'])
        newWSConnection = websocket.WebSocketApp(uriEndpoint,  on_message=partial(on_message, SecuritiesRef=argDict['securities']), on_error=on_error, on_close=on_close, on_open=partial(on_open, url=uriEndpoint, Securities=argDict['securities']), on_ping=on_ping) # 
        WebSocketThread = threading.Thread(target = newWSConnection.run_forever, name=('WebSocketThread'), daemon=True) 
        WebSocketThread.start()
        # update all of our old websocket connections to use the new connection object
        argDict['websocket'] = newWSConnection
        argDict['oldWSthread'] = WebSocketThread # next time this runs it will be the "old" one we want to join
        # create new thread to replace this one
        #try: # placed in try because the names of the old and new timer might bump in which case just give it another name
        newWSTimerThread = threading.Thread(target=webSocketTimer, name=('WebSocketTimer'), args=({"securities": argDict['securities'], 'websocket': newWSConnection, 'oldWSthread': WebSocketThread, 'exitFlag': argDict['exitFlag']},), daemon=True)
        # except:
        #     newWSTimerThread = threading.Thread(target=webSocketTimer, name=('NewWebSocketTimer'), args=({"securities": argDict['securities'], 'websocket': newWSConnection, 'oldWSthread': WebSocketThread, 'exitFlag': argDict['exitFlag']},), daemon=True)
        global CurrentWebSocketTimerThread
        CurrentWebSocketTimerThread = newWSTimerThread
        newWSTimerThread.start()


def main():
    # mongoDB connection object which we will use to log to database - DEBUG_NOTE: MongoClient creates 2 threads
    logMessage(f'Attempting to connect to mongoDB server at {mongoDBserver}', priority='Info')
    try:
        client = MongoClient(mongoDBserver, username='mainworker', password='qwdgBm4vP5P5AkhS', authSource=mongoDBdatabase, authMechanism='SCRAM-SHA-256')
        DBConn = client[mongoDBdatabase]
        logMessage('Successfully connected to mongoDB server', priority='Info')
    except Exception as e:
        logMessage(f'Error connecting to mongoDB server- Error: {e.__class__} \nExiting ...', priority='Info')
        exit(2)
    # instantiating objects for various securities we want to track 
    Securities = {'btc':coin("BTC", DBConn)}#, 'ada':coin("ADA", 0.0001, DBConn), 'eth':coin("ETH", 0.1, DBConn), 'dot':coin("DOT", 0.001, DBConn)} # 10,000-100,000 : 1 \ 1,000-10,000 : 0.1 \ 100-1000 : 0.01 \ 10-100 : 0.001 \ 1-10 : 0.0001
    uriEndpoint = createWebSocketURL(Securities)
    logMessage(f"Attempting to connect to WebSocket endpoint : {uriEndpoint}", priority='Info')
    # websocket for handling updates -  DEBUG_NOTE: websocket creates 1 threads
    ws = websocket.WebSocketApp(uriEndpoint, on_open=partial(on_open, url=uriEndpoint, Securities=Securities), on_message=partial(on_message, SecuritiesRef=Securities), on_error=on_error, on_close=on_close)
    listeningForMessages = threading.Thread(target = ws.run_forever, name='WebSocketThread', daemon=True) #threading.Thread(target = ws.run_forever, daemon=True, kwargs={'ping_interval':300, 'ping_timeout':10, 'ping_payload':'pong'})
    listeningForMessages.start()
    # because websocket connections to binance only last 24 hours we will need to manually reconect after around 22 hours
    # main thread is being blocked by remote server so we need to create a thread that waits ~21-23 hours and then closes the connection and starts a new one
    exitRoutine = False
    websocektTimerArgPackage = {"securities": Securities, 'websocket': ws, 'oldWSthread': listeningForMessages, 'exitFlag': exitRoutine}
    websocketResetTimer = threading.Thread(target= webSocketTimer, name=('WebSocketResetTimer'), args=(websocektTimerArgPackage,), daemon=True) #, name='WebSocketTimer'
    global CurrentWebSocketTimerThread
    CurrentWebSocketTimerThread = websocketResetTimer
    websocketResetTimer.start()
    #-------------------------------------------------------------------------------------------------------------------------------
    # _NOTE: BaseManager creates 1 threads 
    manager = BaseManager(address=('', managerPort), authkey=managerAuthkey.encode())  # authkey=b'secret'
    server = manager.get_server()
    manager.register('RemoteOperations', partial(RemoteOperations, ws= websocektTimerArgPackage,  securitiesRef=Securities, messageServer=server, DBConn= DBConn, startTime= datetime.now())) # websocket here needs to be a refrence as it will update on new connection
    #-------------------------------------------------------------------------------------------------------------------------------
    # need to allow buffer to fill up alittle in order to get snapshot and then apply correct updates/mesages to orderbook as per API documentation
    try:
        logMessage('Entering steady state/main loop of application', priority='Info')
        server.serve_forever()
    except BaseException as e:
        if isinstance(e, SystemExit):
            closemsg = f"Correctly closed BaseManager Remote server as expected"
        else:
            closemsg = f"Unexpected error during main thread blocking with BaseManager Remote Server or with closing down BaseManager - Error: {e}"
        logMessage(closemsg, priority='Info')
    except:
        logMessage('Error opening Remote Server and therefore cannot enter maing loop of application ', priority='Error')
    logMessage('Shutting down sequnce, closing websocket Connection,  joining any threads in preparation for application exit.', priority='Info')
    logMessage(f'Preshutdown thread count: {threading.active_count()}', priority='Debug')
    # regarding thread termination / joining: we dont need to .join() all threads they will exit/cleanup automatically: https://stackoverflow.com/questions/38275944/do-threads-in-python-need-to-be-joined-to-avoid-leakage
    WSResetEvent.set()
    print(f"Active threads : {threading.active_count()}")
    CurrentWebSocketTimerThread.join()
    print(f"Active threads : {threading.active_count()}")
    for security in Securities:
        Securities[security].snapshotTimerError.set()
        if Securities[security].currenSnapShotTimerThread is not None:
            print('Waiting to join snapshottimer')
            Securities[security].currenSnapShotTimerThread.join()
    logMessage(f"Active threads : {threading.active_count()}", priority='Debug')
    logMessage(f"ENUMERATED THREADS:{threading.enumerate()} ", priority='Debug')
    logMessage('Exitting application ...', priority='Info')
    exit(0)

if __name__ == "__main__":
    #websocket.enableTrace(True)
    # This script can be run as an application (usually inside a container) or as a systemd service (requires .service file)
    if os.getenv('AS_SERVICE', False) == True:
        from cysystemd import journal
        RUN_AS_SERVICE = True
    else: 
        RUN_AS_SERVICE = False
    LOGLEVEL = os.getenv('LOGLEVEL','Info')    # highest level of information that we should log
    if os.getenv('DEBUG', False) == True:
        LOGLEVEL = 'Debug'
    mongoDBserver = os.getenv('MONGODB_ENDPOINT','192.168.1.254:27017')
    mongoDBdatabase = os.getenv("MONGODB_DATABASE", 'TEST2')
    orderbookUpdateFrequency = str(os.getenv('ORDERBOOK_UPDATEFREQUENCY', '1000'))
    managerPort = int(os.getenv('MANAGER_PORT', 6634))
    managerAuthkey = os.getenv('MANAGER_AUTHKEY', 'secret')
    WSResetEvent= threading.Event()     # Event flag that will allow us to cut timer short and reset the websocekt
    CurrentWebSocketTimerThread = None  # allows us to keep track of websocket timer; binance allows connection for 24 hours then kicks off so we must  establish a new connection before then
    exitRoutine = False # allows us to exit some loops gracefully 
    # start the main thread/process
    main()
## TODO:
## UPDATE WEBSOCKET REFRENCE IN BASEMANAGER - Gets stale when new websocket is active
## 