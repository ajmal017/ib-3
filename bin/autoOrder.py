#!/usr/bin/python3

import datetime
import logging
import sys

from ib_insync import *

sys.path.append(r'.')
from market import bars
from market import config
from market import connect
from market import contract
from market import data
from market import detector
from market import order
from market import trade

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--conf', type=str, required=True)
parser.add_argument('--symbol', type=str, required=True)
parser.add_argument('--localSymbol', type=str, default=None)
#parser.add_argument('--short', default=None, type=int) # for ema detector, short moving avg
#parser.add_argument('--long', default=None, type=int) # for ema detector, long moving avg
parser.add_argument('--prod', action='store_true', default=None)
parser.add_argument('--debug', action='store_true', default=None)
parser.add_argument('--info', action='store_true', default=None)
args = parser.parse_args()

def isMaxQty(p, conf):
    if conf.byPrice:
        # super wonky: avg cost is avg cost per share
        # .position is share count
        # dollarAmt is the max we'll spend
        # openPositions is the number of amounts
        #  $25 * 4 sh >= $500 * 2
        return p.avgCost * p.position >= conf.dollarAmt * conf.openPositions
    else:
        return p.position >= conf.qty * conf.openPositions

startTime = datetime.datetime.utcnow()

ibc = connect.connect(args.debug, args.prod)
if args.info:
    util.logToConsole(logging.INFO)
conf = config.getConfig(args.conf, autoOrder=True)

wc = contract.wContract(ibc, args.symbol, args.localSymbol)

dataStore = None
dataStream = None
if conf.detector == 'threeBarPattern':
    dataStream = data.getTicker(wc, ibc)
    dataStore = bars.BarSet()
elif conf.detector == 'emaCrossover':
    barSizeStr = '1 min'
    dataStore = detector.EMA(barSizeStr)
    dataStream = data.getHistData(wc, ibc, barSizeStr=barSizeStr, longInterval=detector.EMA.longInterval)
    dataStore.calcInitEMAs(dataStream)
else:
    raise RuntimeError('do not know what to do!')

# what we really want is to extract the "I detected a reason to buy contract n at bar y with reuqirements z"
# and add the es one as well.
logging.warn('running trade loop for %s...', wc.symbol)
while datetime.datetime.utcnow() < startTime + datetime.timedelta(hours=20):
    buyPrice = None
    if conf.detector == 'threeBarPattern':
        buyPrice = detector.threeBarPattern(dataStore, dataStream, ibc.sleep)
    elif conf.detector == 'emaCrossover':
        buyPrice = dataStore.checkForBuy(dataStream, ibc.sleep)

    orderDetails = None
    if buyPrice is not None:
        try:
            orderDetails = order.OrderDetails(buyPrice, conf, wc)
        except FloatingPointError as e:
            logging.debug('got a NaN %s', e)

    if orderDetails is not None:
        makeTrade = True
        positions = ibc.positions()
        ibc.sleep(0)
        for p in positions:
            if p.contract == wc.contract and isMaxQty(p, conf):
                logging.warn('passing on trade as max positions already open')
                makeTrade = False

        if makeTrade:
            orders = order.CreateBracketOrder(orderDetails)
            trades = trade.PlaceBracketTrade(orders, orderDetails, ibc)
            trade.CheckTradeExecution(trades, orderDetails)
            logging.debug(trades)

connect.close(ibc, wc.contract)
sys.exit(0)
