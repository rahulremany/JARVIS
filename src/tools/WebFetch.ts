import { fetch } from 'undici';
import { logger } from '../utils/logging.js';
import { timeout } from '../utils/timing.js';

export interface WebFetchOptions {
  timeout?: number;
  maxRetries?: number;
  userAgent?: string;
}

export interface WebFetchResult {
  url: string;
  status: number;
  content: string;
  contentType: string;
  timestamp: number;
  duration: number;
}

export class WebFetch {
  private readonly defaultOptions: Required<WebFetchOptions> = {
    timeout: 10000,
    maxRetries: 3,
    userAgent: 'JARVIS/1.0.0 (Local AI Assistant)'
  };

  async fetchUrl(url: string, options: WebFetchOptions = {}): Promise<WebFetchResult> {
    const opts = { ...this.defaultOptions, ...options };
    const startTime = performance.now();
    
    let lastError: Error | null = null;
    
    for (let attempt = 1; attempt <= opts.maxRetries; attempt++) {
      try {
        logger.debug(`Fetching ${url} (attempt ${attempt}/${opts.maxRetries})`);
        
        const response = await timeout(
          fetch(url, {
            headers: {
              'User-Agent': opts.userAgent,
              'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
              'Accept-Language': 'en-US,en;q=0.5',
              'Accept-Encoding': 'gzip, deflate',
              'DNT': '1',
              'Connection': 'keep-alive',
              'Upgrade-Insecure-Requests': '1'
            }
          }),
          opts.timeout
        );

        const content = await response.text();
        const duration = performance.now() - startTime;
        
        const result: WebFetchResult = {
          url,
          status: response.status,
          content,
          contentType: response.headers.get('content-type') || 'unknown',
          timestamp: Date.now(),
          duration
        };

        if (response.ok) {
          logger.debug(`Successfully fetched ${url} (${content.length} chars, ${duration.toFixed(1)}ms)`);
          return result;
        } else {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
      } catch (error) {
        lastError = error as Error;
        logger.warn(`Fetch attempt ${attempt} failed for ${url}:`, error);
        
        if (attempt < opts.maxRetries) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
          logger.debug(`Retrying in ${delay}ms...`);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }
    
    const duration = performance.now() - startTime;
    logger.error(`Failed to fetch ${url} after ${opts.maxRetries} attempts`);
    
    throw new Error(`Failed to fetch ${url}: ${lastError?.message || 'Unknown error'}`);
  }

  async fetchMultiple(urls: string[], options: WebFetchOptions = {}): Promise<WebFetchResult[]> {
    logger.info(`Fetching ${urls.length} URLs in parallel`);
    
    const promises = urls.map(url => 
      this.fetchUrl(url, options).catch(error => {
        logger.warn(`Failed to fetch ${url}:`, error);
        return null;
      })
    );
    
    const results = await Promise.all(promises);
    const successful = results.filter((result): result is WebFetchResult => result !== null);
    
    logger.info(`Successfully fetched ${successful.length}/${urls.length} URLs`);
    return successful;
  }

  async searchGoogle(query: string, options: WebFetchOptions = {}): Promise<WebFetchResult[]> {
    // Note: This is a placeholder for actual Google search integration
    // In production, you'd want to use Google Custom Search API or similar
    logger.warn('Google search not implemented - using placeholder');
    
    const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
    
    try {
      const result = await this.fetchUrl(searchUrl, options);
      return [result];
    } catch (error) {
      logger.error('Google search failed:', error);
      return [];
    }
  }

  extractText(html: string): string {
    // Basic HTML text extraction (in production, you'd want a proper HTML parser)
    return html
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
      .replace(/<[^>]*>/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  extractTitle(html: string): string {
    const titleMatch = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    return titleMatch ? titleMatch[1].trim() : 'No title';
  }

  isValidUrl(url: string): boolean {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }
}
