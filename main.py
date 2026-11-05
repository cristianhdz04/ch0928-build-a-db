import sys
from database import Database

# start the database
db = Database()

# read each command
for line in sys.stdin:
    command = line.strip()

    # skip empty lines
    if not command:
        continue

    # stop on exit
    if command.upper() == "EXIT":
        break

    # show command result
    print(db.execute(command), flush=True)
