"""LLM service for article summarization.

This module provides an abstraction layer for LLM services used to generate
article summaries. The design uses an abstract base class with concrete
implementations for different LLM providers.

Architecture:
- BaseLLMService: Abstract base class defining the interface
- OpenAICompatibleLLMService: Singleton implementation using OpenAI-compatible APIs
- get_llm_service(): Factory function to get the appropriate service instance

Concurrent Processing Upgrade Path:
To enable concurrent summarization (when moving from sequential to parallel processing):
1. Remove sleep delays from retry logic in processor.py
2. Add asyncio.Semaphore(max_concurrent_requests) to control provider limits
3. Convert synchronous calls to async/await pattern
4. Increase ThreadPoolExecutor max_workers in main.py startup_event()
5. Monitor provider latency and adjust max_concurrent_requests accordingly
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError
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
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model_name = settings.llm_model_name
        self.temperature = settings.llm_temperature
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=settings.llm_timeout,
        )
        self._initialized = True
        logger.info("LLMService initialized: %s, model=%s", self.base_url, self.model_name)
    

    
    def summarize(self, content: str, title: str, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate a summary using an OpenAI-compatible chat completion API.
        
        Args:
            content: The article content to summarize
            title: The article title
            url: The article URL
            
        Returns:
            Tuple of (success, summary, error)
        """
        try:
            prompt = (
                "Write a 3-5 sentence summary of this article. Output only the summary sentences, nothing else:\n\n"
                f"{content}"
            )
            logger.info("Requesting summary from LLM for: %s...", title[:50])
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You summarize web articles clearly and concisely.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=self.temperature,
                max_tokens=settings.llm_max_output_tokens,
            )
            choices = response.choices or []
            summary = (choices[0].message.content or "").strip() if choices else ""

            # Some "OpenAI-compatible" providers only fully support legacy
            # completions and can return empty chat content.
            if not summary:
                legacy = self.client.completions.create(
                    model=self.model_name,
                    prompt=prompt,
                    temperature=self.temperature,
                    max_tokens=settings.llm_max_output_tokens,
                )
                legacy_choices = legacy.choices or []
                summary = (legacy_choices[0].text or "").strip() if legacy_choices else ""

            if not summary:
                logger.error("LLM returned empty summary")
                return False, None, "Summarization service returned empty result"

            raw_summary = summary
            summary = self._clean_summary(summary)

            if not summary:
                # Be conservative: if cleanup over-filters valid output, keep
                # provider content instead of failing the summarization.
                logger.warning("LLM summary became empty after post-processing; using raw content")
                summary = raw_summary

            if len(summary) > settings.summary_max_length:
                logger.warning("Summary exceeded max length (%d > %d), truncating", len(summary), settings.summary_max_length)
                summary = summary[:settings.summary_max_length]

            summary = self._trim_incomplete_trailing_sentence(summary)

            logger.info("Summary generated successfully (%d chars)", len(summary))
            return True, summary, None

        except APITimeoutError:
            logger.error("Timeout while generating summary for: %s", url)
            return False, None, "Summarization service timeout"

        except APIConnectionError as e:
            logger.error("Connection error to LLM service: %s", e)
            return False, None, "Summarization service unavailable"

        except APIStatusError as e:
            status = getattr(e, "status_code", "unknown")
            logger.error("HTTP error from LLM provider: %s - %s", status, str(e))
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
            if re.match(r"^(summary:|here( is| are)? (a|the|an|\d+) (summary|sentence|key|main)( sentence)?s?:?|in summary:|to summarize:|conclusion:|key points:|main points:|highlights:|takeaways:|tl;dr:)", line, re.IGNORECASE):
                continue
            # Remove lines that are just markdown bullets or numbers
            if re.match(r"^[-*\d. ]+$", line):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _trim_incomplete_trailing_sentence(self, summary: str) -> str:
        """Trim trailing partial sentence if output appears cut off."""
        text = (summary or "").strip()
        if not text:
            return text

        if text.endswith((".", "!", "?")):
            return text

        last_period = text.rfind(".")
        last_bang = text.rfind("!")
        last_q = text.rfind("?")
        last_end = max(last_period, last_bang, last_q)

        # Keep original if no sentence boundary exists yet.
        if last_end == -1:
            return text

        trimmed = text[: last_end + 1].strip()
        return trimmed or text


def get_llm_service() -> BaseLLMService:
    """
    Get the LLM service instance.
    
    Returns:
        BaseLLMService instance (currently OpenAICompatibleLLMService)
    """
    return OpenAICompatibleLLMService()
