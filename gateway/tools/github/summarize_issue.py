import json

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from gateway.tools.base import BaseTool, ToolContext


class SummarizeIssueInput(BaseModel):
    owner: str
    repo: str
    issue_number: int


class SummarizeIssueOutput(BaseModel):
    summary: str
    suggested_labels: list[str]


class SummarizeIssueTool(BaseTool):
    name = "summarize_issue"
    description = "Summarize a GitHub issue and suggest labels based on its content"
    input_model = SummarizeIssueInput
    output_model = SummarizeIssueOutput

    async def run(self, args: SummarizeIssueInput, ctx: ToolContext) -> SummarizeIssueOutput:
        issue_result = await ctx.session.call_tool(
            "get_issue",
            {
                "owner": args.owner,
                "repo": args.repo,
                "issue_number": args.issue_number,
            },
        )
        issue_text = issue_result.content[0].text if issue_result.content else ""

        client = AsyncAnthropic()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize this GitHub issue in 2-3 sentences and suggest 1-3 labels "
                        "from: bug, enhancement, question, documentation, good first issue.\n\n"
                        f"Issue:\n{issue_text}\n\n"
                        'Respond as JSON only: {"summary": "...", "suggested_labels": [...]}'
                    ),
                }
            ],
        )

        data = json.loads(response.content[0].text)
        return SummarizeIssueOutput(**data)
