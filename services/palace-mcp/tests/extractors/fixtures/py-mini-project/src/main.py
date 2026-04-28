"""Entry point — usage site exercising all public symbols."""

from pymini.greeter import Greeter, format_greeting

greeter = Greeter("Hello,")
g = greeter.greet("World")
print(format_greeting(g))

gs = greeter.greet_all(["Alice", "Bob"])
for item in gs:
    print(format_greeting(item))
