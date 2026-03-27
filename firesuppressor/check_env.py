import sys
try:
    import huggingface_hub
    print(f"SUCCESS: huggingface_hub version {huggingface_hub.__version__} is available.")
except ImportError:
    print("ERROR: huggingface_hub is NOT installed in the current environment.")
    sys.exit(1)
