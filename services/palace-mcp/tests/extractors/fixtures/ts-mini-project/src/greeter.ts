export interface Greeting {
  message: string;
  recipient: string;
}

export class Greeter {
  private prefix: string;

  constructor(prefix: string) {
    this.prefix = prefix;
  }

  greet(name: string): Greeting {
    return {
      message: `${this.prefix} ${name}`,
      recipient: name,
    };
  }

  greetAll(names: string[]): Greeting[] {
    return names.map((n) => this.greet(n));
  }
}

export function formatGreeting(g: Greeting): string {
  return `[${g.recipient}] ${g.message}`;
}
