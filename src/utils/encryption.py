"""Encryption utilities for sensitive data."""
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Get encryption key from environment
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY environment variable not set")

# Initialize Fernet cipher
cipher = Fernet(ENCRYPTION_KEY.encode())


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
