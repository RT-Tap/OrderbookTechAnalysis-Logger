import argparse
from multiprocessing.managers import BaseManager
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

parser = argparse.ArgumentParser(
    description='Connects to our fintechapp logging application for (remote) control\nOnly way to interact with it as it will be run as a service \n Warning: if you pass one argument you must pass all which you want as manual entry is skipped.',
    epilog="Commands that can be run:\nRequestOrderbook ")
parser.add_argument('hostport', action='store', default='127.0.0.1:12345', type=str, help='Host:port', nargs='?')
parser.add_argument('-d', '--host', dest='host', action='store', type=str, help='Host name/IP.')
parser.add_argument('-p','--port', dest='port', type=int, help='Port to connect on')
parser.add_argument('-k','--authkey', dest='authkey', default='secret', type=str, help='authentication key of server')
parser.add_argument('-a','--Command', dest='commands', action='store', help='Command to run.\naddSecurity, removeSecurity, getorderbook, ConnectionTest') 
parser.add_argument('-s','--symbol', dest='symbols', action='append', help='the symbol/security you want the action done on, can be use m;ultiple times.', nargs="*")
args = parser.parse_args()
if args.hostport != None: 
    host_port = args.hostport.split(':')
    host = host_port[0]
    port = host_port[1]
if args.host != None: host = args.host
if args.port != None: port = args.port
# if args.authkey != None: authkey = args.authkey
authkey = args.authkey
if args.commands != None: commands = args.commands
if args.symbols != None: symbols = args.symbols

#if no arguments were passed proceed to manual entry of paramters
# if not len(sys.argv) > 1: 
print(ourIP)

# m = BaseManager(address=(host, port), authkey=b'secret')
# m = BaseManager(address=(host, port), authkey=authkey.encode('ASCII'))
m = BaseManager(address=('127.0.0.1', 12345), authkey=b'secret')
m.register('RemoteOperations')
m.connect()
remoteops = m.RemoteOperations()


# print(remoteops.ConnectionTest(ourIP))

# print(remoteops.addSecurity("ada", 0.0001))

# print(remoteops.removeSecurity("ada"))

# print(remoteops.retrieveCurrentOrderbook('btc'))

# remoteops.listSecurities()

# remoteops.RequestOrderbookSnapShot("btc")
# remoteops.RequestOrderbookSnapShot("ada")
print(remoteops.addSecurity("ada", 0.0001))
time.sleep(6)
remoteops.resetWebSocket()
time.sleep(12)
remoteops.terminate()

# print(remoteops.getThreadCount())