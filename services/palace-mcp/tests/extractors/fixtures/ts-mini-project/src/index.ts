import { Greeter, formatGreeting } from "./greeter";

const greeter = new Greeter("Hello,");
const g = greeter.greet("World");
console.log(formatGreeting(g));

const gs = greeter.greetAll(["Alice", "Bob"]);
gs.forEach((item) => console.log(formatGreeting(item)));
