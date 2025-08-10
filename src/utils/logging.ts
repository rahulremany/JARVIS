export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LatencyLog {
  engine: string;
  model_id: string;
  params: Record<string, any>;
  prompt_chars: number;
  session_id: string;
  first_token_ms: number;
  total_ms: number;
  tokens_out: number;
  route: string;
  timestamp: string;
}

class Logger {
  private level: LogLevel = 'info';
  private latencyLogs: LatencyLog[] = [];
  private sampleRate = 1; // In prod, set to 0.05 for 1/20 sampling

  constructor() {
    this.level = 'debug'; // Temporarily set to debug for troubleshooting
    this.latencyLogs = [];
    this.sampleRate = 1;
  }

  setLevel(level: LogLevel) {
    this.level = level;
  }

  setSampleRate(rate: number) {
    this.sampleRate = rate;
  }

  private shouldLog(level: LogLevel): boolean {
    const levels: LogLevel[] = ['debug', 'info', 'warn', 'error'];
    return levels.indexOf(level) >= levels.indexOf(this.level);
  }

  private formatMessage(level: LogLevel, message: string, ...args: any[]): string {
    const timestamp = new Date().toISOString();
    const prefix = `[JARVIS] ${level.toUpperCase()}`;
    
    if (args.length > 0) {
      const formattedArgs = args.map(arg => 
        typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
      ).join(' ');
      return `${prefix} ${message} ${formattedArgs}`;
    }
    
    return `${prefix} ${message}`;
  }

  debug(message: string, ...args: any[]) {
    if (this.shouldLog('debug')) {
      console.log(this.formatMessage('debug', message, ...args));
    }
  }

  info(message: string, ...args: any[]) {
    if (this.shouldLog('info')) {
      console.log(this.formatMessage('info', message, ...args));
    }
  }

  warn(message: string, ...args: any[]) {
    if (this.shouldLog('warn')) {
      console.warn(this.formatMessage('warn', message, ...args));
    }
  }

  error(message: string, ...args: any[]) {
    if (this.shouldLog('error')) {
      console.error(this.formatMessage('error', message, ...args));
    }
  }

  logLatency(log: Omit<LatencyLog, 'timestamp'>) {
    // Sample in production
    if (Math.random() > this.sampleRate) return;

    const completeLog: LatencyLog = {
      ...log,
      timestamp: new Date().toISOString()
    };

    this.latencyLogs.push(completeLog);

    if (this.latencyLogs.length > 100) {
      this.latencyLogs = this.latencyLogs.slice(-100);
    }

    console.log('[JARVIS] 📊 LATENCY:', JSON.stringify(completeLog));
  }

  getLatencyLogs(): LatencyLog[] {
    return [...this.latencyLogs];
  }

  getLatencyStats() {
    if (this.latencyLogs.length === 0) {
      return {
        count: 0,
        avg_first_token_ms: 0,
        avg_total_ms: 0,
        avg_tokens_out: 0
      };
    }

    const firstTokenTimes = this.latencyLogs.map(log => log.first_token_ms);
    const totalTimes = this.latencyLogs.map(log => log.total_ms);
    const tokensOut = this.latencyLogs.map(log => log.tokens_out);

    return {
      count: this.latencyLogs.length,
      avg_first_token_ms: Math.round(firstTokenTimes.reduce((a, b) => a + b, 0) / firstTokenTimes.length),
      avg_total_ms: Math.round(totalTimes.reduce((a, b) => a + b, 0) / totalTimes.length),
      avg_tokens_out: Math.round(tokensOut.reduce((a, b) => a + b, 0) / tokensOut.length)
    };
  }
}

export const logger = new Logger();
