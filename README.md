# Orderbook Techical Analysis - REST API

This is the (financial) security data logging component/submodule of the [Orderbook Technical Analysis project](https://github.com/RT-Tap/OrderbookTechAnalysis-Integration) whose purpose is described in the first section of the [OrderbookTechAnalysis-Integration](https://github.com/RT-Tap/OrderbookTechAnalysis-Integration) repo. 

This (sub)module has the added benefit that it can be run as a systemd-service or in a container by itself or as a normal python script alongside the database it logs to.

## Purpose
Log level2/3 financial data about a security for later analysis.  However as stated in [OrderbookTechAnalysis-Integration](https://github.com/RT-Tap/OrderbookTechAnalysis-Integration), live level 2/3 data streams for securities listed on traditional markets like NYSE or NASDAQ are extremely expensive and usually reserved for institutions and professionals.  Because this is a proof of concept we are choosing to use crypto currency data as it tends to be freely available.  The information logged is the status of the orderbook at regular intervals as well as any trades that occured during that time period.  Logging in this project also consists of consitioning data as to reduce the amount of space required to store all this data.  Conditioning in the context of this project is the process logging a "base image" of an order book at large intervals and then tracking the chagnes to these "base images" at smaller intervals and only logging these changes, therefore allowing the recreation of the orderbook at any point in time while at the same time minimizing the space required. 

## level 2 binance vs level 3 coinbase dilemma
A "issue" that arises in logging cryptocurrencies is the fact that crypto currencies are traded across many different markets rather than on one making the decision of which market to follow and log a big one.  Unfortunately there is no easy answer here, the price can and does vary between markets and so combining multiple orderbooks into one is not a viable option.  Originally it was decided that the market with the greatest volume would be the best representation of the market as a whole and therefore the level2 logger for bianance was created.  However the most frequent and volumous data steam provided by binance is the equivilent to level 2 market data by definition, this is nice but it would be even nicer if we had the equivilent to a level 3 data stream to allow greater/better analysis.  The difference is level 3 data shows individual orders from different entities being created, filled or cancelled rather than just the depth of market and therefore orderbook (or vice versa) changing, this would allow for extremely fine grained analysis into what individuals are thinking. Although all the information available in level 3 is not currently being logged, the structure to do so is there if it is decided it would be benficial in the tools or analysis that is being created for the front end.  As an additional benefit it allows you to choose between the two biggest markets, or both.

The API for both markets varies and each have their own individual incatracies so the architecture created for tracking and logging the incoming data streams tends to vary quit a bit as well.

## main.py vs main2.py
 Binance orderbook is maintained via main.py and works. Coinbase uses main2.py and maintains a local orderbook but currently lacks capability to log the orderbook information to database.  Therefore Dockerfile and systemd is setup to run binance script (main.py) but it it will be changed to use coinbases main2.py in the near future.  I kept both on the same branch because the intent is to have the ability to choose between the 2 or run both at the same time.

# Use
Environment variables 
  - USE_ENV_FILE: (Default False) If set to true will load environment variables in `vars.env` file.  
  - LOGLEVEL: (Default Info) How much logging you want, uses standard unix levels - info, warning, error etc. 
  - MONGODB_ENDPOINT: (Default 182.16.0.3:27017) IPadress:port of mongodb database to record orderbook to.  
  - MONGODB_DATABASE: (Default orderbook&trades) Name of database used to log to.  
  - ORDERBOOK_UPDATEFREQUENCY: (Default 1000) rate in ms at which new messages/updates about orberbook are recieved.  Either 100 or  1000.  
  - AS_SERVICE: (Default False) Is this being run as a systemd service? 
  - MANAGER_PORT: (Default 6634) port to use remote management script on.  
  - MANAGER_AUTHKEY: (Default `secret`) password/secret for remote management script.  

## As Container  
  - Build remotely 

        docker build https://github.com/RT-Tap/OrderbookTechAnalysis-Logger#main -t ordbooklogger
        docker run -dit --name ordbooklogger -p 6643:6643 ordbooklogger

  - Build locally   

        git clone https://github.com/RT-Tap/OrderbookTechAnalysis-Logger
        cd OrderbookTechAnalysis-Logger
        docker build  . -t ordbooklogger
        docker run -dit --name ordbooklogger -p 6643:6643 ordbooklogger

### port 6643 (the default) is used for remote management script

## systemd service  

      ./service-setup.sh  
      systemctl start finTechApp_logger

## standalone script 
    python main.py/main2.py 


## remote administration
`client.py` is the remote administration/manager script/tool and can be used to add or remove securities without interrupting logging or to get information and health checks about the current state of the logger.

the function names are pretty self explanatory and it works, a full readme writeup of it's use is coming soon.  It may be changes to use arguments rather than an interactive script in the near future so there is currently no writeup.