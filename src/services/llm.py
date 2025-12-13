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
import subprocess
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
            - success: True if summarization succeeded
            - summary: The generated summary text (max 2000 chars)
            - error: User-friendly error message if failed
        """
        pass


class OllamaLLMService(BaseLLMService):
    """Ollama LLM service implementation (singleton pattern)."""
    
    _instance: Optional['OllamaLLMService'] = None
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the service (only once due to singleton)."""
        if self._initialized:
            return
        
        self.client = httpx.Client(timeout=settings.llm_timeout)
        self.base_url = settings.llm_base_url
        self.model_name = settings.llm_model_name
        self.temperature = settings.llm_temperature
        self._initialized = True
        logger.info(f"OllamaLLMService initialized: {self.base_url}, model={self.model_name}")
    
    def _log_gpu_metrics(self, stage: str) -> None:
        """
        Log GPU metrics using nvidia-smi.
        
        Args:
            stage: Description of the current stage (e.g., "before_summarization")
        """
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total,temperature.gpu,power.draw', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                metrics = result.stdout.strip()
                logger.info(f"GPU metrics ({stage}): {metrics}")
            else:
                logger.warning(f"Failed to get GPU metrics ({stage}): {result.stderr}")
        except Exception as e:
            logger.warning(f"Error getting GPU metrics ({stage}): {e}")
    
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
        # Log GPU metrics before summarization
        self._log_gpu_metrics("before_summarization")
        
        try:
            # Build the prompt
            prompt = f"Summarize the following article in 3-5 concise sentences, focusing on key points and main ideas:\n\n{content}"
            
            # Make request to Ollama API
            logger.info(f"Requesting summary from Ollama for: {title[:50]}...")
            
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
            
            # Truncate if needed (should not happen with good prompts)
            if len(summary) > settings.summary_max_length:
                logger.warning(f"Summary exceeded max length ({len(summary)} > {settings.summary_max_length}), truncating")
                summary = summary[:settings.summary_max_length]
            
            # Log GPU metrics after summarization
            self._log_gpu_metrics("after_summarization")
            
            logger.info(f"Summary generated successfully ({len(summary)} chars)")
            return True, summary, None
            
        except httpx.TimeoutException:
            logger.error(f"Timeout while generating summary for: {url}")
            self._log_gpu_metrics("after_timeout")
            return False, None, "Summarization service unavailable"
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Ollama: {e.response.status_code} - {e.response.text}")
            self._log_gpu_metrics("after_http_error")
            return False, None, "Summarization service unavailable"
        
        except Exception as e:
            logger.error(f"Unexpected error during summarization: {e}", exc_info=True)
            self._log_gpu_metrics("after_error")
            return False, None, "Content not suitable for summarization"


def get_llm_service() -> BaseLLMService:
    """
    Get the LLM service instance.
    
    Returns:
        BaseLLMService instance (currently OllamaLLMService)
    """
    return OllamaLLMService()
