"""
FoxPro v2 Signature Algorithm

This module implements the FoxPro-compatible v2 keyed signature algorithm
for the signed launch URL validation.

Canonical string format:
MIS2|n|ln|dp|t|o|d|nonce|return

Normalization rules:
- Convert missing values to empty string
- Trim leading/trailing whitespace
- Replace pipe character `|` with a single space
- Replace CR/LF with a single space
- Trim again
- Do NOT lowercase canonical values (case is preserved)

v2 Signature algorithm:
- MOD = 2147483647
- For each character in text (1-based index i):
  a = ord(character)
  s = ord(secret[(i - 1) % len(secret)])
  h1 = ((h1 * 33) + a + s + i) % MOD
  h2 = ((h2 * 131) + (a * (s + 1)) + i) % MOD
  h3 = ((h3 * 257) + a + h1 + s) % MOD
- Signature format: V2-{h1:010d}-{h2:010d}-{h3:010d}
"""

import hashlib
import re
from datetime import datetime


# Algorithm constants
MOD = 2147483647  # 2^31 - 1 (Mersenne prime)
SIGNATURE_FORMAT = 'V2-{h1:010d}-{h2:010d}-{h3:010d}'

# Timestamp pattern: YYYYMMDDHHMMSS (14 characters)
TIMESTAMP_PATTERN = re.compile(r'^\d{14}$')


def foxpro_norm(value):
    """
    Normalize a value for FoxPro signature computation.
    
    Rules:
    - Convert None/missing to empty string
    - Convert to string
    - Trim leading/trailing whitespace
    - Replace pipe character `|` with a single space
    - Replace CR/LF with a single space
    - Trim again
    
    Args:
        value: The value to normalize (can be None, string, or any type)
        
    Returns:
        Normalized string
    """
    if value is None:
        value = ''
    value = str(value)
    value = value.strip()
    value = value.replace('|', ' ')
    # Handle CR/LF first - replace \r\n with single space, then individual \r and \n
    value = value.replace('\r\n', ' ')
    value = value.replace('\r', ' ')
    value = value.replace('\n', ' ')
    return value.strip()


def foxpro_canonical_v2(params):
    """
    Build the canonical string for v2 signature from URL parameters.
    
    Format: MIS2|n|ln|dp|t|o|d|nonce|return
    
    All values are normalized using foxpro_norm() before joining.
    
    Args:
        params: Dict-like object with get() method (e.g., request.GET)
        
    Returns:
        Canonical string for v2 signature
    """
    return '|'.join([
        'MIS2',
        foxpro_norm(params.get('n')),
        foxpro_norm(params.get('ln')),
        foxpro_norm(params.get('dp')),
        foxpro_norm(params.get('t')),
        foxpro_norm(params.get('o')),  # o is optional but included as empty if missing
        foxpro_norm(params.get('d')),
        foxpro_norm(params.get('nonce')),
        foxpro_norm(params.get('return')),
    ])


def foxpro_sign_v2(canonical, secret):
    """
    Compute the v2 signature for a canonical string.
    
    This implements the FoxPro-compatible v2 signature algorithm:
    - Initial hash values: h1=5381, h2=52711, h3=19349663
    - For each character at 1-based index i:
      a = ord(character)
      s = ord(secret[(i - 1) % len(secret)])
      h1 = ((h1 * 33) + a + s + i) % MOD
      h2 = ((h2 * 131) + (a * (s + 1)) + i) % MOD
      h3 = ((h3 * 257) + a + h1 + s) % MOD
    - Output: V2-{h1:010d}-{h2:010d}-{h3:010d}
    
    Args:
        canonical: The canonical string to sign
        secret: The shared secret (normalized before use)
        
    Returns:
        Signature in format V2-{h1:010d}-{h2:010d}-{h3:010d}
        
    Raises:
        ValueError: If secret is empty or invalid
    """
    if not secret:
        raise ValueError('FOXPRO_V2_SECRET is required')
    
    # Normalize the secret (same rules as params)
    secret = foxpro_norm(secret)
    if not secret:
        raise ValueError('FOXPRO_V2_SECRET is required')
    
    # Build the text to hash: MIS-SIGN-V2|secret|canonical|secret
    text = f'MIS-SIGN-V2|{secret}|{foxpro_norm(canonical)}|{secret}'
    
    # Initialize hash accumulators
    h1 = 5381
    h2 = 52711
    h3 = 19349663
    
    # Process each character with 1-based indexing
    for i, ch in enumerate(text, start=1):
        a = ord(ch)
        s = ord(secret[(i - 1) % len(secret)])
        
        h1 = ((h1 * 33) + a + s + i) % MOD
        h2 = ((h2 * 131) + (a * (s + 1)) + i) % MOD
        h3 = ((h3 * 257) + a + h1 + s) % MOD
    
    return SIGNATURE_FORMAT.format(h1=h1, h2=h2, h3=h3)


def validate_timestamp(timestamp_str):
    """
    Validate that a timestamp string is in YYYYMMDDHHMMSS format.
    
    Args:
        timestamp_str: The timestamp string to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not timestamp_str or not TIMESTAMP_PATTERN.match(timestamp_str):
        return False
    
    try:
        datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
        return True
    except ValueError:
        return False


def parse_timestamp(timestamp_str):
    """
    Parse a timestamp string in YYYYMMDDHHMMSS format.
    
    Args:
        timestamp_str: The timestamp string to parse
        
    Returns:
        datetime object if valid, None otherwise
    """
    if not validate_timestamp(timestamp_str):
        return None
    
    try:
        return datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
    except ValueError:
        return None


def hash_nonce(nonce):
    """
    Compute SHA-256 hash of a nonce for storage.
    
    Args:
        nonce: The nonce string to hash
        
    Returns:
        SHA-256 hash as hex string
    """
    return hashlib.sha256(nonce.encode()).hexdigest()


def is_ip_allowed(client_ip, allowed_ips):
    """
    Check if a client IP is in the allowed list or CIDR ranges.
    
    Args:
        client_ip: The client IP address string
        allowed_ips: List of IP addresses or CIDR ranges
        
    Returns:
        True if allowed, False otherwise
    """
    import ipaddress
    
    if not allowed_ips:
        return True  # No restriction if list is empty
    
    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    
    for allowed in allowed_ips:
        try:
            # Try as network (CIDR)
            if '/' in allowed:
                network = ipaddress.ip_network(allowed, strict=False)
                if client_ip_obj in network:
                    return True
            else:
                # Try as exact IP
                if client_ip_obj == ipaddress.ip_address(allowed):
                    return True
        except ValueError:
            continue
    
    return False