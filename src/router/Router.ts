import { logger } from '../utils/logging.js';
import { DeviceActions } from '../tools/DeviceActions.js';

export type RouteClass = 'direct_command' | 'trivial' | 'normal' | 'hard';

// Which specialist model in the local mesh should handle this request.
// Orthogonal to RouteClass: a request can be "hard" difficulty and still be
// a "coder" facet, or "trivial" and still be a "planner" facet.
export type Facet = 'planner' | 'coder' | 'fast';

export interface RouteResult {
  class: RouteClass;
  confidence: number;
  reasoning: string;
  deviceCommand?: any;
}

export class Router {
  private deviceActions = new DeviceActions();
  
  // Keywords that indicate hard/complex queries
  private hardKeywords = [
    'multi-step', 'full design', 'long plan', 'refactor large file',
    'architect', 'comprehensive', 'detailed analysis', 'compare multiple',
    'research', 'write a report', 'create a document', 'plan a project'
  ];

  // Keywords that indicate direct device commands
  private directCommandKeywords = [
    'turn on', 'turn off', 'play music', 'stop music', 'lock doors',
    'unlock doors', 'set temperature', 'dim lights', 'brighten lights',
    'arm security', 'disarm security'
  ];

  classify(input: string): RouteResult {
    const lower = input.toLowerCase().trim();
    
    logger.debug('Classifying input:', input);

    // Check for direct device commands first
    const deviceCommand = this.deviceActions.parseCommand(input);
    if (deviceCommand) {
      return {
        class: 'direct_command',
        confidence: 0.95,
        reasoning: 'Detected device/automation command',
        deviceCommand
      };
    }

    // Check for explicit direct command patterns
    const hasDirectKeywords = this.directCommandKeywords.some(keyword => 
      lower.includes(keyword)
    );
    
    if (hasDirectKeywords) {
      return {
        class: 'direct_command',
        confidence: 0.9,
        reasoning: 'Contains direct command keywords'
      };
    }

    // Check for hard/complex queries
    const hasHardKeywords = this.hardKeywords.some(keyword => 
      lower.includes(keyword)
    );
    
    if (hasHardKeywords) {
      return {
        class: 'hard',
        confidence: 0.9,
        reasoning: 'Contains complexity keywords indicating hard query'
      };
    }

    // Length-based classification
    if (input.length < 10) {
      return {
        class: 'trivial',
        confidence: 0.7,
        reasoning: 'Very short input likely trivial'
      };
    }

    if (input.length > 200) {
      return {
        class: 'hard',
        confidence: 0.8,
        reasoning: 'Long input suggests complex query'
      };
    }

    // Question complexity analysis
    const questionWords = ['what', 'why', 'how', 'when', 'where', 'who'];
    const hasQuestionWords = questionWords.some(word => lower.includes(word));
    
    if (hasQuestionWords) {
      // Simple factual questions
      if (lower.match(/^(what is|what's|who is|who's|when is|when's|where is|where's)/)) {
        return {
          class: 'trivial',
          confidence: 0.8,
          reasoning: 'Simple factual question'
        };
      }
      
      // Complex how/why questions
      if (lower.includes('how') && (lower.includes('work') || lower.includes('implement') || lower.includes('design'))) {
        return {
          class: 'hard',
          confidence: 0.8,
          reasoning: 'Complex how-to or explanation question'
        };
      }
    }

    // Coding/technical content
    if (lower.includes('code') || lower.includes('function') || lower.includes('class') || 
        lower.includes('algorithm') || lower.includes('implement') || lower.includes('debug')) {
      
      if (lower.includes('simple') || lower.includes('basic') || lower.includes('quick')) {
        return {
          class: 'normal',
          confidence: 0.7,
          reasoning: 'Simple technical query'
        };
      }
      
      return {
        class: 'hard',
        confidence: 0.8,
        reasoning: 'Technical/coding query'
      };
    }

    // Math/calculation
    if (lower.match(/\d+/) && (lower.includes('calculate') || lower.includes('compute') || 
        lower.includes('+') || lower.includes('-') || lower.includes('*') || lower.includes('/'))) {
      return {
        class: 'trivial',
        confidence: 0.8,
        reasoning: 'Simple calculation'
      };
    }

    // Default to normal for most conversational queries
    return {
      class: 'normal',
      confidence: 0.6,
      reasoning: 'Default classification for conversational input'
    };
  }

  // Keywords that indicate a coding/debugging task -> the coder facet
  private coderKeywords = [
    'code', 'function', 'class', 'algorithm', 'implement', 'debug',
    'refactor', 'unit test', 'stack trace', 'syntax error', 'compile',
    'regex', 'script', 'boilerplate', 'git commit', 'api endpoint'
  ];

  // Keywords that indicate planning/brainstorming -> the planner facet
  private plannerKeywords = [
    'plan', 'outline', 'brainstorm', 'kanban', 'roadmap', 'folder structure',
    'break down', 'steps to', 'architecture', 'design doc', 'project goal',
    'compare', 'pros and cons', 'strategy'
  ];

  // Classify which mesh specialist should serve this request. Cheap keyword
  // pass by design -- routing itself must never cost a model invocation.
  classifyFacet(input: string): Facet {
    const lower = input.toLowerCase();

    if (this.coderKeywords.some(k => lower.includes(k))) {
      return 'coder';
    }
    if (this.plannerKeywords.some(k => lower.includes(k))) {
      return 'planner';
    }
    // Short, throwaway requests (autocomplete, summarize-this, quick lookup)
    // default to the always-loaded fast-utility model.
    if (input.length < 120) {
      return 'fast';
    }
    return 'planner';
  }

  // Get engine tier based on route class
  getEngineTier(routeClass: RouteClass): 'router' | 'primary' | 'heavy' {
    switch (routeClass) {
      case 'direct_command':
      case 'trivial':
        return 'router';
      case 'normal':
        return 'primary';
      case 'hard':
        return 'heavy';
      default:
        return 'primary';
    }
  }
}
