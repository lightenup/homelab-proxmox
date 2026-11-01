# Reads Hermes's built-in notes (MEMORY.md) for the one-shot import into the shared memory (spec
# 097 § 8). Run inside hermes_agent as the hermes user by tasks/main.yml, never as root on the
# host: the notes sit in the agent-writable data directory, so a symlink there must not reach a
# host file (PR #340 review). Prints the file base64-encoded, or nothing when it does not exist;
# exits non-zero for anything but a regular file at the expected path. Holds no secret.
import base64, os, stat, sys

path = sys.argv[1] if len(sys.argv) > 1 else "/opt/data/memories/MEMORY.md"
parent = os.path.dirname(path)
if os.path.realpath(parent) != parent:
    sys.exit(f"refusing: {parent} resolves elsewhere ({os.path.realpath(parent)})")
try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
except FileNotFoundError:
    sys.exit(0)
except OSError as e:  # ELOOP for a symlink, EACCES, ...
    sys.exit(f"refusing to read {path}: {e.strerror}")
with os.fdopen(fd, "rb") as f:
    if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
        sys.exit(f"refusing: {path} is not a regular file")
    sys.stdout.write(base64.b64encode(f.read()).decode())
