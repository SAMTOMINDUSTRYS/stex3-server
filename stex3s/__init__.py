import socket
from collections import deque
from enum import Enum

class Product:
    def __init__(self, symbol) -> None:
        self.symbol = symbol

class OrderSide(Enum):
    BUY = 1
    SELL = 2 # WHAT

class MarketMessage(Enum):
    NEW_ORDER = 1
    FILL_ORDER = 2
    AMEND_ORDER = 3
    CANCEL_ORDER = 4

class Colors(Enum):
    PINK = "\033[95m"
    BLUE ="\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"

    def __str__(self):
        return self.value

    @classmethod
    def of_color(cls, color, msg):
        return str(color)+msg+str(cls.RESET)

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
# is this actually needed?
class SimpleMarketData:
    def __init__(self) -> None:
        self.level_one = None
        self.level_two = {
            # we are going to ignore this complexity for now
        }
        self.clients = []

    def register_client(self, client):
        self.clients.append(client)

    def send_message(self, msg):
        for client in self.clients:
            client.receive_message(msg)

    # lol do this nicely
    def l1_update(self, payload):
        last_payload = self.level_one
        if last_payload != payload:
            msg = Colors.of_color(Colors.RED, "[L1]") + str(payload)
            print(msg)
            #self.send_message(f"{c}{str(payload)}")
        self.level_one = payload

    def l2_update(self, event_type, payload):
        msg = f"{Colors.PINK}[L2]{Colors.RESET} {event_type} {payload}"
        print(msg)
        #self.send_message(msg)

        ##if event_type == MarketMessage.FILL_ORDER:
        #    # changes: last_price, last_size, buy/sell prices/sizes
        #    self.update_price(payload["last_price"])

    def client_update(self, event_type,  payload):
        msg = f"{Colors.GREEN}[CL]{Colors.RESET} {event_type} {payload}"
        self.send_message(msg)

    def update_price(self, price):
        last_price = self.level_one["last_price"]
        self.level_one["last_price"] = price
        if last_price != price:
            msg = f"{Colors.RED}[L1]{Colors.RESET} PRICE CHANGE = {self.level_one['last_price']}"
            print(msg)
            #self.send_message(msg)
    
    
# match earliest buy to earliest sell
# keep it simple and have one product
class SimpleMatcher:
    def __init__(self, market_service):
        self.buys  = deque([])
        self.sells = deque([])
        self.market_service = market_service
        self.last_price = None
        self.last_size = None
        self.best_buy_price = None
        self.best_buy_size = None
        self.best_sell_price = None
        self.best_sell_size = None

    def update_l1(self):
        # emit l1
        try:
            top_buy = self.buys[0]
            self.best_buy_price = top_buy.price
            self.best_buy_size = 1
        except IndexError:
            pass
        try:
            top_sell = self.sells[0]
            self.best_sell_price = top_sell.price
            self.best_sell_size = 1
        except IndexError:
            pass
            
        payload = {
            "last_price": self.last_price,
            "last_size": self.last_size,
            "buy_price": self.best_buy_price,
            "buy_size": self.best_buy_size,
            "sell_price": self.best_sell_price,
            "sell_size": self.best_sell_size,
        }
        self.market_service.l1_update(payload)

    # matcher IS responsible for the price
    def emit_fill(self, a, b):
        # any calculations needing last price use self.price here
        trade_price = ((a.price +b.price)/2)
        trade_size = 1
        self.last_price = trade_price
        self.last_size = trade_size


        # emit l2
        payload = {
            "a": str(a), # dont look
            "b": str(b), # lol
            "price": self.last_price
        }
        self.market_service.l2_update(MarketMessage.FILL_ORDER, payload)
        self.update_l1()
    
    def try_amend(self, order):
        a = self.buys
        if order.side == OrderSide.SELL:
            a = self.sells
        
        found = None
        for (i, book_order) in enumerate(a):
            if order == book_order:
                found = i
                break
        if found is not None:
            a[found] = order
            self.market_service.l2_update(MarketMessage.AMEND_ORDER, f" -> order {order}")
            self.update_l1()
        else:
            self.market_service.client_update(MarketMessage.AMEND_ORDER, f"NOAMEND -> order {order.oid}")
                
    def try_cancel(self, oid):
        try:
            self.buys.remove(oid)
            self.market_service.l2_update(MarketMessage.CANCEL_ORDER, f" -> order {oid}")
            self.update_l1()
            return
        except ValueError:
            pass
        try:
            self.sells.remove(oid)
            self.market_service.l2_update(MarketMessage.CANCEL_ORDER, f" -> order {oid}")
            self.update_l1()
            return
        except ValueError:
            pass
        self.market_service.client_update(MarketMessage.CANCEL_ORDER, f"NOCANCEL -> order {oid}")
    
    def match(self, order):
        # we fucked this before
        # match should have opportunity to match before it goes on the book
        # (and enable FOK)

        a = self.buys
        b = self.sells

        if order.side == OrderSide.SELL:
            b = self.buys
            a = self.sells
            
        if len(b) > 0: # FILL
            self.emit_fill(b.popleft(), order)
        else: # NEW ORDER
            a.append(order)
            self.market_service.l2_update(MarketMessage.NEW_ORDER, f"NEW -> {order}")
            self.update_l1()

    
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
    def __init__(self, exchange, market_service):
        self.__exchange = exchange # this would be a exchange connection object
        self.market_service = market_service
        self.market_service.register_client(self)

        # TODO next
        # consume messages in here to "forward" to correct client
        # endpoint for requesting L1 data for a particular client
            # and an option to subscribe to it

    def receive_message(self, msg):
        print(Colors.BLUE, "GATEWAY", Colors.RESET, msg)

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
gateway = SimpleGateway(exchange, market_service)
gateway.new_order("STI", 1, 10)
gateway.new_order("STI", 1, 15)
gateway.new_order("STI", 2, 12)
gateway.new_order("STI", 1, 1)
gateway.cancel_order(1)
gateway.cancel_order(2)

order = gateway.new_order("STI", 1, 10)
order.oid = 3
gateway.amend_order(order)

#socket_gateway = SocketGateway(exchange)

# gateway should check message is valid and create relevant objects
# exchange should validate objects for business rules
# matcher is dumb and just follows all instructions

# this time sam is not hung up on fancy architecture and tom is not hung
# up on making it perfectly realistic
# sam was thinking about how complexity killed his original version
#  we're being better at focusing on keeping things as easy to run
#  before getting bogged down in complexity