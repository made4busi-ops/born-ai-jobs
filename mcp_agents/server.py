from fastmcp import FastMCP
from agents.agent_53_sniper import Agent53Sniper

mcp = FastMCP("NeverX007 Agents Server")

@mcp.tool()
def run_agent_53_sniper() -> str:
    """Run Agent 53 - Sniper to find good deals"""
    agent = Agent53Sniper()
    agent.find_deals()
    return "Agent 53 finished running"

if __name__ == "__main__":
    mcp.run()
