import argparse
import time
import os

parser = argparse.ArgumentParser()
parser.add_argument("-u", "--username", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

print(f"[SIMULATION] Recording {args.username} stream to {args.output}...")
time.sleep(10)
with open(args.output, "w") as f:
    f.write("FAKE VIDEO DATA")
print(f"[SIMULATION] Finished recording {args.username}.")