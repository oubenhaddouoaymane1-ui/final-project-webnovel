"""LLM integration module — cloud-only via OpenRouter (no local GPU)."""
from .openrouter_client import OpenRouterLLMClient

__all__ = ["OpenRouterLLMClient"]

# Backward compatibility alias
OllamaClient = OpenRouterLLMClient
