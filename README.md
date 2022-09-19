# Orderbook Techical Analysis - REST API

This is the (financial) security data logging component/submodule of the [Orderbook Technical Analysis project](https://github.com/RT-Tap/OrderbookTechAnalysis-Integration) whose purpose is described in the first section of the [OrderbookTechAnalysis-Integration](https://github.com/RT-Tap/OrderbookTechAnalysis-Integration) repo. 

## Purpose
Log level2/3 financial data about a security for later analysis.  However as stated in [OrderbookTechAnalysis-Integration](https://github.com/RT-Tap/OrderbookTechAnalysis-Integration), live level 2/3 data streams for securities listed on traditional markets like NYSE or NASDAQ are extremely expensive and usually reserved for institutions and professionals.  Because this is a proof of concept we are choosing to use crypto currency data as it tends to be freely available.  The information logged is the status of the orderbook at regular intervals as well as any trades that occured during that time period.  Logging in this project also consists of consitioning data as to reduce the amount of space required to store all this data.  Conditioning in the context of this project is the process logging a "base image" of an order book at large intervals and then tracking the chagnes to these "base images" at smaller intervals and only logging these changes, therefore allowing the recreation of the orderbook at any point in time while at the same time minimizing the space required. 

## How to rum
This (sub)module is meant to be run one of 2 different ways - regardless which way is chosen, all the necessary setup scripts are available for each route
- As a service (possibly in the same container as the mongoDB database)
    - systemd
    automatic:
  run service-setup.sh
manual:
  install requirements.txt (requests, pymongo, websocket-client)
  move vars.env /etc/systemd/fintechapp.conf
  move finTechApp_logger.service to  /etc/systemd/user/fintechapp_logger.service (or ~/.config/systemd/user/, ~/.config/systemd/user.control/, /etc/systemd/user/, /run/systemd/user/, /usr/lib/systemd/user)
  move main.py to /usr/bin/fintechapp
  chmod +x /usr/bin/fintechapp
    - python 
- A container as a component of a service which is created (and described) by the [OrderbookTechAnalysis-Intefration](https://github.com/RT-Tap/OrderbookTechAnalysis-Integration) repo.

# level 2 binance vs level 3 coinbase dilemma
A "issue" that arises in logging cryptocurrencies is the fact that crypto currencies are traded across many different markets rather than on one making the decision of which market to follow and log a big one.  Unfortunately there is no easy answer here, the price can and does vary between markets and so combining multiple orderbooks into one is not a viable option.  Originally it was decided that the market with the greatest volume would be the best representation of the market as a whole and therefore the level2 logger for bianance was created.  However the most frequent and volumous data steam provided by binance is the equivilent to level 2 market data by definition, this is nice but it would be even nicer if we had the equivilent to a level 3 data stream to allow greater/better analysis.  The difference is level 3 data shows individual orders from different entities being created, filled or cancelled rather than just the depth of market and therefore orderbook (or vice versa) changing, this would allow for extremely fine grained analysis into what individuals are thinking. Although all the information available in level 3 is not currently being logged, the structure to do so is there if it is decided it would be benficial in the tools or analysis that is being created for the front end.  As an additional benefit it allows you to choose between the two biggest markets, or both.

The API for both markets varies and each have their own individual incatracies so the architecture created for tracking and logging the incoming data streams tends to vary quit a bit as well.