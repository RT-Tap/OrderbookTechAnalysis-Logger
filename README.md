

 This is considers level 3 data in traditional markets and because 

# About
This repo is part of a larger collection of repositories that makes up a project who's end goal is to provide additional forms of technical analysis based on a securities orderbook as it currently stands versus how it looked in the past.


. aims to provide  log the orderbook and trades that occur on a specific market for specific securities.  The 

environment variables used across different ways to run:
LOGLEVEL= the lowest log level to be displayed/logged- 'Error', 'Warning', 'Notice','Info', 'Debug' - default=INFO - this order is decreasing severity but increasing verbosity
MONGODB_ENDPOINT= mongoDB server, IP:port - ex: 182.16.0.3:27017
MONGODB_DATABASE= database name that you want to use to log data to ex: V1
ORDERBOOK_UPDATEFREQUENCY=orderbook update frequency in ms, binance allows 1000 or 100 (ms)
AS_SERVICE= determines whether this is run as a systemd service or as application (in container) ex: False
MANAGER_PORT= what port to allow the remote managing client to connect from ex: 6634
MANAGER_AUTHKEY= the authentication key used to allow remote managin clients to connect ex: secret

This can be run several different ways.

1) as a python application
    change vars.env to the necessary values in your system/setup (most likely just the mongoDB endpoint)
    run: python main.py
    
2) in a docker container


3) as a systemd service
after changing vars.env to the necessary values in your system/setup
automatic:
  run service-setup.sh
manual:
  install requirements.txt (requests, pymongo, websocket-client)
  move vars.env /etc/systemd/fintechapp.conf
  move finTechApp_logger.service to  /etc/systemd/user/fintechapp_logger.service (or ~/.config/systemd/user/, ~/.config/systemd/user.control/, /etc/systemd/user/, /run/systemd/user/, /usr/lib/systemd/user)
  move main.py to /usr/bin/fintechapp
  chmod +x /usr/bin/fintechapp
