#!/usr/bin/env node

/**
 * Uptime Kuma Configuration Script via Socket.IO
 * 
 * This script automates the initial setup and configuration of Uptime Kuma
 * using Socket.IO client, as the REST API is not available for setup operations.
 */

const io = require('socket.io-client');
const fs = require('fs');
const path = require('path');

// Configuration from command line arguments or environment
const config = {
  url: process.env.UPTIME_KUMA_URL || 'http://localhost:3001',
  publicUrl: process.env.UPTIME_KUMA_PUBLIC_URL || process.env.UPTIME_KUMA_URL || 'http://localhost:3001',
  adminUsername: process.env.ADMIN_USERNAME || process.argv[2],
  adminPassword: process.env.ADMIN_PASSWORD || process.argv[3],
  configFile: process.env.CONFIG_FILE || process.argv[4],
};

// Validate required parameters
if (!config.adminUsername || !config.adminPassword || !config.configFile) {
  console.error('Usage: node configure_uptime_kuma.js <admin_username> <admin_password> <config_file.json>');
  console.error('   OR: Set environment variables ADMIN_USERNAME, ADMIN_PASSWORD, CONFIG_FILE');
  process.exit(1);
}

// Load configuration file with SMTP and monitors
let monitoringConfig;
try {
  const configData = fs.readFileSync(config.configFile, 'utf8');
  monitoringConfig = JSON.parse(configData);
} catch (error) {
  console.error(`Error reading config file: ${error.message}`);
  process.exit(1);
}

// Socket.IO client setup
const socket = io(config.url, {
  reconnection: true,
  timeout: 10000,
  transports: ['websocket', 'polling'],
});

let isAuthenticated = false;
let authToken = null;
let configurationStarted = false;

// Helper function to emit and wait for response
function emitAsync(event, data = {}) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error(`Timeout waiting for response to ${event}`));
    }, 30000);

    socket.emit(event, data, (response) => {
      clearTimeout(timeout);
      if (response && response.ok === false) {
        reject(new Error(response.msg || `Error in ${event}`));
      } else {
        resolve(response);
      }
    });
  });
}

// Helper function for addNotification which requires 3 parameters: notification, notificationID, callback
function addNotificationAsync(notification, notificationID = null) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error(`Timeout waiting for response to addNotification`));
    }, 30000);

    socket.emit('addNotification', notification, notificationID, (response) => {
      clearTimeout(timeout);
      if (response && response.ok === false) {
        reject(new Error(response.msg || 'Error in addNotification'));
      } else {
        resolve(response);
      }
    });
  });
}

// Main execution function
async function configureUptimeKuma() {
  // Prevent multiple executions
  if (configurationStarted) {
    return;
  }
  configurationStarted = true;
  
  try {
    // Step 1: Check if setup is needed
    console.log('Checking setup status...');
    
    const needSetup = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Timeout waiting for needSetup response'));
      }, 10000);
      
      socket.emit('needSetup', (response) => {
        clearTimeout(timeout);
        resolve(response);
      });
    });
    
    console.log('DEBUG: needSetup value:', needSetup);
    
    if (needSetup) {
      console.log('⚙ Initial setup required, creating admin account...');
      
      // Note: setup event expects separate parameters, not an object
      const setupResponse = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Timeout waiting for setup response'));
        }, 10000);
        
        socket.emit('setup', config.adminUsername, config.adminPassword, (response) => {
          clearTimeout(timeout);
          if (response && response.ok === false) {
            reject(new Error(response.msg || 'Setup failed'));
          } else {
            resolve(response);
          }
        });
      });
      
      console.log('✓ Admin account created');
    } else {
      console.log('✓ Setup already completed, logging in...');
    }

    // Step 2: Login
    const loginResponse = await emitAsync('login', {
      username: config.adminUsername,
      password: config.adminPassword,
      token: '',
    });

    if (loginResponse.ok) {
      isAuthenticated = true;
      authToken = loginResponse.token;
      console.log('✓ Logged in successfully');
    } else {
      throw new Error('Login failed: ' + loginResponse.msg);
    }

    // Step 3: Configure SMTP notification (with idempotency)
    if (monitoringConfig.smtp && monitoringConfig.smtp.host) {
      console.log('Configuring SMTP notification...');
      console.log(`  Host: ${monitoringConfig.smtp.host}:${monitoringConfig.smtp.port}`);
      console.log(`  From: ${monitoringConfig.smtp.from}`);
      console.log(`  To: ${monitoringConfig.smtp.to}`);
      
      try {
        // Get existing notifications (pushed after login via notificationList event)
        let existingNotifications = [];
        await new Promise((resolve) => {
          const timeout = setTimeout(resolve, 3000);
          
          socket.once('notificationList', (data) => {
            clearTimeout(timeout);
            existingNotifications = data || [];
            console.log(`  Found ${existingNotifications.length} existing notifications`);
            resolve();
          });
        });
        
        // Build SMTP configuration (reused for add/update and test)
        const notificationName = 'Email Notifications';
        const smtpConfig = {
          name: notificationName,
          type: 'smtp',
          isDefault: true,
          applyExisting: true,
          smtpHost: monitoringConfig.smtp.host,
          smtpPort: monitoringConfig.smtp.port,
          smtpSecure: '', // Empty string for STARTTLS on port 587
          smtpIgnoreTLSError: false,
          smtpUsername: monitoringConfig.smtp.user,
          smtpPassword: monitoringConfig.smtp.password,
          smtpFrom: monitoringConfig.smtp.from,
          smtpTo: monitoringConfig.smtp.to,
        };
        
        // Check if notification exists and create/update
        const existingNotif = existingNotifications.find(n => n.name === notificationName);
        
        if (existingNotif) {
          console.log(`  - ${notificationName}: already exists, updating...`);
          const notifResponse = await addNotificationAsync(smtpConfig, existingNotif.id);
          
          if (notifResponse && notifResponse.ok) {
            console.log(`  ✓ ${notificationName}: updated`);
          } else {
            console.log(`  ⚠ ${notificationName}: update failed: ${JSON.stringify(notifResponse)}`);
          }
        } else {
          const notifResponse = await addNotificationAsync(smtpConfig, null);
          
          if (notifResponse && notifResponse.ok) {
            console.log(`  ✓ ${notificationName}: created`);
          } else {
            console.log(`  ⚠ ${notificationName}: unexpected response: ${JSON.stringify(notifResponse)}`);
          }
        }
        
        // Test the notification
        console.log('  Testing notification...');
        const testResponse = await emitAsync('testNotification', smtpConfig);
        if (testResponse && testResponse.ok) {
          console.log(`  ✓ Test notification: ${testResponse.msg}`);
        } else {
          console.log(`  ⚠ Test notification failed: ${JSON.stringify(testResponse)}`);
        }
        
      } catch (error) {
        console.log(`⚠ SMTP notification error: ${error.message}`);
        console.log('  (This is non-critical, continuing with monitor setup)');
      }
    }

    // Step 4: Add monitors (with idempotency)
    if (monitoringConfig.monitors && Array.isArray(monitoringConfig.monitors)) {
      console.log(`Adding ${monitoringConfig.monitors.length} monitors...`);
      
      // Get existing monitors via monitorList event (push model)
      let existingMonitors = {};
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Timeout waiting for monitorList event')), 10000);
        
        socket.once('monitorList', (data) => {
          clearTimeout(timeout);
          existingMonitors = data || {};
          console.log(`  Found ${Object.keys(existingMonitors).length} existing monitors`);
          resolve();
        });
        
        // Trigger the monitorList push
        socket.emit('getMonitorList', (response) => {
          if (!response || !response.ok) {
            clearTimeout(timeout);
            reject(new Error('Failed to get monitor list'));
          }
        });
      });
      
      // Build set of existing monitor names for fast lookup
      const existingNames = new Set(
        Object.values(existingMonitors).map(m => m.name)
      );
      console.log(`  Existing monitor names: ${[...existingNames].join(', ') || 'none'}`);
      
      // Add monitors that don't exist yet
      for (const monitor of monitoringConfig.monitors) {
        let shouldCreate = true;

        if (existingNames.has(monitor.name)) {
          const existing = Object.values(existingMonitors).find(m => m.name === monitor.name);
          
          // Check if it's a broken push monitor (missing token)
          if (monitor.type === 'push' && !existing.pushToken) {
            console.log(`  - ${monitor.name}: exists but missing pushToken, deleting to recreate...`);
            try {
              await emitAsync('deleteMonitor', existing.id);
              console.log(`  ✓ ${monitor.name}: deleted`);
            } catch (error) {
              console.log(`  ⚠ ${monitor.name}: delete failed (${error.message})`);
              shouldCreate = false; // Don't try to create if delete failed
            }
          } else {
            console.log(`  - ${monitor.name}: already exists (skipping)`);
            shouldCreate = false;
          }
        }
        
        if (shouldCreate) {
          try {
            const monitorConfig = {
            type: monitor.type || 'http',
            name: monitor.name,
            url: monitor.url || '',
            interval: monitor.interval || 60,
            retryInterval: monitor.retryInterval || 60,
            resendInterval: 0,
            maxretries: 1,
            upsideDown: false,
            notificationIDList: {},
            ignoreTls: monitor.ignoreTls || false,
            expiryNotification: false,
            maxredirects: 10,
            accepted_statuscodes: ['200-299'],
            dns_resolve_type: 'A',
            dns_resolve_server: '1.1.1.1',
            docker_container: '',
            docker_host: null,
            proxyId: null,
            method: 'GET',
            body: null,
            headers: null,
            authMethod: null,
            active: true,
          };

          // For Push monitors, generate a token if not provided
          if (monitorConfig.type === 'push') {
             // Generate a random 10-char token
             const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
             let token = '';
             for (let i = 0; i < 10; i++) {
                 token += chars.charAt(Math.floor(Math.random() * chars.length));
             }
             monitorConfig.pushToken = token;
             console.log(`  ℹ ${monitor.name}: Generated client-side push token: ${token}`);
          }

          const response = await emitAsync('add', monitorConfig);
          if (response && response.ok) {
            console.log(`  ✓ ${monitor.name}: created`);
          } else {
            console.log(`  ⚠ ${monitor.name}: response: ${JSON.stringify(response)}`);
          }
        } catch (error) {
          console.log(`  ⚠ ${monitor.name}: error (${error.message})`);
        }
      }
    }

      // Refresh monitor list to get tokens for all monitors (including new ones)
      console.log('Refreshing monitor list to retrieve tokens...');
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Timeout waiting for monitorList event')), 10000);
        
        socket.once('monitorList', (data) => {
          clearTimeout(timeout);
          existingMonitors = data || {};
          resolve();
        });
        
        socket.emit('getMonitorList', (response) => {
          if (!response || !response.ok) {
            clearTimeout(timeout);
            reject(new Error('Failed to get monitor list'));
          }
        });
      });

      console.log(`DEBUG: Refreshed monitors: ${Object.keys(existingMonitors).length}`);
      
      const backupMonitor = Object.values(existingMonitors).find(m => m.name === 'Proxmox Backup');
      if (backupMonitor) {
        console.log(`DEBUG: Proxmox Backup monitor found. Type: ${backupMonitor.type}, PushToken: ${backupMonitor.pushToken}`);
      } else {
        console.log('DEBUG: Proxmox Backup monitor NOT found in refreshed list');
      }

      // Collect Push URLs
      const pushMonitors = {};
      for (const monitor of monitoringConfig.monitors) {
        if (monitor.type === 'push') {
          // Find the monitor in the updated list
          const foundMonitor = Object.values(existingMonitors).find(m => m.name === monitor.name);
          if (foundMonitor && foundMonitor.pushToken) {
            pushMonitors[monitor.name] = {
              pushToken: foundMonitor.pushToken,
              pushUrl: `${config.publicUrl.replace(/\/$/, '')}/api/push/${foundMonitor.pushToken}`
            };
          }
        }
      }

      // Output Push URLs as JSON for Ansible to capture
      if (Object.keys(pushMonitors).length > 0) {
        console.log('__PUSH_MONITORS_JSON__');
        console.log(JSON.stringify(pushMonitors));
        console.log('__END_PUSH_MONITORS_JSON__');
      }
    }

    console.log('\n✅ Configuration complete!');
    console.log(`   Dashboard: ${config.url}`);
    console.log(`   Username: ${config.adminUsername}`);
    
    socket.disconnect();
    process.exit(0);

  } catch (error) {
    console.error(`\n❌ Error: ${error.message}`);
    socket.disconnect();
    process.exit(1);
  }
}

// Connection event handlers
socket.on('connect', () => {
  console.log('✓ Connected to Uptime Kuma');
});

// Listen for the 'info' event that Uptime Kuma sends upon connection
socket.once('info', async (info) => {
  console.log('Received server info');
  await configureUptimeKuma();
});

socket.on('connect_error', (error) => {
  console.error('Connection error:', error.message);
  process.exit(1);
});

socket.on('disconnect', (reason) => {
  if (!isAuthenticated) {
    console.log('Disconnected:', reason);
  }
});

// Handle process termination
process.on('SIGINT', () => {
  console.log('\nInterrupted');
  socket.disconnect();
  process.exit(130);
});
