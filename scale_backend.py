import random
import time

# --- SIMULATION STATE ---
# We use these global variables to fake the "Tare" behavior
_current_offset = 0.0
_base_weight = 50.0  # Let's pretend there is 50kg on the scale

def get_live_weight():
    """
    Simulates reading from a hardware scale.
    Returns: Float (weight in kg)
    """
    # 1. Simulate a raw sensor reading with some noise/jitter
    # Real sensors always fluctuate slightly (e.g., 50.001, 49.999)
    jitter = random.uniform(-0.05, 0.05)
    raw_val = _base_weight + jitter
    
    # 2. Apply the "Tare" offset (Logic: Reading = Raw - Offset)
    final_weight = raw_val - _current_offset
    
    # 3. Handle near-zero negative numbers (common in real scales)
    if -0.05 < final_weight < 0.05:
        final_weight = 0.0
        
    return round(final_weight, 3)

def tare_scale():
    """
    Simulates the Tare/Zero button.
    It sets the current simulated weight as the new '0'.
    """
    global _current_offset
    # To tare, we set the offset equal to the current base weight (plus noise)
    jitter = random.uniform(-0.05, 0.05)
    _current_offset = _base_weight + jitter
    return True
