# functions to detect changes which indicate a buy point for various securities
import datetime
import logging

from market import bars
from market import data
from market import date

def setupData(ibc, wc, conf, backtestArgs=None):
    dataStore = None
    dataStream = None
    if backtestArgs is not None:
        if conf.detector == 'threeBarPattern':
            dataStore = barSet = bars.BarSet()
        elif conf.detector == 'emaCrossover':
            dataStore = EMA(conf.barSizeStr, wc, backtestArgs['shortInterval'], backtestArgs['longInterval'], backtestArgs['watchCount'])
            dataStore.backTest = True
            logging.fatal('WARNING: DOING A BACKTEST, NOT USING LIVE DATA')
        dataStream = data.getHistData(wc, ibc, barSizeStr=conf.barSizeStr, longInterval=dataStore.longInterval, e=backtestArgs['e'], d=backtestArgs['d'], t=backtestArgs['t'], r=backtestArgs['r'], f=backtestArgs['f'], k=backtestArgs['k'])
        if conf.detector == 'emaCrossover':
            dataStore.calcInitEMAs(dataStream)
    elif conf.detector == 'threeBarPattern':
        dataStream = data.getTicker(wc, ibc)
    elif conf.detector == 'emaCrossover':
        barSizeStr = '1 min'
        dataStore = EMA(conf.barSizeStr, wc, conf.shortEMA, conf.longEMA, conf.watchCount)
        dataStream = data.getHistData(wc, ibc, barSizeStr=conf.barSizeStr, longInterval=dataStore.longInterval)
        dataStore.calcInitEMAs(dataStream)
    else:
        raise RuntimeError('do not know what to do!')
    return dataStore, dataStream

# get the next minute's bar
def GetNextBar(ticker, sleepFunc):
    numberOfTicksInBar = 240
    sleepSecs = 0.250
    logging.debug('getting points every 250ms')

    bar = bars.Bar(ticker.marketPrice())
    for i in range(0, numberOfTicksInBar):
        sleepFunc(sleepSecs)
        m = ticker.marketPrice()
        if m > bar.high:
            bar.high = m
        elif m < bar.low:
            bar.low = m
    bar.close = ticker.marketPrice()
    bar.cleanUp()
    bar.anotate()
    return bar

# a three bar pattern is a set of three bars where it's g/r/g or r/g/r
# indicating a momentum change
def threeBarPattern(barSet, ticker, sleepFunc):
    if barSet.first is None and barSet.second is None:
        barSet.first = GetNextBar(ticker, sleepFunc)
        barSet.second = GetNextBar(ticker, sleepFunc)
    else:
        barSet.first = barSet.second
        barSet.second = barSet.third
    barSet.third = GetNextBar(ticker, sleepFunc)
    return barSet.analyze()

from market.contract import wContract
# EMA tracks two expoential moving averages
# a long and a short
class EMA:
    wContract: wContract
    short: float = 0
    long_: float = 0
    isCrossed: bool = None
    previousState: bool = None
    stateChanged: bool = None
    areWatching: bool = None
    countOfCrossedIntervals: int = 0
    watchCount: int = 5 # barSizeSetting intervals
    shortInterval: int = 5
    longInterval: int = 20
    barSizeStr: str = None
    sleepTime: int = None
    backTest: bool = None
    curEmaIndex: int = None
    curIndex: int = None
    byPeriod: int = None # number of days of bars to examine during iterative backtest

    def __init__(self, barSizeStr, wContract, shortInterval=None, longInterval=None, watchCount=None):
        if shortInterval is not None:
            self.shortInterval = shortInterval
        if longInterval is not None:
            self.longInterval = longInterval
        if watchCount is not None:
            self.watchCount = watchCount
        dur = data.barSizeToDuration[barSizeStr]
        self.wContract = wContract
        if dur['unit'] != 'S' or not dur['value'] or not isinstance(dur['value'], int):
            raise RuntimeError('re-factor')
        self.sleepTime = dur['value']

    def __repr__(self):
        pieces = []
        for k, v in self.__dict__.items():
            pieces.append('{}:{}'.format(k, v))
        return ','.join(pieces)

    def update(self, short, long_):
        if self.isCrossed is not None:
            self.previousState = self.isCrossed
        self.short = short
        self.long = long_
        self.isCrossed = True if self.short > self.long else False
        if self.isCrossed is not None and self.previousState is not None:
            if self.isCrossed != self.previousState:
                self.stateChanged = True
            else:
                self.stateChanged = False
        logging.info('updated ema: %s', self)

    def calcInitEMAs(self, dataStream):
        short = 0
        long_ = 0
        logging.info('datastream is {}'.format(len(dataStream)))
        for interval in [self.shortInterval, self.longInterval]:
            if self.backTest: # in backtest, we can just start from 0 instead of later
                sma = 0
                startIndex = 0
                if self.byPeriod:
                    startIndex = len(dataStream) - 1 - self.byPeriod *60 *24
                    logging.info('doing by period, using index/period(days): {}/{}'.format(startIndex, self.byPeriod))
                for i in range(startIndex, startIndex+interval):
                    sma += dataStream[i].close
                sma = sma / interval
                ema = data.calcEMA(dataStream[startIndex+interval].close, sma, interval)
                self.curEmaIndex = startIndex+interval
            else:
                # first we calculate the SMA over the interval (going backwards) one interval back in the dataStream
                tailOffset = len(dataStream) - 1 - interval - 2 # See note in data.SMA
                sma = data.calcSMA(interval, dataStream, tailOffset)
                logging.info('calculated sma of {} for {} at {}'.format(sma, interval, tailOffset))
    
                prevEMA = sma
                ema = 0
                index = len(dataStream) - 1 - interval - 1 # See note in data.SMA
                for point in range(0, interval):
                    curPrice = dataStream[index].close
                    ema = data.calcEMA(curPrice, prevEMA, interval)
                    prevEMA = ema
                    index += 1
            logging.info('calculated ema for {} as {}'.format(interval, ema))
            if interval == self.shortInterval:
                short = ema
            elif interval == self.longInterval:
                long_ = ema
        self.update(short, long_)

    def recalcEMAs(self, dataStream):
        if self.backTest:
            self.curEmaIndex = self.curEmaIndex + 1
        else:
            self.curEmaIndex = len(dataStream) - 2 # See note in data.SMA
        curPrice = dataStream[self.curEmaIndex].close
        logging.info('recalculating emas at index {} using last minutes price of {}'.format(self.curEmaIndex, curPrice))
        short = data.calcEMA(curPrice, self.short, self.shortInterval)
        long_ = data.calcEMA(curPrice, self.long, self.longInterval)
        self.update(short, long_)

    # the rules for buying:
    #
    #   if the short-term ema is above the long-term ema for n minutes where n > 15 after crossing
    #   if the current interval's price drops below the long ema, do not enter (weak momo)
    #   if the market opened less than 15 minutes ago, we're just going to ignore signals
    def checkForBuy(self, dataStream, sleepFunc=None):
        logging.info('waiting for data to check for buy...')
        if not self.backTest:
            sleepFunc(self.sleepTime) # if you change this, be sure to understand the call to data.getHistData and the p argument

        self.recalcEMAs(dataStream)
        self.curIndex = len(dataStream) - 1 # See note in data module for SMA
        if self.backTest:
            self.curIndex = self.curEmaIndex + 1
        curClosePrice = dataStream[self.curIndex].close
        logging.info('current index/price: {}/{}'.format(self.curIndex, curClosePrice))

        logging.info('before checks: %s', self)
        if not self.backTest and date.marketOpenedLessThan( date.parseOpenHours(self.wContract.details), datetime.timedelta(minutes=self.watchCount) ):
            logging.warn('market just opened, waiting')
        elif not self.areWatching and self.stateChanged and self.isCrossed: # short crossed long, might be a buy, flag for re-inspection
            self.areWatching = True
            self.countOfCrossedIntervals = 0
        elif self.areWatching and self.stateChanged and not self.isCrossed: # watching for consistent crossover, didn't get it
            self.areWatching = False
        elif self.areWatching and not self.stateChanged and self.isCrossed: # watching, and it's staying set
            self.countOfCrossedIntervals += 1
        elif self.areWatching and curClosePrice < self.long:
            self.areWatching = False
        logging.info('after checks: %s', self)
    
        if self.areWatching and self.countOfCrossedIntervals > self.watchCount:
            self.areWatching = False
            logging.info('returning a buy {}'.format(self))
            return curClosePrice # buyPrice
