"""Encryption utilities for sensitive data."""
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from src.config import settings

load_dotenv()

# Initialize Fernet cipher
cipher = Fernet(settings.encryption_key.encode())


def encrypt_token(token: str) -> str:
    """
    Encrypt a GitHub personal access token.
    
    Args:
        token: Plain text GitHub PAT
        
    Returns:
        Encrypted token as base64 string
    """
    encrypted = cipher.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a GitHub personal access token.
    
    Args:
        encrypted_token: Encrypted token as base64 string
        
    Returns:
        Plain text GitHub PAT
    """
    decrypted = cipher.decrypt(encrypted_token.encode())
    return decrypted.decode()
