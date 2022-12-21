from collections import deque
from enum import Enum

class Product:
    def __init__(self, symbol) -> None:
        self.symbol = symbol

class OrderSide(Enum):
    BUY = 1
    SELL = 2 # WHAT

class Order:
    def __init__(self, product: Product, order_side: OrderSide):
        self.product = product
        self.side = order_side
        self.oid = 0
        # keep this REALLY simple and forget about qty and price for now

    @staticmethod
    def from_garbage(symbol, side):
        return Order(Product(symbol), OrderSide(side))

    def __str__(self):
        return f"Order {self.oid} PROD={self.product.symbol} SIDE={self.side}"

    def __eq__(self, other):
        if isinstance(other, int):
            return self.oid == other
        return self.oid == other.oid
        # this might haunt us later but we don't care for now
        
class SimpleMarketData:
    def log(self, s):
        print(s)
    
    
# match earliest buy to earliest sell
# keep it simple and have one product
class SimpleMatcher:
    def __init__(self, market_service):
        self.buys  = deque([])
        self.sells = deque([])
        self.market_service = market_service
        
    def emit_fill(self, a, b):
        self.market_service.log('FILL -> order: {} and order: {} '.format(a,b))
    
    def try_cancel(self, order):
        try:
            self.buys.remove(order)
            self.market_service.log(f"CANCEL -> order {order}")
        except ValueError:
            pass
        try:
            self.sells.remove(order)
            self.market_service.log(f"CANCEL -> order {order}")
        except ValueError:
            self.market_service.log(f"NOCANCEL -> order {order}")
    
    def match(self, order):
        # we fucked this before
        # match should have opportunity to match before it goes on the book
        # (and enable FOK)

        a = self.buys
        b = self.sells

        if order.side == OrderSide.SELL:
            b = self.buys
            a = self.sells
            
        if len(a) > 0:
            self.emit_fill(a.popleft(), order)
        else:
            b.append(order)
            self.market_service.log(f"NEW -> {order}")

    
# lets keep this simple
# hold one "product"
class SimpleExchange:

    def __init__(self, product_symbol, market_service):
        self.product_symbol = product_symbol
        self.matcher = SimpleMatcher(market_service) # this time around the exchange is just a pass through to the matcher
        self.next_id = 0

    def new_order(self, order):
        order.oid = self.next_id
        self.next_id += 1
        self.matcher.match(order)

    def amend_order(self):
        pass

    def cancel_order(self, oid):
        self.matcher.try_cancel(oid)


# make an exchange
market_service = SimpleMarketData()
exchange = SimpleExchange("STI", market_service)
o1 = Order.from_garbage("STI", 1)
o2 = Order.from_garbage("STI", 2)
o3 = Order.from_garbage("STI", 1)
exchange.new_order(o1)
exchange.new_order(o2)
exchange.new_order(o3)

exchange.cancel_order(1)
exchange.cancel_order(2)