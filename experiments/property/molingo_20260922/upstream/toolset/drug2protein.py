from toolset.uniprotID2name import uniprotID2name
from toolset.call_gpt import gpt_api
import json
import re
import time

def clean_gpt_dict(text: str):
    """
    Extract a JSON-like dictionary from GPT output safely.
    """
    # Remove code fences and markdown
    text = re.sub(r"```(?:python)?|```", "", text, flags=re.IGNORECASE).strip()
    
    # Try to extract {...} block
    match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if match:
        text = match.group(1)
    else:
        raise ValueError("No dictionary found in GPT output")
    
    # Replace Python-style None with null for JSON
    text = text.replace("None", "null")
    
    return json.loads(text)

def normalize_name(name: str):
    """
    Normalize names for matching: lowercase, remove hyphens.
    """
    return name.replace('-', '').replace('‑', '').lower()

def drug2protein_(molecule_name: str):
    # Prompt GPT for protein targets
    prompt = (
        f"What are the protein targets of {molecule_name}? "
        "Find all UniProt IDs of them. "
        "Return the result as a dictionary only, using this template: "
        "{protein_name: uniprot_id}"
    )
    res1 = gpt_api(prompt)
    
    # Prompt GPT to cleanly extract the dictionary
    prompt2 = f"Extract only the Python dictionary from this text: {res1}"
    res2 = gpt_api(prompt2)

    # Parse dictionary safely
    try:
        raw_dict = clean_gpt_dict(res2)
    except Exception as e:
        print("Failed to parse GPT dictionary:", e)
        return None
    
    # Validate and normalize results
    res_ = {}
    for k, v in raw_dict.items():
        try:
            gt = normalize_name(uniprotID2name(v))
            y = normalize_name(k)
            if y in gt or gt in y:
                res_[v] = k
        except Exception:
            continue  # skip invalid IDs
    
    return res_

def drug2protein(molecule_name: str, retries: int = 3, delay: float = 1.0):
    """
    Retry wrapper to make the function more robust.
    """
    for attempt in range(retries):
        try:
            result = drug2protein_(molecule_name)
            if result is not None:
                return result
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(delay)  # small delay between retries
    return None