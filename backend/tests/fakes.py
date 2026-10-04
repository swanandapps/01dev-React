"""A scripted chat model for create_agent tests — no network.

GenericFakeChatModel alone can't drive create_agent: it has no bind_tools, and its
_stream drops tool_calls under stream_mode="messages". This subclass fixes both.
"""
import json

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = next(self.messages)
        msg = AIMessage(content=msg) if isinstance(msg, str) else msg
        if msg.tool_calls:
            chunk = ChatGenerationChunk(message=AIMessageChunk(
                content=msg.content, id=msg.id, chunk_position="last",
                tool_call_chunks=[
                    {"name": t["name"], "args": json.dumps(t["args"]), "id": t["id"], "index": i}
                    for i, t in enumerate(msg.tool_calls)
                ],
            ))
            if run_manager:
                run_manager.on_llm_new_token(msg.content, chunk=chunk)
            yield chunk
            return
        words = msg.content.split(" ")
        for i, w in enumerate(words):
            chunk = ChatGenerationChunk(message=AIMessageChunk(
                content=w if i == 0 else " " + w, id=msg.id,
                chunk_position="last" if i == len(words) - 1 else None,
            ))
            if run_manager:
                run_manager.on_llm_new_token(chunk.message.content, chunk=chunk)
            yield chunk
