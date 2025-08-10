import { logger } from '../utils/logging.js';

export interface DeviceCommand {
  type: 'lights' | 'thermostat' | 'music' | 'security' | 'general';
  action: string;
  parameters?: Record<string, any>;
}

export class DeviceActions {
  async executeCommand(command: DeviceCommand): Promise<string> {
    logger.info('Executing device command:', command);

    switch (command.type) {
      case 'lights':
        return this.handleLights(command);
      case 'thermostat':
        return this.handleThermostat(command);
      case 'music':
        return this.handleMusic(command);
      case 'security':
        return this.handleSecurity(command);
      default:
        return this.handleGeneral(command);
    }
  }

  private async handleLights(command: DeviceCommand): Promise<string> {
    const { action, parameters } = command;
    
    // Placeholder for actual smart home integration
    logger.debug('Light command:', { action, parameters });
    
    switch (action.toLowerCase()) {
      case 'turn_on':
      case 'on':
        return `Turning on lights${parameters?.room ? ` in ${parameters.room}` : ''}`;
      case 'turn_off':
      case 'off':
        return `Turning off lights${parameters?.room ? ` in ${parameters.room}` : ''}`;
      case 'dim':
        const level = parameters?.level || 50;
        return `Dimming lights to ${level}%${parameters?.room ? ` in ${parameters.room}` : ''}`;
      case 'brighten':
        return `Brightening lights${parameters?.room ? ` in ${parameters.room}` : ''}`;
      default:
        return `Unknown light command: ${action}`;
    }
  }

  private async handleThermostat(command: DeviceCommand): Promise<string> {
    const { action, parameters } = command;
    
    logger.debug('Thermostat command:', { action, parameters });
    
    switch (action.toLowerCase()) {
      case 'set_temperature':
        const temp = parameters?.temperature || 72;
        return `Setting temperature to ${temp}°F`;
      case 'raise_temperature':
        return 'Raising temperature by 2 degrees';
      case 'lower_temperature':
        return 'Lowering temperature by 2 degrees';
      case 'set_mode':
        const mode = parameters?.mode || 'auto';
        return `Setting thermostat mode to ${mode}`;
      default:
        return `Unknown thermostat command: ${action}`;
    }
  }

  private async handleMusic(command: DeviceCommand): Promise<string> {
    const { action, parameters } = command;
    
    logger.debug('Music command:', { action, parameters });
    
    switch (action.toLowerCase()) {
      case 'play':
        const song = parameters?.song || 'music';
        return `Playing ${song}`;
      case 'pause':
        return 'Pausing music';
      case 'stop':
        return 'Stopping music';
      case 'volume_up':
        return 'Turning volume up';
      case 'volume_down':
        return 'Turning volume down';
      case 'next':
        return 'Skipping to next track';
      case 'previous':
        return 'Going to previous track';
      default:
        return `Unknown music command: ${action}`;
    }
  }

  private async handleSecurity(command: DeviceCommand): Promise<string> {
    const { action, parameters } = command;
    
    logger.debug('Security command:', { action, parameters });
    
    switch (action.toLowerCase()) {
      case 'arm':
        return 'Arming security system';
      case 'disarm':
        return 'Disarming security system';
      case 'lock_doors':
        return 'Locking all doors';
      case 'unlock_doors':
        return 'Unlocking doors';
      case 'check_status':
        return 'Security system is armed and all sensors are normal';
      default:
        return `Unknown security command: ${action}`;
    }
  }

  private async handleGeneral(command: DeviceCommand): Promise<string> {
    const { action, parameters } = command;
    
    logger.debug('General command:', { action, parameters });
    
    // Placeholder for general automation
    return `Executing ${action}${parameters ? ` with parameters: ${JSON.stringify(parameters)}` : ''}`;
  }

  // Parse natural language into device commands
  parseCommand(input: string): DeviceCommand | null {
    const lower = input.toLowerCase();
    
    // Light commands
    if (lower.includes('light') || lower.includes('lamp')) {
      if (lower.includes('turn on') || lower.includes('switch on')) {
        return { type: 'lights', action: 'turn_on' };
      }
      if (lower.includes('turn off') || lower.includes('switch off')) {
        return { type: 'lights', action: 'turn_off' };
      }
      if (lower.includes('dim')) {
        return { type: 'lights', action: 'dim' };
      }
      if (lower.includes('brighten') || lower.includes('bright')) {
        return { type: 'lights', action: 'brighten' };
      }
    }
    
    // Thermostat commands
    if (lower.includes('temperature') || lower.includes('thermostat') || lower.includes('heat') || lower.includes('cool')) {
      if (lower.includes('set') && /\d+/.test(lower)) {
        const temp = lower.match(/\d+/)?.[0];
        return { 
          type: 'thermostat', 
          action: 'set_temperature', 
          parameters: { temperature: parseInt(temp || '72') }
        };
      }
      if (lower.includes('raise') || lower.includes('up') || lower.includes('warmer')) {
        return { type: 'thermostat', action: 'raise_temperature' };
      }
      if (lower.includes('lower') || lower.includes('down') || lower.includes('cooler')) {
        return { type: 'thermostat', action: 'lower_temperature' };
      }
    }
    
    // Music commands
    if (lower.includes('music') || lower.includes('song') || lower.includes('play') || lower.includes('spotify')) {
      if (lower.includes('play')) {
        return { type: 'music', action: 'play' };
      }
      if (lower.includes('pause')) {
        return { type: 'music', action: 'pause' };
      }
      if (lower.includes('stop')) {
        return { type: 'music', action: 'stop' };
      }
      if (lower.includes('volume up') || lower.includes('louder')) {
        return { type: 'music', action: 'volume_up' };
      }
      if (lower.includes('volume down') || lower.includes('quieter')) {
        return { type: 'music', action: 'volume_down' };
      }
    }
    
    // Security commands
    if (lower.includes('lock') || lower.includes('unlock') || lower.includes('security') || lower.includes('alarm')) {
      if (lower.includes('lock')) {
        return { type: 'security', action: 'lock_doors' };
      }
      if (lower.includes('unlock')) {
        return { type: 'security', action: 'unlock_doors' };
      }
      if (lower.includes('arm')) {
        return { type: 'security', action: 'arm' };
      }
      if (lower.includes('disarm')) {
        return { type: 'security', action: 'disarm' };
      }
    }
    
    return null;
  }

  // Additional method needed by index.ts
  async executeDirectCommand(input: string) {
    const command = this.parseCommand(input);
    
    if (command) {
      const message = await this.executeCommand(command);
      return {
        success: true,
        message,
        action: command.action,
        device: command.type
      };
    } else {
      return {
        success: false,
        message: 'Command not recognized',
        action: 'unknown',
        device: 'unknown'
      };
    }
  }
}
