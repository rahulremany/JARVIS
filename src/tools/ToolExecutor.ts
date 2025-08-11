// src/tools/ToolExecutor.ts
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import { logger } from '../utils/logging.js';

const execAsync = promisify(exec);

export interface ToolCall {
  action: string;
  params: Record<string, any>;
  confidence?: number;
}

export interface ToolResult {
  success: boolean;
  output: string;
  action: string;
  error?: string;
}

export class ToolExecutor {
  private readonly safeCommands = new Set([
    'ls', 'pwd', 'date', 'whoami', 'uptime', 'df', 'free',
    'ps', 'top', 'which', 'echo', 'cat', 'head', 'tail'
  ]);

  /**
   * Parse tool calls from LLM output
   */
  parseToolCall(text: string): ToolCall | null {
    try {
      const jsonMatch = text.match(/\{[^}]*"action"[^}]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
      return null;
    } catch (error) {
      logger.error('Failed to parse tool call:', error);
      return null;
    }
  }

  /**
   * Execute a tool call
   */
  async execute(toolCall: ToolCall): Promise<ToolResult> {
    try {
      switch (toolCall.action) {
        case 'get_time':
          return this.getCurrentTime();
        
        case 'open_app':
          return await this.openApp(toolCall.params.name);
        
        case 'type_text':
          return await this.typeText(toolCall.params.text);
        
        case 'press_keys':
          return await this.pressKeys(toolCall.params.keys);
        
        case 'read_screen':
          return await this.readScreen();
        
        case 'run_shell':
          return await this.runShellCommand(toolCall.params.command);
        
        case 'web_search':
          return await this.webSearch(toolCall.params.query);
        
        case 'web_search_and_open':
          return await this.webSearchAndOpen(toolCall.params.query);
        
        case 'open_and_type':
          return await this.openAndType(toolCall.params.app, toolCall.params.text);
        
        case 'click_element':
          return await this.clickElement(toolCall.params.target);
        
        case 'type_in_field':
          return await this.typeInField(toolCall.params.text, toolCall.params.field);
        
        case 'scroll':
          return await this.scroll(toolCall.params.direction);
        
        default:
          return {
            success: false,
            output: `Unknown action: ${toolCall.action}`,
            action: toolCall.action,
            error: 'Action not supported'
          };
      }
    } catch (error) {
      logger.error(`Tool execution error for ${toolCall.action}:`, error);
      return {
        success: false,
        output: `Failed to execute ${toolCall.action}`,
        action: toolCall.action,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Get current time and date
   */
  getCurrentTime(): ToolResult {
    const now = new Date();
    
    const timeString = now.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZoneName: 'short'
    });
    
    const dateString = now.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
    
    return {
      success: true,
      output: `Current time: ${timeString} on ${dateString}`,
      action: 'get_time'
    };
  }

  /**
   * Open macOS applications
   */
  async openApp(appName: string): Promise<ToolResult> {
    try {
      const sanitizedName = appName.replace(/[^a-zA-Z0-9\s\-_]/g, '').trim();
      
      if (!sanitizedName) {
        return {
          success: false,
          output: 'Invalid app name provided',
          action: 'open_app',
          error: 'Empty or invalid app name'
        };
      }

      const commonMappings: Record<string, string> = {
        'browser': 'Safari',
        'chrome': 'Google Chrome',
        'firefox': 'Firefox',
        'safari': 'Safari',
        'terminal': 'Terminal',
        'finder': 'Finder',
        'vscode': 'Visual Studio Code',
        'code': 'Visual Studio Code',
        'cursor': 'Cursor',
        'notes': 'Notes',
        'calculator': 'Calculator',
        'mail': 'Mail'
      };

      const blockedApps = ['orion'];
      
      if (blockedApps.includes(sanitizedName.toLowerCase())) {
        return {
          success: false,
          output: `${sanitizedName} blocks programmatic opening for security reasons. Please open it manually.`,
          action: 'open_app',
          error: 'App blocks automation'
        };
      }

      const targetApp = commonMappings[sanitizedName.toLowerCase()] || sanitizedName;
      await execAsync(`open -a "${targetApp}"`);
      
      return {
        success: true,
        output: `Opened ${targetApp}`,
        action: 'open_app'
      };
      
    } catch (error) {
      return {
        success: false,
        output: `Failed to open ${appName}`,
        action: 'open_app',
        error: error instanceof Error ? error.message : 'App launch failed'
      };
    }
  }

  /**
   * Type text at current cursor position
   */
  async typeText(text: string): Promise<ToolResult> {
    try {
      const escapedText = text.replace(/"/g, '\\"').replace(/\\/g, '\\\\');
      
      const script = `
        tell application "System Events"
          keystroke "${escapedText}"
        end tell
      `;
      
      await execAsync(`osascript -e '${script}'`);
      
      return {
        success: true,
        output: `Typed: "${text}"`,
        action: 'type_text'
      };
    } catch (error) {
      return {
        success: false,
        output: `Failed to type text`,
        action: 'type_text',
        error: error instanceof Error ? error.message : 'Typing failed'
      };
    }
  }

  /**
   * Press key combinations
   */
  async pressKeys(keys: string[]): Promise<ToolResult> {
    try {
      const keyMappings: Record<string, string> = {
        'cmd': 'command',
        'ctrl': 'control',
        'alt': 'option',
        'enter': 'return',
        'return': 'return',
        'esc': 'escape',
        'space': 'space',
        'tab': 'tab'
      };
      
      if (keys.length === 1 && keys[0].toLowerCase() === 'return') {
        const script = `
          tell application "System Events"
            keystroke return
          end tell
        `;
        await execAsync(`osascript -e '${script}'`);
      } else if (keys.length === 1) {
        const key = keyMappings[keys[0].toLowerCase()] || keys[0];
        const script = `
          tell application "System Events"
            keystroke "${key}"
          end tell
        `;
        await execAsync(`osascript -e '${script}'`);
      } else {
        const mappedKeys = keys.map(key => keyMappings[key.toLowerCase()] || key);
        const keyString = mappedKeys.join(' down, ') + ' down';
        
        const script = `
          tell application "System Events"
            key down {${keyString}}
          end tell
        `;
        await execAsync(`osascript -e '${script}'`);
      }
      
      return {
        success: true,
        output: `Pressed keys: ${keys.join(' + ')}`,
        action: 'press_keys'
      };
    } catch (error) {
      return {
        success: false,
        output: `Failed to press keys`,
        action: 'press_keys',
        error: error instanceof Error ? error.message : 'Key press failed'
      };
    }
  }

  /**
   * Read active window and screen context with AI Vision
   */
  async readScreen(): Promise<ToolResult> {
    try {
      const { stdout: activeApp } = await execAsync(`
        osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true'
      `);
      
      const { stdout: windowTitle } = await execAsync(`
        osascript -e 'tell application "System Events" to get name of front window of first application process whose frontmost is true'
      `).catch(() => ({ stdout: 'No window title available' }));
      
      const screenshotPath = `/tmp/jarvis_screenshot_${Date.now()}.png`;
      let visionDescription = '';
      
      try {
        await execAsync(`screencapture -x "${screenshotPath}"`);
        
        const imageBuffer = fs.readFileSync(screenshotPath);
        const base64Image = imageBuffer.toString('base64');
        
        if (process.env.OPENAI_API_KEY) {
          try {
            const response = await fetch('https://api.openai.com/v1/chat/completions', {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                model: 'gpt-4o',
                messages: [
                  {
                    role: 'user',
                    content: [
                      {
                        type: 'text',
                        text: `Analyze this screenshot and describe:
1. What app is shown and what's visible on screen
2. Any text content that's readable
3. Clickable elements (buttons, links, text fields) and their approximate locations
4. What actions the user might want to take

Be specific about UI elements and their positions. Focus on actionable information.`
                      },
                      {
                        type: 'image_url',
                        image_url: {
                          url: `data:image/png;base64,${base64Image}`,
                          detail: 'high'
                        }
                      }
                    ]
                  }
                ],
                max_tokens: 500
              })
            });

            if (response.ok) {
              const result = await response.json();
              visionDescription = result.choices[0]?.message?.content || 'No description generated';
              logger.info('AI Vision analysis completed successfully');
            } else {
              throw new Error(`OpenAI API error: ${response.status}`);
            }
          } catch (apiError) {
            logger.error('OpenAI Vision API failed:', apiError);
            visionDescription = 'AI Vision analysis failed - please check your OpenAI API key and connection';
          }
        } else {
          visionDescription = 'OpenAI API key not configured - set OPENAI_API_KEY environment variable to enable AI vision';
        }
        
        await execAsync(`rm -f "${screenshotPath}"`).catch(() => {});
        
      } catch (screenshotError) {
        logger.error('Screenshot failed:', screenshotError);
        visionDescription = 'Screenshot capture failed - please check screen recording permissions';
      }
      
      const result = [
        `Active app: ${activeApp.trim()}`,
        `Window: ${windowTitle.trim()}`,
        ``,
        visionDescription
      ];
      
      return {
        success: true,
        output: result.join('\n'),
        action: 'read_screen'
      };
      
    } catch (error) {
      return {
        success: false,
        output: 'Failed to read screen context',
        action: 'read_screen',
        error: error instanceof Error ? error.message : 'Screen reading failed'
      };
    }
  }

  /**
   * Execute safe shell commands
   */
  async runShellCommand(command: string): Promise<ToolResult> {
    try {
      const commandParts = command.trim().split(' ');
      const baseCommand = commandParts[0];
      
      if (!this.safeCommands.has(baseCommand)) {
        return {
          success: false,
          output: `Command '${baseCommand}' is not in the safe commands list`,
          action: 'run_shell',
          error: 'Command not allowed'
        };
      }
      
      const { stdout, stderr } = await execAsync(command);
      
      return {
        success: true,
        output: stdout || stderr || 'Command executed successfully',
        action: 'run_shell'
      };
    } catch (error) {
      return {
        success: false,
        output: `Shell command failed: ${command}`,
        action: 'run_shell',
        error: error instanceof Error ? error.message : 'Command execution failed'
      };
    }
  }

  /**
   * Basic web search
   */
  async webSearch(query: string): Promise<ToolResult> {
    try {
      const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
      await execAsync(`open "${searchUrl}"`);
      
      return {
        success: true,
        output: `Opened web search for: ${query}`,
        action: 'web_search'
      };
    } catch (error) {
      return {
        success: false,
        output: `Failed to perform web search`,
        action: 'web_search',
        error: error instanceof Error ? error.message : 'Web search failed'
      };
    }
  }

  /**
   * Open browser and perform web search
   */
  async webSearchAndOpen(query: string): Promise<ToolResult> {
    try {
      const openResult = await this.openApp('Safari');
      if (!openResult.success) {
        return openResult;
      }
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      await this.pressKeys(['cmd', 'l']);
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
      await this.typeText(searchUrl);
      await new Promise(resolve => setTimeout(resolve, 500));
      
      await this.pressKeys(['return']);
      
      return {
        success: true,
        output: `Opened Safari and searched for: "${query}"`,
        action: 'web_search_and_open'
      };
    } catch (error) {
      return {
        success: false,
        output: `Failed to perform web search`,
        action: 'web_search_and_open',
        error: error instanceof Error ? error.message : 'Search failed'
      };
    }
  }

  /**
   * Open an app and type text into it
   */
  async openAndType(appName: string, text: string): Promise<ToolResult> {
    try {
      const openResult = await this.openApp(appName);
      if (!openResult.success) {
        return openResult;
      }
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const typeResult = await this.typeText(text);
      
      return {
        success: typeResult.success,
        output: `${openResult.output} and typed: "${text}"`,
        action: 'open_and_type'
      };
    } catch (error) {
      return {
        success: false,
        output: `Failed to open ${appName} and type text`,
        action: 'open_and_type',
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Click on an element using AI vision to find it
   */
  async clickElement(target: string): Promise<ToolResult> {
    try {
      const screenshotPath = `/tmp/jarvis_click_${Date.now()}.png`;
      await execAsync(`screencapture -x "${screenshotPath}"`);
      
      if (process.env.OPENAI_API_KEY) {
        const imageBuffer = fs.readFileSync(screenshotPath);
        const base64Image = imageBuffer.toString('base64');
        
        const response = await fetch('https://api.openai.com/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: 'gpt-4o',
            messages: [
              {
                role: 'user',
                content: [
                  {
                    type: 'text',
                    text: `Find the "${target}" element on this screen. Respond with ONLY the coordinates in this exact format: {"x": 123, "y": 456}. If you can't find it, respond with {"error": "not found"}.`
                  },
                  {
                    type: 'image_url',
                    image_url: {
                      url: `data:image/png;base64,${base64Image}`,
                      detail: 'high'
                    }
                  }
                ]
              }
            ],
            max_tokens: 100
          })
        });

        if (response.ok) {
          const result = await response.json();
          const aiResponse = result.choices[0]?.message?.content;
          
          try {
            const coords = JSON.parse(aiResponse);
            if (coords.error) {
              await execAsync(`rm -f "${screenshotPath}"`).catch(() => {});
              return this.clickElementAccessibility(target);
            }
            
            await execAsync(`osascript -e 'tell application "System Events" to click at {${coords.x}, ${coords.y}}'`);
            await execAsync(`rm -f "${screenshotPath}"`).catch(() => {});
            
            return {
              success: true,
              output: `Clicked on "${target}" at coordinates (${coords.x}, ${coords.y})`,
              action: 'click_element'
            };
          } catch (parseError) {
            return this.clickElementAccessibility(target);
          }
        }
      }
      
      await execAsync(`rm -f "${screenshotPath}"`).catch(() => {});
      return this.clickElementAccessibility(target);
      
    } catch (error) {
      return {
        success: false,
        output: `Failed to click on "${target}"`,
        action: 'click_element',
        error: error instanceof Error ? error.message : 'Click failed'
      };
    }
  }

  /**
   * Fallback: Click using accessibility API
   */
  private async clickElementAccessibility(target: string): Promise<ToolResult> {
    try {
      const { stdout: activeApp } = await execAsync(`
        osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true'
      `);
      
      const script = `
        tell application "System Events"
          tell process "${activeApp.trim()}"
            try
              click button "${target}"
              return "success"
            on error
              try
                click (first button whose title contains "${target}")
                return "success"
              on error
                return "not found"
              end try
            end try
          end tell
        end tell
      `;
      
      const { stdout } = await execAsync(`osascript -e '${script}'`);
      
      if (stdout.includes('success')) {
        return {
          success: true,
          output: `Clicked on "${target}"`,
          action: 'click_element'
        };
      } else {
        return {
          success: false,
          output: `Could not find button "${target}"`,
          action: 'click_element',
          error: 'Button not found'
        };
      }
    } catch (error) {
      return {
        success: false,
        output: `Failed to click "${target}"`,
        action: 'click_element',
        error: error instanceof Error ? error.message : 'Accessibility click failed'
      };
    }
  }

  /**
   * Type text into a specific field
   */
  async typeInField(text: string, fieldName: string): Promise<ToolResult> {
    try {
      const clickResult = await this.clickElement(fieldName);
      if (!clickResult.success) {
        return {
          success: false,
          output: `Could not find field "${fieldName}" to type in`,
          action: 'type_in_field',
          error: 'Field not found'
        };
      }
      
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const typeResult = await this.typeText(text);
      
      return {
        success: typeResult.success,
        output: `Typed "${text}" in field "${fieldName}"`,
        action: 'type_in_field'
      };
    } catch (error) {
      return {
        success: false,
        output: `Failed to type in field "${fieldName}"`,
        action: 'type_in_field',
        error: error instanceof Error ? error.message : 'Type in field failed'
      };
    }
  }

  /**
   * Scroll in a direction
   */
  async scroll(direction: string): Promise<ToolResult> {
    try {
      const scrollAmount = direction === 'up' ? '-10' : '10';
      
      const script = `
        tell application "System Events"
          scroll (first window of first process whose frontmost is true) by ${scrollAmount}
        end tell
      `;
      
      await execAsync(`osascript -e '${script}'`);
      
      return {
        success: true,
        output: `Scrolled ${direction}`,
        action: 'scroll'
      };
    } catch (error) {
      return {
        success: false,
        output: `Failed to scroll ${direction}`,
        action: 'scroll',
        error: error instanceof Error ? error.message : 'Scroll failed'
      };
    }
  }

  /**
   * Check if a tool call needs confirmation
   */
  needsConfirmation(toolCall: ToolCall): boolean {
    const dangerousActions = ['run_shell', 'delete_file', 'modify_system'];
    return dangerousActions.includes(toolCall.action);
  }
}