import { Greeter, formatGreeting } from "./greeter";
export { Cache } from "./Cache";
import Logger from "./Logger";
export { Logger };
export { Button } from "./Button";
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { helper } = require("./legacy");
export { helper };

const greeter = new Greeter("Hello,");
const g = greeter.greet("World");
console.log(formatGreeting(g));

const gs = greeter.greetAll(["Alice", "Bob"]);
gs.forEach((item) => console.log(formatGreeting(item)));

const logger = new Logger("main");
logger.log("done");
