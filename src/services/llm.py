"""LLM service for article summarization.

This module provides an abstraction layer for LLM services used to generate
article summaries. The design uses an abstract base class with concrete
implementations for different LLM providers (currently Ollama).

Architecture:
- BaseLLMService: Abstract base class defining the interface
- OllamaLLMService: Singleton implementation using Ollama with HuggingFace models
- get_llm_service(): Factory function to get the appropriate service instance

Concurrent Processing Upgrade Path:
To enable concurrent summarization (when moving from sequential to parallel processing):
1. Remove sleep delays from retry logic in processor.py
2. Add asyncio.Semaphore(max_concurrent_requests) to control GPU access
3. Convert synchronous calls to async/await pattern
4. Increase ThreadPoolExecutor max_workers in main.py startup_event()
5. Monitor GPU memory usage and adjust max_concurrent_requests accordingly
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import httpx
from src.config import settings
from src.utils.logging import logger


class BaseLLMService(ABC):
    """Abstract base class for LLM services."""
    
    @abstractmethod
    def summarize(self, content: str, title: str, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate a summary of the article content.
        
        Args:
            content: The article content to summarize
            title: The article title
            url: The article URL
        Returns:
            Tuple of (success: bool, summary: Optional[str], error: Optional[str])
        """
        pass


class OllamaLLMService(BaseLLMService):
    """Ollama LLM service implementation (singleton pattern)."""
    
    _instance: Optional['OllamaLLMService'] = None
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            setattr(cls._instance, '_initialized', False)
        return cls._instance
    
    def __init__(self):
        """Initialize the service (only once due to singleton)."""
        if getattr(self, '_initialized', False):
            return
        self.client = httpx.Client(timeout=settings.llm_timeout)
        self.base_url = settings.llm_base_url
        self.model_name = settings.llm_model_name
        self.temperature = settings.llm_temperature
        self._initialized = True
        logger.info("OllamaLLMService initialized: %s, model=%s", self.base_url, self.model_name)
    

    
    def summarize(self, content: str, title: str, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate a summary using Ollama.
        
        Args:
            content: The article content to summarize
            title: The article title
            url: The article URL
            
        Returns:
            Tuple of (success, summary, error)
        """
        try:
            # Improved prompt: explicitly request only summary sentences
            prompt = (
                "Write a 3-5 sentence summary of this article. Output only the summary sentences, nothing else:\n\n"
                f"{content}"
            )
            # Make request to Ollama API
            logger.info("Requesting summary from Ollama for: %s...", title[:50])
            response = self.client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            # Extract summary from response
            summary = result.get("response", "").strip()
            if not summary:
                logger.error("Ollama returned empty summary")
                return False, None, "Summarization service returned empty result"
            # Post-process to remove narration lines
            summary = self._clean_summary(summary)
            # Truncate if needed (should not happen with good prompts)
            if len(summary) > settings.summary_max_length:
                logger.warning("Summary exceeded max length (%d > %d), truncating", len(summary), settings.summary_max_length)
                summary = summary[:settings.summary_max_length]
            logger.info("Summary generated successfully (%d chars)", len(summary))
            return True, summary, None
        except httpx.TimeoutException:
            logger.error("Timeout while generating summary for: %s", url)
            return False, None, "Summarization service timeout"
        except httpx.ConnectError as e:
            logger.error("Connection error to Ollama: %s", e)
            return False, None, "Summarization service unavailable"
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error from Ollama: %d - %s", e.response.status_code, e.response.text)
            return False, None, "Summarization service error"
        except Exception as e:
            logger.error("Unexpected error during summarization: %s", e, exc_info=True)
            return False, None, f"Summarization error: {str(e)}"

    def _clean_summary(self, summary: str) -> str:
        """
        Remove narration or instruction lines from LLM output, keeping only summary sentences.
        """
        import re
        lines = summary.splitlines()
        cleaned = []
        for line in lines:
            line = line.strip()
            # Remove lines that look like narration or instructions
            if not line:
                continue
            if re.match(r"^(summary:|here( is| are)? (a|the|an|\d+) (summary|sentence|key|main)( sentence)?s?:?|in summary|to summarize|the article|this article|overall,|in conclusion|conclusion:|key points:|main points:|highlights:|takeaways:|tl;dr:)", line, re.IGNORECASE):
                continue
            # Remove lines that are just markdown bullets or numbers
            if re.match(r"^[-*\d. ]+$", line):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)


def get_llm_service() -> BaseLLMService:
    """
    Get the LLM service instance.
    
    Returns:
        BaseLLMService instance (currently OllamaLLMService)
    """
    return OllamaLLMService()
