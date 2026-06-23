"""LLM service for article summarization.

This module provides an abstraction layer for LLM services used to generate
article summaries through an OpenAI-compatible API.
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


class OpenAICompatibleLLMService(BaseLLMService):
    """OpenAI-compatible LLM service implementation (singleton pattern)."""
    
    _instance: Optional['OpenAICompatibleLLMService'] = None
    
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
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key.strip()
        self.model_name = settings.llm_model_name
        self._initialized = True
        logger.info("OpenAICompatibleLLMService initialized: %s, model=%s", self.base_url, self.model_name)

    def _build_headers(self) -> dict[str, str]:
        """Build request headers for OpenAI-compatible APIs."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    

    
    def summarize(self, content: str, title: str, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate a summary using an OpenAI-compatible Chat Completions API.
        
        Args:
            content: The article content to summarize
            title: The article title
            url: The article URL
            
        Returns:
            Tuple of (success, summary, error)
        """
        try:
            logger.info("Requesting summary from LLM API for: %s...", title[:50])
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._build_headers(),
                json={
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a concise summarization assistant. Return only the summary text."
                        },
                        {
                            "role": "user",
                            "content": (
                                "Write a 3-5 sentence summary of this article. "
                                "Output only the summary sentences, nothing else.\n\n"
                                f"Title: {title}\n"
                                f"URL: {url}\n\n"
                                f"Article:\n{content}"
                            )
                        }
                    ]
                }
            )
            response.raise_for_status()
            result = response.json()
            # Extract summary from OpenAI-compatible chat completion response
            summary = ""
            choices = result.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                summary = (message.get("content") or "").strip()
            if not summary:
                logger.error("LLM API returned empty summary")
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
            logger.error("Connection error to LLM API: %s", e)
            return False, None, "Summarization service unavailable"
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error from LLM API: %d - %s", e.response.status_code, e.response.text)
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
        BaseLLMService instance
    """
    return OpenAICompatibleLLMService()
