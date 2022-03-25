import argparse
from audioop import add
from multiprocessing.managers import BaseManager
from re import sub
import time
import socket # this is just used to get our local ip
import os

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def send_addSecurity(connection, security,  *pair):
    if len(pair) == 0:
        print(connection.addSecurity(security))
    else:
        print(connection.addSecurity(security, pair))

def send_removeSecurity(connection, security):
    print(connection.removeSecurity(security))

def send_requestOrderbookSnapshot(connection, security):
    print(connection.requestOrderbookSnapshot(security))

def send_listSecurities(connection):
    print(print(connection.listSecurities()))

def send_connectionTest(connection):
    print(connection.connectionTest(ourIP))

def send_getThreadCount(connection):
    print(connection.getThreadCount())

def send_resetWebSocket(connection):
    print(connection.resetWebSocket())

def send_retrieveCurrentOrderbook(connection, security):
    print(connection.retrieveCurrentOrderbook(security))

def send_elapsedRunningTime(connection):
    print(connection.elapsedRunningTime())

def send_terminate(connection):
    connection.terminate()
    for i in range(5):
        print('. ', end=" ") # print on same line 
        time.sleep(1)
    try:
        print(send_connectionTest())
    except:
        print('Successfully terminated program.')

host = os.getenv('LOGGER_SERVER_IP', '182.16.0.8')
port= int(os.getenv('MANAGER_PORT', 66345))
authkey=os.getenv('MANAGER_AUTHKEY', 'secret')
ourIP = get_local_ip()

print(f'Current settings:\nServer:{host}:{port}\nauthentication:{authkey}')
change = input("change settings?\n")
if change == 'y' or change == 'yes':
    while change == 'y' or change == 'yes':
        host = input('Host ip/hostname:')
        port = input('Port:')
        authkey = input('authkey:')
        print('Updated settings:\n')
        print(f'Current settings:\nServer:{host}:{port}\nauthentication:{authkey}')
        update = input('Correct?')
        if update == 'y' or update =='yes':
            change = 'n'




m = BaseManager(address=(host, port), authkey=authkey.encode())     # authkey=b'secret'
m.register('RemoteOperations')
m.connect()
remoteops = m.RemoteOperations()

proceed = True

while proceed == True:
    command = input('Enter which command you would like to run:\n 0=requestOrderbookSnapShot\n1=addSecurity\n2=removeSecurity\n3=terminate\n4=listSecurities\n5=connectionTest\n6=getThreadCount\n7=resetWebSocket\n8=retrieveCurrentOrderbook\n9=elapsedRunningTime\n')
    if command == '0' :
        security = input('For what security :\n')
        send_requestOrderbookSnapshot('test', security)
    elif command == '1' or command == 'addSecurity':
        security = input('What security are we adding:\n')
        send_addSecurity('test', security)
    elif command == '2' or command == 'removeSecurity':
        security = input("what security would you like to remove:\n")
        send_removeSecurity('lol', security)
    elif command == '3':
        send_terminate('test')
    elif command == '4':
        send_listSecurities('conn')
    elif command == '5':
        send_connectionTest('ok')
    elif command == '6':
        send_getThreadCount('plz')
    elif command == '7':
        send_resetWebSocket('lodk')
    elif command == '8':
        send_retrieveCurrentOrderbook('ol')
    elif command == '9':
        send_elapsedRunningTime('re')
    else: print('please enter correct command')

    runagain = input('Run Another command?\n')
    if runagain  == 'n' or runagain == 'no' or runagain == 'exit':
        proceed = False



''' 
import argparse
from audioop import add
from multiprocessing.managers import BaseManager
from re import sub
import time
import socket # this is just used to get our local ip

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

host = 'localhost'
port=12345
authkey='secret'
ourIP = get_local_ip()

def send_addSecurity(connection, security, groupAmt, *pair):
    print('addsecurity')
    # if len(pair) == 0:
    #     print(connection.addSecurity(security, groupAmt))
    # else:
    #     print(connection.addSecurity(security, groupAmt, pair))

def send_removeSecurity(connection, security):
    print('removesecurtiy')
    # print(connection.removeSecurity(security))

def send_requestOrderbookSnapshot(connection, security):
    print('requestorderbook')
    # print(connection.requestOrderbookSnapshot(security))

def send_listSecurities(connection):
    print('listsecurities')
    # print(print(connection.listSecurities()))

def send_connectionTest(connection):
    print(connection.connectionTest(ourIP))

def send_getThreadCount(connection):
    print('threadcount')
    # print(connection.getThreadCount())

def send_resetWebSocket(connection):
    print('resetwebsockets')
    # print(connection.resetWebSocket())

def send_retrieveCurrentOrderbook(connection, security):
    print('retrieveorderbooks')
    # print(connection.retrieveCurrentOrderbook(security))

def send_elapsedRunningTime(connection):
    print('r;unningtime')
    # print(connection.elapsedRunningTime())

def send_terminate(connection):
    print('terminate')
    # connection.terminate()
    # for i in range(5):
    #     print('. ', end=" ") # print on same line 
    #     time.sleep(1)
    # try:
    #     print(send_connectionTest())
    # except:
    #     print('Successfully terminated program.')

# HOW to run :
# can be run one of two ways - command first or host first
# command first:  choose a single command:
# python client.py command <symbols?> <host> <optional>
# if the command takes symbols list them right after command and if you ;want to define a different host it should be after all symbols and before optuionals
# host first: choose a command after defining host 
# python client.py host <alternatively: -d host -p port> command <symbol>
# if you run with a hostname:port (or -d hostname -p port) and then a command <symbols> if that command takes symbols 
# command first examples: 
# python client.py addSecurity ada dot eth
# python client.py addSecurity ada 127.0.0.1:12345
# python client.py addSecurity ada dot -d 127.0.0.1 -p 12345 -k secret
# host first exasmples:
# python client.py 127.0.0.1:12345 



parser = argparse.ArgumentParser(
    description='Connects to our fintechapp logging application for (remote) control\nOnly way to interact with it as it will be run as a service \n Warning: if you pass one argument you must pass all which you want as manual entry is skipped.',
    epilog="Commands that can be run:\nrequestOrderbookSnapShot, addSecurity, removeSecurity, requestOrderbookSnapshot, terminate, listSecurities, connectionTest, getThreadCount, resetWebSocket,  retrieveCurrentOrderbook, elapsedRunningTime")
subparser = parser.add_subparsers(dest='command')

requestOrderbookSnapShot = subparser.add_parser('requestOrderbookSnapShot')
requestOrderbookSnapShot.add_argument('symbol', type=str,  nargs="*", action='append')
requestOrderbookSnapShot.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
requestOrderbookSnapShot.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
requestOrderbookSnapShot.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
requestOrderbookSnapShot.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

addSecurity = subparser.add_parser('addSecurity')
addSecurity.add_argument('symbol', type=str,  nargs="*", action='append')
addSecurity.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
addSecurity.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
addSecurity.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
addSecurity.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

removeSecurity = subparser.add_parser('removeSecurity')
removeSecurity.add_argument('symbol', type=str,  nargs="*", action='append')
removeSecurity.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
removeSecurity.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
removeSecurity.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
removeSecurity.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

requestOrderbookSnapshot = subparser.add_parser('requestOrderbookSnapshot')
requestOrderbookSnapshot.add_argument('symbol', type=str,  nargs="*", action='append')
requestOrderbookSnapshot.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
requestOrderbookSnapshot.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
requestOrderbookSnapshot.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
requestOrderbookSnapshot.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

terminate = subparser.add_parser('terminate')
terminate.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
terminate.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
terminate.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
terminate.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

listSecurities = subparser.add_parser('listSecurities')
listSecurities.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
listSecurities.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
listSecurities.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
listSecurities.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

connectionTest = subparser.add_parser('connectionTest')
connectionTest.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
connectionTest.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
connectionTest.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
connectionTest.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

getThreadCount = subparser.add_parser('getThreadCount')
getThreadCount.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
getThreadCount.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
getThreadCount.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
getThreadCount.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

resetWebSocket = subparser.add_parser('resetWebSocket')
resetWebSocket.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
resetWebSocket.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
resetWebSocket.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
resetWebSocket.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)


retrieveCurrentOrderbook = subparser.add_parser('retrieveCurrentOrderbook')
retrieveCurrentOrderbook.add_argument('symbol', type=str,  nargs="*", action='append')
retrieveCurrentOrderbook.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
retrieveCurrentOrderbook.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
retrieveCurrentOrderbook.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
retrieveCurrentOrderbook.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

elapsedRunningTime = subparser.add_parser('elapsedRunningTime')
elapsedRunningTime.add_argument('host', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
elapsedRunningTime.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
elapsedRunningTime.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
elapsedRunningTime.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)

parser.add_argument('-D', '--hostport', action='store', default='127.0.0.1:12345', type=str, help='Host:Port', nargs='?')
parser.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.', nargs=1)
parser.add_argument('-p','--port', dest='port', type=int, help='Port to connect on', nargs=1)
parser.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server', nargs=1)
parser.add_argument('--command', dest='commands', action='store', help='Command to run.\naddSecurity, removeSecurity, getorderbook, ConnectionTest', nargs='*') 
parser.add_argument('-s','--symbol', dest='symbol', action='append', help='the symbol/security you want the action done on, can be use multiple times.', nargs="*")
# parser.add_argument('-t', '--terminate', dest='terminate', action='store-true', help='Terminate program')

args = parser.parse_args()


# m = BaseManager(address=(host, port), authkey=b'secret')
# m = BaseManager(address=(host, port), authkey=authkey.encode('ASCII'))
if args.command == 'connectionTest':
    print('connection tsest')
    # try:
    #     m = BaseManager(address=(host, port), authkey=authkey.encode())        # authkey=b'secret'
    #     m.register('RemoteOperations')
    #     m.connect()
    #     remoteops = m.RemoteOperations()
    #     send_connectionTest(remoteops)
    # except:
    #     print('Could not connect to destination')
    # exit(0)

# m = BaseManager(address=(host, port), authkey=authkey.encode())     # authkey=b'secret'
# m.register('RemoteOperations')
# m.connect()
# remoteops = m.RemoteOperations()
remoteops = 'lol'

if args.command == 'requestOrderbookSnapShot':
    for securities in requestOrderbookSnapshot.symbol:
        send_requestOrderbookSnapshot(remoteops, securities)

elif args.command == 'addSecurity':
    for securities in  addSecurity.symbol:
        send_addSecurity(remoteops, securities,)

elif args.command == 'removeSecurity':
    for securities in removeSecurity.symbol:
        send_removeSecurity(remoteops, securities)

elif args.command == 'terminate':
    send_terminate(remoteops)

elif args.command == 'listSecurities':
    send_listSecurities(remoteops)

elif args.command == 'getThreadCount':
    send_getThreadCount(remoteops)

elif args.command == 'resetWebSocket':
    send_resetWebSocket(remoteops)

elif args.command == 'retrieveCurrentOrderbook':
    for securities in args.symbol:
        send_retrieveCurrentOrderbook(remoteops, securities)

elif args.command == 'elapsedRunningTime':
    send_elapsedRunningTime()

if terminate == True:
    send_terminate(remoteops)
    exit(0)

if args.commands:
    for command in args.commands:
        for security in args.symbol:
            eval('send_'+command)(remoteops, security)






# print(remoteops.ConnectionTest(ourIP))
# print(remoteops.addSecurity("ada", 0.0001))
# print(remoteops.removeSecurity("ada"))
# print(remoteops.retrieveCurrentOrderbook('btc'))
# remoteops.listSecurities()
# remoteops.RequestOrderbookSnapShot("btc")
# remoteops.RequestOrderbookSnapShot("ada")
# print(remoteops.addSecurity("ada", 0.0001))
# time.sleep(6)
# remoteops.resetWebSocket()
# time.sleep(12)
# remoteops.terminate()
# print(remoteops.getThreadCount())
'''