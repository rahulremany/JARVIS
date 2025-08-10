import { Router, type RouteClass } from '../src/router/Router.js';

describe('Router', () => {
  let router: Router;

  beforeEach(() => {
    router = new Router();
  });

  describe('Direct Command Classification', () => {
    it('should classify device commands as direct_command', () => {
      const testCases = [
        'turn on the lights',
        'play music',
        'lock the doors',
        'set temperature to 72',
        'dim the living room lights',
        'arm security system'
      ];

      testCases.forEach(input => {
        const result = router.classify(input);
        expect(result.class).toBe('direct_command');
        expect(result.confidence).toBeGreaterThan(0.8);
      });
    });
  });

  describe('Trivial Query Classification', () => {
    it('should classify simple questions as trivial', () => {
      const testCases = [
        'what is 2+2',
        'hi',
        'hello',
        'what time is it',
        'who is the president',
        'what\'s the weather'
      ];

      testCases.forEach(input => {
        const result = router.classify(input);
        expect(['trivial', 'direct_command']).toContain(result.class);
      });
    });

    it('should classify calculations as trivial', () => {
      const mathQuestions = [
        'what is 15 + 27',
        'calculate 100 / 4',
        'compute 5 * 8'
      ];

      mathQuestions.forEach(input => {
        const result = router.classify(input);
        expect(result.class).toBe('trivial');
        expect(result.reasoning).toContain('calculation');
      });
    });
  });

  describe('Normal Query Classification', () => {
    it('should classify conversational queries as normal', () => {
      const testCases = [
        'how are you doing today',
        'can you help me with something',
        'what do you think about artificial intelligence',
        'tell me a joke',
        'explain the concept of gravity'
      ];

      testCases.forEach(input => {
        const result = router.classify(input);
        expect(['normal', 'trivial']).toContain(result.class);
      });
    });
  });

  describe('Hard Query Classification', () => {
    it('should classify complex queries as hard', () => {
      const testCases = [
        'write a comprehensive analysis of machine learning algorithms',
        'create a detailed project plan for building a web application',
        'architect a multi-step solution for data processing',
        'provide a full design for a distributed system',
        'research the latest trends in quantum computing and write a report'
      ];

      testCases.forEach(input => {
        const result = router.classify(input);
        expect(result.class).toBe('hard');
        expect(result.confidence).toBeGreaterThan(0.7);
      });
    });

    it('should classify complex technical questions as hard', () => {
      const testCases = [
        'how do I implement a complex algorithm for graph traversal',
        'debug this multi-threaded application with race conditions',
        'design a scalable architecture for microservices'
      ];

      testCases.forEach(input => {
        const result = router.classify(input);
        expect(['hard', 'normal']).toContain(result.class);
      });
    });

    it('should classify long inputs as hard', () => {
      const longInput = 'This is a very long query that contains many words and complex ideas that would require significant processing and a detailed response covering multiple aspects of the topic at hand.'.repeat(2);
      
      const result = router.classify(longInput);
      expect(result.class).toBe('hard');
      expect(result.reasoning).toContain('Long input');
    });
  });

  describe('Engine Tier Mapping', () => {
    it('should map route classes to correct engine tiers', () => {
      expect(router.getEngineTier('direct_command')).toBe('router');
      expect(router.getEngineTier('trivial')).toBe('router');
      expect(router.getEngineTier('normal')).toBe('primary');
      expect(router.getEngineTier('hard')).toBe('heavy');
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty input', () => {
      const result = router.classify('');
      expect(result.class).toBe('trivial');
    });

    it('should handle very short input', () => {
      const result = router.classify('hi');
      expect(result.class).toBe('trivial');
    });

    it('should handle input with only spaces', () => {
      const result = router.classify('   ');
      expect(result.class).toBe('trivial');
    });

    it('should handle mixed case input', () => {
      const result = router.classify('TURN ON THE LIGHTS');
      expect(result.class).toBe('direct_command');
    });
  });

  describe('Confidence Scoring', () => {
    it('should return confidence scores between 0 and 1', () => {
      const testInputs = [
        'hello',
        'turn on lights',
        'explain quantum physics',
        'write a comprehensive analysis'
      ];

      testInputs.forEach(input => {
        const result = router.classify(input);
        expect(result.confidence).toBeGreaterThanOrEqual(0);
        expect(result.confidence).toBeLessThanOrEqual(1);
      });
    });

    it('should have higher confidence for clear classifications', () => {
      const clearDevice = router.classify('turn on the lights');
      const clearTrivial = router.classify('what is 2+2');
      const clearHard = router.classify('write a comprehensive multi-step analysis');

      expect(clearDevice.confidence).toBeGreaterThan(0.8);
      expect(clearTrivial.confidence).toBeGreaterThan(0.7);
      expect(clearHard.confidence).toBeGreaterThan(0.8);
    });
  });

  describe('Reasoning', () => {
    it('should provide reasoning for classifications', () => {
      const testCases = [
        'turn on lights',
        'hello',
        'explain AI in detail with examples and comparisons'
      ];

      testCases.forEach(input => {
        const result = router.classify(input);
        expect(result.reasoning).toBeDefined();
        expect(typeof result.reasoning).toBe('string');
        expect(result.reasoning.length).toBeGreaterThan(0);
      });
    });
  });
});
