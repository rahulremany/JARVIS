import { logger } from '../utils/logging.js';
import { DeviceActions } from '../tools/DeviceActions.js';

export type RouteClass = 'direct_command' | 'trivial' | 'normal' | 'hard';

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
