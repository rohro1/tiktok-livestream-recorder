# A simple in-memory tracker for user livestream statuses
statuses = {}

def update_status(username, online=False, current_duration=0, last_online=None):
    statuses[username] = {
        "online": online,
        "current_duration": current_duration,
        "last_online": last_online
    }

def get_all_statuses():
    return statuses
