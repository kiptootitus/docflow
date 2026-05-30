from abc import ABC, abstractmethod
from typing import Generator, Dict, Any, List
from django.conf import settings
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

class AIProvider(ABC):
    """
    Abstract blueprint enforcing absolute structural signature compliance 
    across swap-ready generative model provider classes.
    """
    @abstractmethod
    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Dict[str, Any]:
        pass

    @abstractmethod
    def stream_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Generator[str, None, None]:
        pass


class AnthropicAIProvider(AIProvider):
    def __init__(self, model_name: str = "claude-3-5-sonnet-20241022"):
        self.llm = ChatAnthropic(
            model=model_name,
            temperature=0.0,
            anthropic_api_key=settings.ANTHROPIC_API_KEY
        )

    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Dict[str, Any]:
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        response = self.llm.invoke(messages, temperature=temperature)
        metadata = response.response_metadata
        return {
            "content": response.content,
            "tokens_used": metadata.get("usage", {}).get("total_tokens", 0),
            "model": self.llm.model
        }

    def stream_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Generator[str, None, None]:
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        for chunk in self.llm.stream(messages, temperature=temperature):
            yield chunk.content


class OpenAIAIProvider(AIProvider):
    def __init__(self, model_name: str = "gpt-4o"):
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.0,
            openai_api_key=settings.OPENAI_API_KEY
        )

    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Dict[str, Any]:
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        response = self.llm.invoke(messages, temperature=temperature)
        token_usage = response.usage_metadata or {}
        return {
            "content": response.content,
            "tokens_used": token_usage.get("total_tokens", 0),
            "model": self.llm.model
        }

    def stream_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Generator[str, None, None]:
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        for chunk in self.llm.stream(messages, temperature=temperature):
            yield chunk.content


def get_ai_provider(model_name: str) -> AIProvider:
    """
    Factory dispatch engine resolving structural client routing requests 
    dynamically at runtime based on model parameters.
    """
    if "claude" in model_name.lower():
        return AnthropicAIProvider(model_name=model_name)
    elif "gpt" in model_name.lower():
        return OpenAIAIProvider(model_name=model_name)
    else:
        # High-availability corporate defensive configuration fallback option
        return OpenAIAIProvider(model_name="gpt-4o")