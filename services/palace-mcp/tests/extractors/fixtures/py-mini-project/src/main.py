"""Entry point — usage site exercising all public symbols."""

from pymini.cache import Cache
from pymini.greeter import Greeter, format_greeting
from pymini.legacy import Config
from pymini.logger import Logger

greeter = Greeter("Hello,")
g = greeter.greet("World")
print(format_greeting(g))

gs = greeter.greet_all(["Alice", "Bob"])
for item in gs:
    print(format_greeting(item))

cache: Cache[str, int] = Cache()
cache.put("x", 1)

logger = Logger("main")
logger.log("started")

config = Config(name="test", debug=True)
