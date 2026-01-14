import sys

for i in range(1000):
    sys.stdout.write(f"out-{i}\n")

for i in range(1000):
    sys.stderr.write(f"err-{i}\n")
