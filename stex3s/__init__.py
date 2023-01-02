import socket
import uuid
import time
from collections import deque
from enum import Enum

class ExecutionReport:
    @staticmethod
    def for_book():
        return {
            "status": "open"
        }

    @staticmethod
    def for_fill():
        return {
            "status": "filled"
        }

    @staticmethod
    def for_cancel():
        return {
            "status": "cancelled"
        }

class Product:
    def __init__(self, symbol) -> None:
        self.symbol = symbol

class OrderSide(Enum):
    BUY = 1
    SELL = 2 # WHAT

class MarketMessage(Enum):
    NEW_ORDER = 1
    FILL_ORDER = 2
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
    def __init__(self, product: Product, order_side: OrderSide, price, client_id, timestamp):
        self.product = product
        self.side = order_side
        self.oid = 0
        self.price = price
        self.client_id = client_id
        self.receive_ts = timestamp
        # keep this REALLY simple and forget about qty and price for now

    @staticmethod
    def from_garbage(symbol, side, price, client_id):
        return Order(Product(symbol), OrderSide(side), price, client_id, time.time_ns())

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
        if event_type == MarketMessage.NEW_ORDER:
            self.client_update(event_type, payload)
        #print(msg)
        payload["client_id"] = "*"
        self.send_message(payload)
        #self.send_message(msg)

        ##if event_type == MarketMessage.FILL_ORDER:
        #    # changes: last_price, last_size, buy/sell prices/sizes
        #    self.update_price(payload["last_price"])

    def client_update(self, event_type,  payload):
        #msg = f"{Colors.GREEN}[CL]{Colors.RESET} {event_type} {payload}"
        self.send_message(payload)

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
    
    def try_cancel(self, client_id, oid):
        try:
            self.buys.remove(oid)
            self.market_service.l2_update(MarketMessage.CANCEL_ORDER, {"client_id": client_id, "oid": oid})
            self.update_l1()
            return
        except ValueError:
            pass
        try:
            self.sells.remove(oid)
            self.market_service.l2_update(MarketMessage.CANCEL_ORDER, {"client_id": client_id, "oid": oid})
            self.update_l1()
            return
        except ValueError:
            pass

        payload = {
            "type": "NOCANCEL",
            "client_id": client_id,
            "order": oid,
        }
        self.market_service.client_update(MarketMessage.CANCEL_ORDER, payload)
    
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
            payload = {
                "client_id": order.client_id,
                "order": order,
            }
            self.market_service.l2_update(MarketMessage.NEW_ORDER, payload) # lol
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

    def cancel_order(self, client_id, oid):
        self.matcher.try_cancel(client_id, oid)


class SimpleGateway:
    def __init__(self, number, exchange, market_service):
        self.number = number
        self.__exchange = exchange # this would be a exchange connection object
        self.market_service = market_service
        self.market_service.register_client(self)
        self.connections = {}

        # TODO next
        # consume messages in here to "forward" to correct client
        # endpoint for requesting L1 data for a particular client
            # and an option to subscribe to it

    def register_client(self, client):
        self.connections[client.client_id] = client

    def receive_message(self, msg):
        if msg.get("client_id") in self.connections:
            self.connections[msg["client_id"]].receive_message(msg)
        elif msg.get("client_id") == "*":
            for _, connection in self.connections.items():
                connection.receive_message(msg)
        else:
            print(Colors.BLUE, f"GATEWAY {self.number} DISCARD", Colors.RESET, msg)


    def new_order(self, product, side, price, client_id):
        order = Order.from_garbage(product, side, price, client_id)
        self.__exchange.new_order(order)
        return order # does not necessarily imply order has been accepted

    def cancel_order(self, client_id, oid):
        self.__exchange.cancel_order(client_id, oid)


class SimpleClient:
    def __init__(self):
        self.client_id = uuid.uuid4()

    def receive_message(self, msg):
        print(Colors.BLUE, f"CLIENT {self.client_id}", Colors.RESET, msg)


market_service = SimpleMarketData()
exchange = SimpleExchange("STI", market_service)
gateway = SimpleGateway(1, exchange, market_service)

client = SimpleClient()
gateway.register_client(client)

client2 = SimpleClient()
gateway.register_client(client2)

CLIENT_ID = client.client_id
gateway.new_order("STI", 1, 10, CLIENT_ID)
gateway.new_order("STI", 1, 15, CLIENT_ID)
gateway.new_order("STI", 2, 12, CLIENT_ID)
gateway.new_order("STI", 1, 1, CLIENT_ID)
gateway.cancel_order(CLIENT_ID, 1)
gateway.cancel_order(CLIENT_ID, 2)

#socket_gateway = SocketGateway(exchange)

# gateway should check message is valid and create relevant objects
# exchange should validate objects for business rules
# matcher is dumb and just follows all instructions

# this time sam is not hung up on fancy architecture and tom is not hung
# up on making it perfectly realistic
# sam was thinking about how complexity killed his original version
#  we're being better at focusing on keeping things as easy to run
#  before getting bogged down in complexity