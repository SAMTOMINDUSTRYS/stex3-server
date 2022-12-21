from collections import deque
from enum import Enum

class Product:
    def __init__(self, symbol) -> None:
        self.symbol = symbol

class OrderSide(Enum):
    BUY = 1
    SELL = 2 # WHAT

class Order:
    def __init__(self, product: Product, order_side: OrderSide, price):
        self.product = product
        self.side = order_side
        self.oid = 0
        self.price = price
        # keep this REALLY simple and forget about qty and price for now

    @staticmethod
    def from_garbage(symbol, side, price):
        return Order(Product(symbol), OrderSide(side), price)

    def __str__(self):
        return f"Order {self.oid} PROD={self.product.symbol} SIDE={self.side}"

    def __hash__(self):
        return hash(self.oid)
        
    # this might haunt us later but we don't care for now
    def __eq__(self, other):
        if isinstance(other, int):
            return self.oid == other
        return self.oid == other.oid

# THIS is the truth
# clients need to connect and make sure they have read all messages in their sequence
class SimpleMarketData:
    def __init__(self) -> None:
        self.price = None

    def log(self, s):
        print(s)

    def update_price(self, trade):
        self.price = trade["price"]
        self.log(f"PRICE -> {self.price}")
    
    
# match earliest buy to earliest sell
# keep it simple and have one product
class SimpleMatcher:
    def __init__(self, market_service):
        self.buys  = deque([])
        self.sells = deque([])
        self.market_service = market_service
    
    # matcher IS responsible for the price
    def emit_fill(self, a, b):
        price = ((a.price +b.price)/2)
        self.market_service.log('FILL -> order: {} and order: {} @ {}'.format(a,b, price))
        self.market_service.update_price({"price": price})
    
    def try_amend(self, order):
        a = self.buys
        if order.side == OrderSide.SELL:
            a = self.sells
        
        found = None
        for (i, book_order) in enumerate(a):
            print(book_order, order)
            if order == book_order:
                found = i
                break
        if found is not None:
            a[found] = order
            self.market_service.log(f"AMEND -> order {order}")
        else:
            self.market_service.log(f"NOAMEND -> order {order.oid}")
                

    def try_cancel(self, oid):
        try:
            self.buys.remove(oid)
            self.market_service.log(f"CANCEL -> order {oid}")
            return
        except ValueError:
            pass
        try:
            self.sells.remove(oid)
            self.market_service.log(f"CANCEL -> order {oid}")
            return
        except ValueError:
            pass

        self.market_service.log(f"NOCANCEL -> order {oid}")
    
    def match(self, order):
        # we fucked this before
        # match should have opportunity to match before it goes on the book
        # (and enable FOK)

        a = self.buys
        b = self.sells

        if order.side == OrderSide.SELL:
            b = self.buys
            a = self.sells
            
        if len(b) > 0:
            self.emit_fill(b.popleft(), order)
        else:
            a.append(order)
            self.market_service.log(f"NEW -> {order}")

    
# lets keep this simple
# hold one "product"
class SimpleExchange:

    # exchange should validate the user is allowed to cancel/amend
    def __init__(self, product_symbol, market_service):
        self.product_symbol = product_symbol
        self.matcher = SimpleMatcher(market_service) # this time around the exchange is just a pass through to the matcher
        self.next_id = 0

    def new_order(self, order):
        order.oid = self.next_id
        self.next_id += 1
        self.matcher.match(order)

    def amend_order(self, order):
        # any checking should be done here
        # we decided side amend is not allowed
        self.matcher.try_amend(order)
    

    def cancel_order(self, oid):
        self.matcher.try_cancel(oid)


class SimpleGateway:
    def __init__(self, exchange):
        self.__exchange = exchange # this would be a exchange connection object

    def new_order(self, product, side, price):
        order = Order.from_garbage(product, side, price)
        self.__exchange.new_order(order)
        return order # does not necessarily imply order has been accepted

    def cancel_order(self, oid):
        self.__exchange.cancel_order(oid)

    def amend_order(self, order):
        self.__exchange.amend_order(order)
    

market_service = SimpleMarketData()
exchange = SimpleExchange("STI", market_service)
gateway = SimpleGateway(exchange)
gateway.new_order("STI", 1, 10)
gateway.new_order("STI", 2, 12)
gateway.new_order("STI", 1, 1)
gateway.cancel_order(1)
gateway.cancel_order(2)

order = gateway.new_order("STI", 1, 10)
order.oid = 3
gateway.amend_order(order)

# gateway should check message is valid and create relevant objects
# exchange should validate objects for business rules
# matcher is dumb and just follows all instructions

# this time sam is not hung up on fancy architecture and tom is not hung
# up on making it perfectly realistic