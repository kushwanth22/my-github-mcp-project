import asyncio

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient

from gateway.auth import GATEWAY, MCP_PATH, get_gateway_token


async def run_issue_triager_agent():
    token = get_gateway_token(
        client_id="agent-issue-triager",
        client_secret_env="AGENT_ISSUE_TRIAGER_SECRET",
        scope="github:read github:issues:write",
    )

    mcp_client = MultiServerMCPClient(
        {
            "github": {
                "url": f"{GATEWAY}{MCP_PATH}",
                "transport": "streamable_http",
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    )
    tools = await mcp_client.get_tools()

    llm = ChatAnthropic(model="claude-sonnet-5")
    agent = create_agent(llm, tools)

    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Check open issues in kushwanth22/fundready-ai. For any issue "
                        "without a label, add an appropriate one (bug, enhancement, "
                        "question, triaged) based on its title. Report what you changed."
                    ),
                }
            ]
        }
    )

    print_final_response(result)


def print_final_response(result):
    content = result["messages"][-1].content
    if isinstance(content, str):
        print(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                print(block["text"])
    else:
        print(content)


if __name__ == "__main__":
    asyncio.run(run_issue_triager_agent())
