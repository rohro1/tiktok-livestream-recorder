import os
import subprocess

def git_commit_push():
    # Stage changes in recordings folder
    subprocess.run(["git", "add", "recordings", "usernames.txt"])
    # Check if there are changes
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        subprocess.run(["git", "commit", "-m", "Auto-update TikTok recordings"])
        subprocess.run(["git", "push"])
        print("New recordings committed and pushed.")
    else:
        print("No changes to commit.")

if __name__ == "__main__":
    git_commit_push()
