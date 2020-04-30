from ib_insync.contract import Contract
from ib_insync.contract import ContractDetails
from ib_insync.contract import Stock
from ib_insync.ib import IB

# wrapper for ib's contract since things are spread out among the contract and its details
class wContract:
    contract: Contract
    details: ContractDetails
    symbol: str
    localSymbol: str
    ibclient: IB
    def __init__(self, ibc, symbol, localSymbol):
        self.symbol = symbol
        self.localSymbol = localSymbol
        self.ibclient = ibc
        self.ibContract()
        self.qualify()
        self.ibDetails()

    def ibContract(self):
        c = None
        if self.symbol == 'TQQQ':
            c = Stock(symbol=self.symbol, exchange='SMART', currency='USD', primaryExchange='NASDAQ')
        elif self.symbol == 'SQQQ':
            c = Stock(symbol=self.symbol, exchange='SMART', currency='USD', primaryExchange='NASDAQ')
        elif self.symbol == 'AAP2' or self.symbol == 'AMZ2' or self.symbol == 'CRM2' or self.symbol == 'FB2' or self.symbol == 'GOO2' or self.symbol == 'GS2' or self.symbol == 'MSF2' or self.symbol == 'NFL2' or self.symbol == 'NVD2' or self.symbol == 'VIS2':
            c = Stock(symbol=self.symbol, exchange='SMART', currency='USD', primaryExchange='LSE')
        elif (self.symbol == 'ES' or self.symbol == 'NQ') and self.localSymbol != None:
            c = Contract(secType='FUT', symbol=self.symbol, localSymbol=self.localSymbol, exchange='GLOBEX', currency='USD')
        else:
            raise RuntimeError('no security specified')
        self.contract = c

    def qualify(self):
        r = self.ibclient.qualifyContracts(self.contract)
        if len(r) != 1 or r[0].symbol != self.symbol:
            raise LookupError('could not validate response: %s', r[0])
        if self.localSymbol == None: # sometimes the local symbol isn't passed in (like with stocks)
            if self.contract.localSymbol == None:
                raise LookupError('problem with looking up contract')
            else:
                self.localSymbol = self.contract.localSymbol

    def ibDetails(self):
        r = self.ibclient.reqContractDetails(self.contract)
        if len(r) != 1 or r[0].contract != self.contract:
            raise LookupError('problem getting contract details: %s', r)
        self.details = r[0]
