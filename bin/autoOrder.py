#!/usr/bin/python3

import datetime
import logging
import pytz
import sys

sys.path.append(r'/home/adam/ibCur')
from market import account
from market import bars
from market import config
from market import connect
from market import contract
from market import data
from market import date
from market import detector
from market import order
from market import trade

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--conf', type=str, required=True)
parser.add_argument('--debug', action='store_true', default=None)
parser.add_argument('--info', action='store_true', default=None)
args = parser.parse_args()

def now():
    return datetime.datetime.utcnow().astimezone(pytz.utc)

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

def getPosition(wc):
    positions = wc.ibClient.positions()
    wc.ibClient.sleep(0)
    for p in positions:
        if p.contract == wc.contract:
            return p
    return None

def outputIfHolding(wc):
    p = getPosition(wc)
    if p is not None and p.contract == wc.contract:
        out = ''
        if p.position > 0:
            out += 'holding an open position on {} of {}; '.format(p.contract.symbol, p.position)
        else:
            out += 'no open position on {}; '.format(p.contract.symbol)
        out += 'marketPrice: {} unrealizedPNL: {}, realizedPNL: {}'.format(p.marketPrice, p.unrealizedPNL, p.realizedPNL)
        logging.warn(out)

def checkForExcessiveLosses(wc, conf):
    loss = detector.lossTooHigh(wc, conf)
    if loss:
        logging.critical('lost too many dollars, exiting.  {} {} {} {}'.format(config.maxLoss, rpnl, conf.account, wc.contract))
        sys.exit(1)
    p = getPosition(wc)
    if loss is None and p is not None and p.contract == wc.contract:
        raise RuntimeError('somethings wrong with pnl: {} {} {}'.format(wc.pnl, wc.contract, p))

startTime = now()

conf = config.getConfig(args.conf, detectorOn=True)
ibc = connect.connect(conf, args.debug)
from ib_insync import util
if args.info:
    util.logToConsole(logging.INFO)
account.summary(ibc, conf.account)

wc = contract.wContract(ibc, conf.symbol, conf.localSymbol)
ibc.reqPnLSingle(account=conf.account, modelCode='', conId=wc.contract.conId) # request updates

dataStore, dataStream = detector.setupData(ibc, wc, conf)

totalTrades = 0
outputIfHolding(wc)
portfolioCheck = now()
# what we really want is to extract the "I detected a reason to buy contract n at bar y with reuqirements z"
# and add the es one as well.
logging.warn('running trade loop for %s...', wc.symbol)
while now() < startTime + datetime.timedelta(hours=20):
    if totalTrades >= conf.totalTrades:
        logging.warn('completed total number of trades {}/{}, exiting'.format(totalTrades, conf.totalTrades))
        break
    elif not date.isMarketOpen( date.parseOpenHours(wc.details) ):
        logging.warn('market closed, waiting to open')
        ibc.sleep(60 * 5)
    # FIXME: is a "just opened" useful here, or is the one in EMA's check for buy ok?
    elif not date.isMarketOpen(date.parseOpenHours(wc.details), now() + datetime.timedelta(minutes=conf.greyzone)): # closing soon
        logging.warn('market closing soon, waiting for close [will restart analysis on open]')
        ibc.sleep(60 * conf.greyzone)

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
        p = getPosition(wc)
        if p.contract == wc.contract and isMaxQty(p, conf):
            logging.warn('passing on trade as max positions already open')
            makeTrade = False

        orders = order.CreateBracketOrder(orderDetails, conf.account)
        if not order.adequateFunds(ibc, orderDetails, orders):
            logging.error('not enough funds to place a trade.')
            makeTrade = False

        if makeTrade:
            trades = trade.PlaceBracketTrade(orders, orderDetails, ibc)
            trade.CheckTradeExecution(trades, orderDetails)
            totalTrades += 1
            logging.debug(trades)

    if datetime.datetime.utcnow().astimezone(pytz.utc) > portfolioCheck + datetime.timedelta(minutes=30):
        portfolioCheck = datetime.datetime.utcnow().astimezone(pytz.utc)
        outputIfHolding(wc)

    checkForExcessiveLosses(wc, conf)

connect.close(ibc, wc)
sys.exit(0)
