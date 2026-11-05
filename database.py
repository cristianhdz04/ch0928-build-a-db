import json
import os
import time


class Database:
    """persistent key-value store with a list-based index."""

    def __init__(self):
        self.data = []
        self.pending = None
        self.backup = None
        self.file = "data.db"

        # make sure file exists
        open(self.file, "a").close()

        # recover saved operations.
        with open(self.file) as f:
            transaction = None
            for line in f:
                try:
                    op = json.loads(line)
                    # track unfinished transactions
                    if op[0] == "BEGIN":
                        transaction = []
                    elif op[0] == "COMMIT":
                        if transaction is not None:
                            for item in transaction:
                                self.apply(item)
                        transaction = None
                    elif transaction is not None:
                        transaction.append(op)
                    else:
                        self.apply(op)
                except (ValueError, IndexError, TypeError):
                    pass

    def find(self, key):
        """find a key and remove it if expired."""
        for item in self.data:
            if item[0] == key:
                # clear expired keys
                if item[3] is not None and item[3] <= time.time():
                    self.data.remove(item)
                    return None
                return item
        return None

    def apply(self, op):
        """apply an operation to the in-memory index."""
        # update stored data
        if op[0] == "FLUSHDB":
            self.data.clear()
        elif op[0] == "DEL":
            self.data = [x for x in self.data if x[0] != op[1]]
        elif op[0] == "SET":
            self.data = [x for x in self.data if x[0] != op[1]]
            self.data.append(op[1:])

    def write(self, operations):
        """append operations to disk."""
        with open(self.file, "a") as f:
            for op in operations:
                f.write(json.dumps(op) + "\n")
            f.flush()
            # save changes safely
            os.fsync(f.fileno())

    def save(self, op):
        """save immediately or queue inside a transaction."""
        if self.pending is None:
            self.write([op])
        else:
            self.pending.append(op)
        self.apply(op)

    def execute(self, line):
        """execute a database command."""
        parts = line.split()
        if not parts:
            return ""

        # read the command
        cmd = parts[0].upper()
        a = parts[1:]
        result = "OK"

        try:
            if cmd == "SET":
                self.save(["SET", a[0], "str", a[1], None])

            elif cmd == "GET":
                x = self.find(a[0])
                result = x[2] if x and x[1] == "str" else ""

            elif cmd == "DEL":
                x = self.find(a[0])
                self.save(["DEL", a[0]])
                result = "1" if x else "0"

            elif cmd == "EXISTS":
                result = "1" if self.find(a[0]) else "0"

            # handle multiple keys
            elif cmd == "MSET":
                if not a or len(a) % 2:
                    raise ValueError()
                for i in range(0, len(a), 2):
                    self.save(["SET", a[i], "str", a[i + 1], None])

            elif cmd == "MGET":
                result = "\n".join(
                    x[2] if (x := self.find(k)) and x[1] == "str" else "nil" for k in a
                )

            # set key expiration
            elif cmd == "EXPIRE":
                x = self.find(a[0])
                result = "0"
                seconds = int(a[1])
                if x:
                    if seconds <= 0:
                        self.save(["DEL", a[0]])
                    else:
                        self.save(["SET", x[0], x[1], x[2], time.time() + seconds])
                    result = "1"

            elif cmd == "TTL":
                x = self.find(a[0])
                result = str(
                    -2
                    if not x
                    else -1 if x[3] is None else max(0, int(x[3] - time.time()))
                )

            # list matching keys
            elif cmd == "RANGE":
                start = a[0]
                end = a[1] if len(a) > 1 else ""

                if end == '""':
                    end = ""

                keys = sorted(
                    x[0]
                    for x in self.data[:]
                    if x[0] >= start and (not end or x[0] <= end) and self.find(x[0])
                )
                result = "\n".join(keys + ["END"])

            # start a transaction
            elif cmd == "BEGIN":
                if self.pending is not None:
                    result = "ERROR"
                else:
                    self.backup = json.dumps(self.data)
                    self.pending = []

            elif cmd == "COMMIT":
                if self.pending is None:
                    result = "ERROR"
                else:
                    self.write([["BEGIN"]] + self.pending + [["COMMIT"]])
                    self.pending = None
                    self.backup = None

            elif cmd == "ABORT":
                if self.pending is None:
                    result = "ERROR"
                else:
                    self.data = json.loads(self.backup)
                    self.pending = None
                    self.backup = None

            # work with hashes
            elif cmd == "HSET":
                x = self.find(a[0])
                if x and x[1] != "hash":
                    return "ERROR"

                fields = [v[:] for v in x[2]] if x else []
                old = next((v for v in fields if v[0] == a[1]), None)

                if old:
                    fields.remove(old)

                fields.append([a[1], a[2]])
                expiry = x[3] if x else None

                self.save(["SET", a[0], "hash", fields, expiry])
                result = "0" if old else "1"

            elif cmd == "HGET":
                x = self.find(a[0])
                result = "nil"

                if x and x[1] == "hash":
                    for k, v in x[2]:
                        if k == a[1]:
                            result = v
                            break

            elif cmd == "HGETALL":
                x = self.find(a[0])
                result = (
                    " ".join(v for pair in sorted(x[2]) for v in pair)
                    if x and x[1] == "hash"
                    else "nil"
                )

            # add list items
            elif cmd in ("LPUSH", "RPUSH"):
                x = self.find(a[0])
                if x and x[1] != "list":
                    return "ERROR"

                values = x[2][:] if x else []

                if cmd == "LPUSH":
                    values.insert(0, a[1])
                else:
                    values.append(a[1])

                expiry = x[3] if x else None
                self.save(["SET", a[0], "list", values, expiry])
                result = str(len(values))

            elif cmd in ("LPOP", "RPOP"):
                x = self.find(a[0])

                if not x or x[1] != "list" or not x[2]:
                    result = "ERROR"
                else:
                    values = x[2][:]
                    result = values.pop(0 if cmd == "LPOP" else -1)
                    self.save(["SET", a[0], "list", values, x[3]])

            elif cmd == "LRANGE":
                x = self.find(a[0])
                result = "END"

                if x and x[1] == "list":
                    values = x[2]
                    start = int(a[1])
                    stop = int(a[2])

                    if start < 0:
                        start += len(values)
                    if stop < 0:
                        stop += len(values)

                    start = max(0, start)
                    stop = min(len(values) - 1, stop)

                    selected = values[start : stop + 1] if start <= stop else []
                    result = "\n".join(selected + ["END"])

            # change number values
            elif cmd in ("INCR", "DECR"):
                x = self.find(a[0])

                if x and x[1] != "str":
                    return "ERROR"

                n = int(x[2]) if x else 0
                n += 1 if cmd == "INCR" else -1

                expiry = x[3] if x else None
                self.save(["SET", a[0], "str", str(n), expiry])
                result = str(n)

            elif cmd == "FLUSHDB":
                self.save(["FLUSHDB"])

            else:
                result = "ERROR"

        except (IndexError, ValueError, TypeError):
            result = "ERROR"

        return result
