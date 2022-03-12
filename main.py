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
from datetime import datetime # dtime = datetime.now(); unixtime = datetime.utcnow() -  datetime.fromtimestamp(messaged['E']/100).strftime('%Y-%m-%d %H:%M:%S')}
from enum import Enum

LOGLEVEL = 'Error'
mongoDBserver = '192.168.1.254:27017'

# this is handy because we will be using utc basically everywhere and to get back to local we use this
def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz=None)
    # convert fro;m timestamp to dat time: datetime.utcfromtimestamp(float(messaged['E'])/1000).strftime('%Y-%m-%d %H:%M:%S') 

def logMessage(message, **priority):
    # 0 - emergency system unuable
    # 1 - alert immediate action needed
    # 2 - critical conditions exist
    # 3 - error conditions exist
    # 4 - warning conditiosn exit
    # 5 - notice. normal but significant conditions exist
    # 6 - info informational messages
    # 7 - debug
    # date - time - log level - Event - message
    loglvl = dict(zip(['Error', 'Warning', 'Notice','Info', 'Debug'], range(3,7)))
    if loglvl[priority] > (loglvl[LOGLEVEL] if isinstance(LOGLEVEL, str) else LOGLEVEL) :
        print(f"{datetime.now()} - {'loglvl: debug' if priority.get('lvl') == None else  'loglvl: '+priority['lvl']} -- {message}")
    #filename = 'db/' + self.coin + str(self.eventTime) + '-incident.log'
    # at this point we wrap up all events between last function call (orderbook update) and now (this function call / orderbook update), put them in a temporary object, clear the logging object and log the original (temporary/old) data
    #with open(filename, 'a') as file:
    #    print(f"{datetime.now()} - {'' if priority.get('lvl') == None else  ' priority: '+str(priority['lvl'])} \n{message}", file=file)

class RemoteOperations:
    def __init__(self, ws, securitiesRef, messageServer, DBConn):
        self.websocketConnection = ws
        self.securities = securitiesRef
        # were using BaseManager from multiprocessing library to incorporate inter process communication 
        # although it/we doesn't/aren't actually start a new process but instead using a thread to accomodate this
        # functionality we need a way to terminate this thread - we do thhis by setting a stop event that in turn teminates itself
        self.messageServer = messageServer
        self.DBConn = DBConn

    def addSecurity(self, newcoin, groupAmt, *pair):
        logMessage(f"RemoteClient requested {newcoin} to be logged as well.", priority='Info')
        self.securities[newcoin.lower()] = coin(newcoin.upper(), groupAmt, self.DBConn)
        self.securities[newcoin.lower()].addSelfToStream(self.websocketConnection)
        return f"Successfully added {newcoin} to websocket stream."
    
    def removeSecurity(self, symbol):
        logMessage(f"RemoteClient requested {symbol} to be removed from logging.", priority='Info')
        self.securities[symbol].removeSelfCheck = True
        self.securities[symbol].snapshotTimerError.set()
        self.securities[symbol].removeSelfFromStream(self.websocketConnection)
        del self.securities[symbol]
        return f"Successfully removed {symbol} from websocket stream."
    
    def getorderbook(self, symbol):
        logMessage(f"Remote client requested new/updated orderbook snapshot for {symbol}", priority='Info')
        self.securities[symbol.lower()].snapshotTimerError.set()
    
    def terminate(self):
        logMessage("Remote terminate command received", priority='Info')
        self.messageServer.stop_event.set()

    def listSecurities(self):
        return self.securities.keys()

    def ConnectionTest(self, gimme):
        logMessage(f"Remote connection test from:  {gimme} ", priority="Info")
        return "Success"
    
    def restartWebSocket(self):
        pass

class coin:
    def __init__(self, name, groupAmt, DBConn, sigTradeLim=10000):
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
        self.significantTradeLimit = sigTradeLim
        self.significantTradeEvents = []
        # we want to grab an orderbook snapshot every x seconds (30 min) unless a message error occurs (e.g. an incoming update has an unexpected updateID indicating we missed an update message)
        #  therefore we have a thread that just waits for the timer to run out or the event to be set and requests another snapshot
        self.snapshotTimerError = threading.Event()
        # when deleting a security we want to end the orderbookErrorTimer thread but don't want to retrieve and orderbook so this will allow us to check if we are removing or not
        self.removeSelfCheck = False

    def updateOrderBook(self, message):
        if message['U'] > self.last_uID + 1:
            errormsg = f"ERROR {self.symbol} updateID for {message['E']} was not what was expected - last_uID logged: {self.last_uID} | uID (first event) of this message : {message['U']} - difference : {float(message['U']) - self.last_uID}"
            logMessage(errormsg, priority='warning')
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
            # when the orderbook grows bigger than 1000 on either side we need to remove the highest ask and lowest bid in order to keep orders from one side flowing into the other
            counter = 0
            while len(self.orderBook[bookSide]) > 1000:
                counter += 1
                # print(f"{counter} - deleting {bookSide} side of orderbok which contained {min(self.orderBook['bids'], key=self.orderBook['bids'].get) if side == 'b' else max(self.orderBook['asks'], key=self.orderBook['asks'].get)}")
                del self.orderBook[bookSide][(min(self.orderBook['bids'], key=self.orderBook['bids'].get)) if side == 'b' else (max(self.orderBook['asks'], key=self.orderBook['asks'].get))]
        if max(self.orderBook['bids'], key=self.orderBook['bids'].get) > min(self.orderBook['asks'], key=self.orderBook['asks'].get) :
            errormesg = f"ERROR! - Orderbook ask/bid Overlap! \nmax bid : { (max(self.orderBook['bids'], key=self.orderBook['bids'].get))} - min ask : {min(self.orderBook['asks'], key=self.orderBook['asks'].get)}"
            self.logMessage(errormesg, priority='warning')
            self.snapshotTimerError.set()
        #self.mongolog()

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
            self.significantTradeEvents.update([str(tradeData['p']), float(tradeData['q'])])
        
    def messageupdates(self, message):
        # because it saves space to only log updates rather than the entire orderbook we will turn the updates into a dictionary (because it is easier for us to handle than a list) 
        # that can then be applied to the orderbook at the previous timestamps condition
        updatedict = {"asks":{}, "bids":{}}
        for msgkey, logkey in {"a":"asks","b":"bids"}.items():
            for updates in message[msgkey]:
                updatedict[logkey].update({updates[0]: float(updates[1])})
        self.mongolog(updatedict)

    def mongolog(self, *update):
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
                logMessage(f"Inserted : \n {result}", priority='Debug')
            except Exception as e:
                logMessage(f"MongoDB insert error occured : {e}", priority='Error')
                logMessage(f"Tried to insert: {insertData}", priority='Debug')
            # clear trade tracking for next time interval
            self.trades = {'bought':{}, 'sold':{}}
            self.significantTradeEvents = [] 
    
    def snapshotTimer(self, *onSelfDelete):
        logMessage(f"Snapshottimer started for: {self.symbol}", priority='debug')
        # a thread is created for this function and we wait 1800 seconds UNLESS the snapshotTimerError flag is set from elsewhere becaue of an unexpected behaviour and therefore we can start over
        # from a fresh orderbook snapshot
        self.snapshotTimerError.wait(1800)
        # make sure we didnt start an exit routine in whch case no point starting a new request thread
        if self.removeSelfCheck == False:
            # create a thread that grabs a fresh orderbook snapshot
            getorderbook = threading.Thread(target= self.getOrderBookSnapshot, daemon=True)
            getorderbook.start()

    def getOrderBookSnapshot(self):
        time.sleep(1)
        API_endpoint = 'https://api.binance.com'  # url of api server
        getObjectEndpoint = 'api/v3/depth'
        parameterNameSymbol = 'symbol'
        parameterValueSymbol = self.symbol.upper()
        parameterNameLimit = 'limit'
        parameterValueLimit = '1000'
        orderBookURL = f'{API_endpoint}/{getObjectEndpoint}?{parameterNameSymbol}={parameterValueSymbol}&{parameterNameLimit}={parameterValueLimit}'  # /{orderbookDepth}
        logMessage(f'Retrieving orderbook for {self.symbol} from {orderBookURL}', priority='Info')
        orderBookEncoded = get(orderBookURL)
        if orderBookEncoded.ok: 
            rawOrderBook = orderBookEncoded.json() 
            logMessage(f'Succesfully retreived order book for  {self.symbol}', priority="Info")
            # we dont really want any incoming orderbook updates to interrupt (re)setting the orderbook so we lock the thread for this portion
            with threading.Lock():
                # set/update orderbook to snapshot 
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
                # This section only necessary for 100ms update stream as we can request and receive a snapshot within 1 sec comfortably 100ms on the otherhand may cause some issues because we may have recieved
                #  an update that is newer than what is in the snapshot and if we dont't apply that update before the next incoming update our orderbook will be off
                logMessage(f'Applying buffered messages to {self.symbol} orderbook', priority='Debug')
                if len(self.ordBookBuff) >= 1: # <-- because we removed the wait before getting snapshot its possible no update messages came in so we have to make sure there are updates before trying to apply them (this will most likely onyl be neccesary at 100mS orderbook stream even then it may not be)
                    while self.ordBookBuff[0]['u'] <= self.last_uID: #ordBookBuff[0]['u'] != None and
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
                        logMessage("nothing left in buffer - taking next available/incoming message frame.", priority='Debug')
                else:
                    logMessage("No update messages arrived while rertreiving orderbook snapshot. Taking next available/incoming message frame.", priority='Debug')
                self.SnapShotRecieved = True
                #------------------------------
            self.snapshotTimerError.clear()
            snapshotRequestTimer = threading.Thread(target=self.snapshotTimer, daemon=True)
            snapshotRequestTimer.start()
        else:
            logMessage(f'Error retieving order book. Status code : {str(orderBookEncoded.status_code)} -- Reason : {orderBookEncoded.reason}', priority='Error') #RESTfull request failed 
        return

    def addSelfToStream(self, ws):
        logMessage(f'Connecting websockets data stream for {self.symbol}', priority='Info')
        # msgtype "sub" for subscribing and "unsub" or anything else for unsubscribing
        message = {"method": "SUBSCRIBE", "params": self.streams, "id": 1 }
        ws.send(json.dumps(message))
        getsnapshot = threading.Thread(target=self.getOrderBookSnapshot, daemon=True)
        getsnapshot.start()
    
    def removeSelfFromStream(self, ws):
        logMessage(f'Disconnecting websockets data stream for {self.symbol}', priority='Info')
        message = {"method": "UNSUBSCRIBE", "params": self.streams, "id": 1 }
        ws.send(json.dumps(message))

def on_message(ws, message, SecuritiesRef):
    messaged = json.loads(message)
    CoinObj = SecuritiesRef[messaged['stream'].partition('usdt')[0]]
    if "stream" in messaged:
        if fnmatch.fnmatch(messaged['stream'], "*@depth@1000ms") :
            # although it should be possbile to recieve an update within the time period between orderbook updates from websocket stream best practice is to log any messages as well
            if CoinObj.SnapShotRecieved == False:
                CoinObj.ordBookBuff.append(messaged['data'])
                logMessage(f'Appending message to buffer for {getattr(CoinObj, "coin")}', priority='Debug')
            else:
                logMessage(f"Orderbook update for {getattr(CoinObj, 'coin')} - last recorded ID: {CoinObj.last_uID} -- Update = eventtime : {messaged['data']['E']}, first UID: {messaged['data']['U']},  last uID : {messaged['data']['u']} ", priority='Debug')
                # we will keep an up to date orderbook locally 
                CoinObj.updateOrderBook(messaged['data'])
                # it is more "efficient" or rather we can save a lot of disk space by only logging changes to the orderbook so we take the message data and send it to be conditioned and logged
                CoinObj.messageupdates(messaged['data'])
        elif fnmatch.fnmatch(messaged['stream'], "*@aggTrade"):
            CoinObj.addTrade(messaged['data']) #, messaged['E']
    else:
        logMessage(f"WebSocket (un)subscribed from stream, message : {messaged}", priority='Info' )
    # else:      #the catch all statement
    #     logMessage(f'Incoming message being handled incorrectly. Message: {messaged}', priority='Error')

def on_error(ws, error):
    logMessage(f'Websocket connection error: {error}', priority='Error')

def on_close(ws, close_status_code, close_msg):
    logMessage("Closed websocket connection", priority='Info')

def on_open(ws, url, Securities):
    logMessage(f'Websocket connected to : {url}', priority='Info')
    for coinObjects in Securities.values():
        snapshotthread = threading.Thread(target= coinObjects.getOrderBookSnapshot, daemon=True)
        snapshotthread.start()

def main():
    # mongoDB connection object which we will use to log to database - _NOTE: MongoClient creates 2 threads
    logMessage(f'Attempting to connect to mongoDB server at {mongoDBserver}')
    try:
        client = MongoClient(mongoDBserver, username='mainworker', password='qwdgBm4vP5P5AkhS', authSource='orderbook&trades', authMechanism='SCRAM-SHA-256')
        DBConn = client['orderbook&trades']
        logMessage('Successfully connected to mongoDB server', priority='Info')
    except Exception as e:
        logMessage(f'Error connecting to mongoDB server- Error: {e.__class__}', priority='Info')
        logMessage(f'Fix issue and try again. Exiting ...', priority='Info')
        exit(0)
    # instantiating objects for various securities - list of objects that will be used to create the base uri endpoint and subscribe to their relative streams
    # Securities = {'btc':coin("BTC", 1), 'ada':coin("ADA", 0.0001), 'eth':coin("ETH", 0.1), 'dot':coin("DOT", 0.001)} # 10,000-100,000 : 1 \ 1,000-10,000 : 0.1 \ 100-1000 : 0.01 \ 10-100 : 0.001 \ 1-10 : 0.0001
    Securities = {'btc':coin("BTC", 1, DBConn)}#, 'ada':coin("ADA", 0.0001, DBConn), 'eth':coin("ETH", 0.1, DBConn), 'dot':coin("DOT", 0.001, DBConn)} # 10,000-100,000 : 1 \ 1,000-10,000 : 0.1 \ 100-1000 : 0.01 \ 10-100 : 0.001 \ 1-10 : 0.0001
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
    logMessage(f"Attempting to connect to WebSocket endpoint : {uriEndpoint}", priority='Info')
    # websocket for handling updates -  _NOTE: websocket creates 1 threads
    ws = WebSocketApp(uriEndpoint, on_open=partial(on_open, url=uriEndpoint, Securities=Securities), on_message=partial(on_message, SecuritiesRef=Securities), on_error=on_error, on_close=on_close) #, on_ping=on_ping
    listeningForMessages = threading.Thread(target = ws.run_forever, daemon=True) #threading.Thread(target = ws.run_forever, daemon=True, kwargs={'ping_interval':300, 'ping_timeout':10, 'ping_payload':'pong'})
    listeningForMessages.start()
    # because websocket connections to binance only last 24 hours we will need to manually reconect after around 22 hours
    # main thread is being blocked by remote server so we need to create a thread that waits ~21-23 hours and then closes the connection and starts a new one

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
    # _NOTE: Used to fire off get orderbook snapshot threads here however during testing it was found that the server can be delayed and websocket connection/ getting orderbook may not be timed correctly
    #  therefore it is safer to get orderbook AFTER a websocket connection is established
    try:
        logMessage('Entering steady state/main loop of application', priority='Info')
        server.serve_forever()
    except BaseException as e:
        if e == 0:
            closemsg = f"Closed multiprocessing server as expected"
      
        else:
            closemsg = f"Unexpected error with main blocking statement or closing down BaseManager : {e}"
        # with open('fintechappLog.txt', 'a') as file:
        #     print(f"{datetime.now()} -  priority: 1 \n{closemsg}", file=file)
        logMessage(closemsg, priority='Info')
    except:
        logMessage('Error opening Remote Server and therefore cannot enter maing loop of application ', priority='Error')
    logMessage('Closing websocket Connection and joining it\'s thread in preparation for application exit.', priority='Info')
    ws.close()
    listeningForMessages.join()
    logMessage(f"Active threads : {threading.active_count()}", priority='Debug')
    logMessage('Exitting application ...', priority='Info')
    exit(0)

if __name__ == "__main__":
    main()

