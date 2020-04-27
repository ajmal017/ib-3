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
from market import order
from market import rand
from market import trade

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--symbol', type=str, required=True)
parser.add_argument('--localSymbol', type=str)
parser.add_argument('--conf', type=str, required=True)
parser.add_argument('--prod', action='store_true', default=None)
parser.add_argument('--debug', action='store_true')
args = parser.parse_args()

startTime = datetime.datetime.utcnow()

ibc = connect.connect(args.debug, args.prod)
conf = config.getConfig(args.conf)

if args.localSymbol:
    c = contract.getContract(args.symbol, args.localSymbol)
else:
    c = contract.getContract(args.symbol, None)
contract.qualify(c, ibc)

ticker = data.getTicker(c, ibc)
ibc.sleep(0)

logging.warn('running trade loop for %s...', c.symbol)
barSet = bars.BarSet()
while datetime.datetime.utcnow() < startTime + datetime.timedelta(hours=24):
    if barSet.first is None and barSet.second is None:
        barSet.first = bars.GetNextBar(ticker, ibc.sleep)
        barSet.second = bars.GetNextBar(ticker, ibc.sleep)
    else:
        barSet.first = barSet.second
        barSet.second = barSet.third
    barSet.third = bars.GetNextBar(ticker, ibc.sleep)
    try:
        orderDetails = order.OrderDetails(barSet.analyze(), conf, c)
    except FloatingPointError as e:
        logging.debug('got a NaN %s', e)

    if orderDetails.buyPrice is not None:
        positions = ibc.positions()
        ibc.sleep(0)
        makeTrade = True
        for p in positions:
            if p.contract == c and p.position >= conf.qty * conf.openPositions:
                logging.warn('passing on trade as max positions already open')
                makeTrade = False
        if makeTrade:
            orders = order.CreateBracketOrder(orderDetails)
            trades = trade.PlaceBracketTrade(orders, orderDetails, ibc)
            trade.CheckTradeExecution(trades, orderDetails)
            logging.debug(trades)

connect.close(ibc, c)
sys.exit(0)
