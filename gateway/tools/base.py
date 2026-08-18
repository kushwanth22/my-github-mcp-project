from abc import ABC, abstractmethod
from dataclasses import dataclass

from mcp import ClientSession, types
from pydantic import BaseModel


@dataclass
class ToolContext:
    session: ClientSession


class BaseTool(ABC):
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    def to_mcp_tool(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_model.model_json_schema(),
        )

    async def __call__(self, arguments: dict, ctx: ToolContext) -> list[types.TextContent]:
        args = self.input_model(**arguments)
        result = await self.run(args, ctx)
        return [types.TextContent(type="text", text=result.model_dump_json())]

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> BaseModel: ...
