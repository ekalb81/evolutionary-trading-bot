# DashClaw Connection Test

This script connects to your DashClaw instance using the installed SDK.

## Setup

You need a `DASHCLAW_API_KEY` from your DashClaw dashboard.

Run this in the terminal with the key:
```bash
export DASHCLAW_API_KEY="your-key-here"
node /data/workspace/dashclaw-test/connect.js
```

## Script: /data/workspace/dashclaw-test/connect.js

```javascript
import { DashClaw } from 'dashclaw';

const baseUrl = 'https://dash-claw-wheat.vercel.app/';
const apiKey = process.env.DASHCLAW_API_KEY;
const agentId = 'openclaw-agent';

if (!apiKey) {
  console.error('Error: DASHCLAW_API_KEY not set in environment.');
  console.log('Run: export DASHCLAW_API_KEY="your-key"');
  process.exit(1);
}

const claw = new DashClaw({
  baseUrl: baseUrl,
  apiKey: apiKey,
  agentId: agentId,
  agentName: 'OpenClaw Agent',
});

console.log(`Connecting to ${baseUrl}...`);

(async () => {
  try {
    // Attempt to fetch agent info or health check
    // (Depends on DashClaw API, usually GET /agents or just createAction implies connection)
    const action = await claw.createAction({
      action_type: 'test_connection',
      declared_goal: 'Verify OpenClaw connectivity',
      risk_score: 0,
    });
    console.log('Connection successful! Action ID:', action.action_id || action.id);
    
    await claw.updateOutcome(action.action_id || action.id, {
      status: 'completed',
      output_summary: 'Successfully connected from OpenClaw instance.',
    });
  } catch (e) {
    console.error('Connection failed:', e.message);
  }
})();
