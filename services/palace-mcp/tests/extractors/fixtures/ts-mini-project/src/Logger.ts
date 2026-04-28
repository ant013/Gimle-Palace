export default class Logger {
  private name: string;

  constructor(name: string) {
    this.name = name;
  }

  log(message: string): void {
    console.log(`[${this.name}] ${message}`);
  }
}
