import os
import tempfile

# Vor dem Import von app.settings setzen (Settings liest die Umgebung beim Import)
os.environ.setdefault("STORY_PROVIDER", "fake")
os.environ.setdefault("DEVICE_TOKEN", "test-token")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
