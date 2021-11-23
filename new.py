from websocket import WebSocketApp
import websocket

eventTime = 1223456

def main():
    print('entered function')
    filename = 'db/' + str(eventTime) + '.txt'
    print(f'creating file : {filename}')
    file = open(filename, 'w')
    file.write('trades:')
    #file.write(self.trades)
    file.write('orderbook')
    #file.write(self.orderBook)
    file.close()

if __name__ == "__main__":
    main()