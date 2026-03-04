import { DashClaw } from 'dashclaw';

async function run() {
  console.log('Base URL:', process.env.DASHCLAW_BASE_URL || "(not set)");
  console.log('Agent ID:', process.env.DASHCLAW_AGENT_ID || "(not set)");
  console.log('API Key configured:', !!process.env.DASHCLAW_API_KEY);

  const claw = new DashClaw({
    baseUrl: process.env.DASHCLAW_BASE_URL,
    apiKey: process.env.DASHCLAW_API_KEY,
    agentId: process.env.DASHCLAW_AGENT_ID || "openclaw-agent",
    agentName: process.env.DASHCLAW_AGENT_ID || "openclaw-agent",
  });

  try {
    const response = await claw.createAction({
      action_type: 'monitor',
      declared_goal: 'Smoke test: agent connected from OpenClaw',
      risk_score: 1,
    });
    console.log('✅ DashClaw action successfully created:', response.action_id || response.id || response);
  } catch (error) {
    console.error('❌ Failed to connect to DashClaw:', error.message || error);
  }
}

run();
