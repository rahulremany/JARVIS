import { logger } from '../utils/logging.js';

export interface SessionContext {
  id: string;
  messages: Array<{
    role: 'system' | 'user' | 'assistant';
    content: string;
    timestamp: number;
  }>;
  createdAt: number;
  lastAccessedAt: number;
}

export class SessionManager {
  private sessions: Map<string, SessionContext> = new Map();
  private readonly maxSessions = 100;
  private readonly sessionTimeoutMs = 30 * 60 * 1000; // 30 minutes

  private readonly systemPrompt = `You are JARVIS, a personal AI assistant. You are helpful, concise, and professional.
Never reference Tony Stark, Iron Man, Marvel characters, or fictional scenarios. You assist real users with real tasks.
Keep responses brief and focused. Remember user preferences and names when told.`;

  getOrCreate(sessionId: string): SessionContext {
    let session = this.sessions.get(sessionId);
    
    if (!session) {
      session = {
        id: sessionId,
        messages: [
          {
            role: 'system',
            content: this.systemPrompt,
            timestamp: Date.now()
          }
        ],
        createdAt: Date.now(),
        lastAccessedAt: Date.now()
      };
      
      this.sessions.set(sessionId, session);
      logger.debug(`Created new session: ${sessionId}`);
      
      // Cleanup old sessions if we're at the limit
      this.cleanup();
    } else {
      session.lastAccessedAt = Date.now();
    }
    
    return session;
  }

  appendUser(sessionId: string, content: string): SessionContext {
    const session = this.getOrCreate(sessionId);
    
    session.messages.push({
      role: 'user',
      content,
      timestamp: Date.now()
    });
    
    return session;
  }

  appendAssistant(sessionId: string, content: string): SessionContext {
    const session = this.getOrCreate(sessionId);
    
    session.messages.push({
      role: 'assistant',
      content,
      timestamp: Date.now()
    });
    
    return session;
  }

  getMessages(sessionId: string): SessionContext['messages'] {
    const session = this.getOrCreate(sessionId);
    return session.messages;
  }

  reset(sessionId: string): void {
    this.sessions.delete(sessionId);
    logger.debug(`Reset session: ${sessionId}`);
  }

  private cleanup(): void {
    if (this.sessions.size <= this.maxSessions) return;
    
    const now = Date.now();
    const sessionsToDelete: string[] = [];
    
    // Find expired sessions
    for (const [id, session] of this.sessions) {
      if (now - session.lastAccessedAt > this.sessionTimeoutMs) {
        sessionsToDelete.push(id);
      }
    }
    
    // If we still have too many, delete the oldest
    if (this.sessions.size - sessionsToDelete.length > this.maxSessions) {
      const sortedSessions = Array.from(this.sessions.entries())
        .sort((a, b) => a[1].lastAccessedAt - b[1].lastAccessedAt);
      
      const excess = this.sessions.size - sessionsToDelete.length - this.maxSessions;
      for (let i = 0; i < excess; i++) {
        sessionsToDelete.push(sortedSessions[i][0]);
      }
    }
    
    // Delete sessions
    sessionsToDelete.forEach(id => {
      this.sessions.delete(id);
      logger.debug(`Cleaned up session: ${id}`);
    });
  }

  getSessions(): string[] {
    return Array.from(this.sessions.keys());
  }

  getSessionCount(): number {
    return this.sessions.size;
  }
}

// Global session storage for llama.cpp contexts and chats
const llamaSessions = new Map<string, { context: any; chat: any }>();

// Get or create persistent context & chat for a session
export async function getSession<TCtx, TChat>(
  sessionId: string,
  createCtx: () => Promise<TCtx> | TCtx,
  createChat: (ctx: TCtx) => Promise<TChat> | TChat
): Promise<{ context: TCtx; chat: TChat }> {
  if (llamaSessions.has(sessionId)) {
    const existing = llamaSessions.get(sessionId)!;
    return { context: existing.context, chat: existing.chat };
  }

  logger.debug(`Creating new llama session: ${sessionId}`);
  const context = await createCtx();
  const chat = await createChat(context);
  
  llamaSessions.set(sessionId, { context, chat });
  
  // Cleanup old sessions if we have too many
  if (llamaSessions.size > 50) {
    const oldestKey = llamaSessions.keys().next().value;
    if (oldestKey) {
      llamaSessions.delete(oldestKey);
      logger.debug(`Cleaned up old llama session: ${oldestKey}`);
    }
  }
  
  return { context, chat };
}
