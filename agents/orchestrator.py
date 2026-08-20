import logging
import uuid
from typing import TypedDict

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from gateway.auth import INTERNAL_GATEWAY, MCP_PATH, get_gateway_token_async

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("orchestrator")


class OrchestratorState(TypedDict):
    owner: str
    repo: str
    issue_number: int
    context: str
    proposed_fix: str
    approved: bool | None


def log_tool_calls(node: str, result: dict) -> None:
    for msg in result["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                logger.info(f"  [{node}] → tool: {tc['name']} args={tc['args']}")


def extract_text(result) -> str:
    content = result["messages"][-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


async def build_agent(client_id: str, secret_env: str, scope: str):
    token = await get_gateway_token_async(
        client_id=client_id,
        client_secret_env=secret_env,
        scope=scope,
        base_url=INTERNAL_GATEWAY,
    )
    mcp_client = MultiServerMCPClient(
        {
            "github": {
                "url": f"{INTERNAL_GATEWAY}{MCP_PATH}",
                "transport": "streamable_http",
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    )
    tools = await mcp_client.get_tools()
    llm = ChatAnthropic(model="claude-sonnet-5")
    return create_agent(llm, tools)


async def gather_context_node(state: OrchestratorState):
    logger.info(
        f"[gather_context] starting for {state['owner']}/{state['repo']} issue #{state['issue_number']}"
    )
    agent = await build_agent("agent-nightly-report", "AGENT_NIGHTLY_REPORT_SECRET", "github:read")
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Gather recent commits and related activity in {state['owner']}/{state['repo']} "
                        f"that might be relevant to issue #{state['issue_number']}. Be concise."
                    ),
                }
            ]
        }
    )
    log_tool_calls("gather_context", result)
    text = extract_text(result)
    logger.info(f"[gather_context] done — {len(text)} chars returned")
    return {"context": text}


async def draft_fix_node(state: OrchestratorState):
    logger.info(f"[draft_fix] starting for issue #{state['issue_number']}")
    agent = await build_agent(
        "agent-issue-triager", "AGENT_ISSUE_TRIAGER_SECRET", "github:read github:issues:write"
    )
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Context on {state['owner']}/{state['repo']}: {state['context']}\n\n"
                        f"Look at issue #{state['issue_number']} and propose a fix. "
                        f"Describe exactly what file(s) you'd change and what the new content would be. "
                        f"Do NOT attempt to commit anything -- you only have read and issue-comment access right now."
                    ),
                }
            ]
        }
    )
    log_tool_calls("draft_fix", result)
    text = extract_text(result)
    logger.info(f"[draft_fix] done — {len(text)} chars returned")
    return {"proposed_fix": text}


async def request_consent_node(state: OrchestratorState):
    logger.info(f"[request_consent] pausing for approval on issue #{state['issue_number']}")
    decision = interrupt(
        {
            "question": f"Approve this fix for {state['owner']}/{state['repo']} issue #{state['issue_number']}?",
            "proposed_fix": state["proposed_fix"],
        }
    )
    logger.info(f"[request_consent] resumed with decision={decision}")
    return {"approved": decision == "approve"}


async def commit_fix_node(state: OrchestratorState):
    if not state["approved"]:
        logger.info("[commit_fix] not approved, skipping")
        return {}
    logger.info(f"[commit_fix] committing approved fix for issue #{state['issue_number']}")
    agent = await build_agent(
        "agent-issue-triager",
        "AGENT_ISSUE_TRIAGER_SECRET",
        "github:read github:issues:write github:write",
    )
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"The following fix was approved by the repo owner for "
                        f"{state['owner']}/{state['repo']} issue #{state['issue_number']}:\n\n"
                        f"{state['proposed_fix']}\n\n"
                        f"Commit this change now, and comment on the issue linking the commit."
                    ),
                }
            ]
        }
    )
    log_tool_calls("commit_fix", result)
    text = extract_text(result)
    logger.info(f"[commit_fix] done — {text}")
    return {"context": state["context"] + "\n\nCommit result:\n" + text}


def build_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("gather_context", gather_context_node)
    graph.add_node("draft_fix", draft_fix_node)
    graph.add_node("request_consent", request_consent_node)
    graph.add_node("commit_fix", commit_fix_node)

    graph.set_entry_point("gather_context")
    graph.add_edge("gather_context", "draft_fix")
    graph.add_edge("draft_fix", "request_consent")
    graph.add_edge("request_consent", "commit_fix")
    graph.add_edge("commit_fix", END)

    return graph.compile(checkpointer=MemorySaver())


_graph = build_graph()
_pending = {}


def get_pending():
    return _pending


async def start_orchestrator(owner: str, repo: str, issue_number: int):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    result = await _graph.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
            "context": "",
            "proposed_fix": "",
            "approved": None,
        },
        config=config,
    )

    if "__interrupt__" in result:
        interrupt_data = result["__interrupt__"][0].value
        _pending[thread_id] = {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
            "proposed_fix": interrupt_data["proposed_fix"],
        }
        logger.info(
            f"[PENDING APPROVAL] thread_id={thread_id} {owner}/{repo} issue #{issue_number}"
        )
        logger.info(f"  Proposed fix:\n{interrupt_data['proposed_fix']}")
        logger.info(f"  Approve with: python3 approve.py {thread_id} approve")
        logger.info(f"  Reject with:  python3 approve.py {thread_id} reject")

    return thread_id


async def resume_orchestrator(thread_id: str, decision: str):
    config = {"configurable": {"thread_id": thread_id}}
    result = await _graph.ainvoke(Command(resume=decision), config=config)
    _pending.pop(thread_id, None)
    return result
