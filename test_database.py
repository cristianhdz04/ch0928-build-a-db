import os
import random
import tempfile
import unittest
from database import Database


class TestDatabase(unittest.TestCase):
    def test_database(self):
        # use temporary storage
        with tempfile.TemporaryDirectory() as folder:
            old = os.getcwd()
            try:
                os.chdir(folder)
                db = Database()

                # random number of cat treats
                treats = random.randint(10, 100)

                # test basic commands
                self.assertEqual(db.execute(f"SET cat_treats {treats}"), "OK")
                self.assertEqual(db.execute("GET cat_treats"), str(treats))
                self.assertEqual(db.execute("INCR cat_treats"), str(treats + 1))
                self.assertEqual(db.execute("EXISTS cat_treats"), "1")
                self.assertEqual(db.execute("GET missing_cat"), "")

                # test multiple cats
                luna_age = random.randint(1, 15)
                milo_age = random.randint(1, 15)

                db.execute(f"MSET luna {luna_age} milo {milo_age}")
                self.assertEqual(
                    db.execute("MGET luna milo"), f"{luna_age}\n{milo_age}"
                )

                # test cat information
                db.execute("HSET cat_profile name Whiskers")
                self.assertEqual(db.execute("HGET cat_profile name"), "Whiskers")

                # test cat toy list
                db.execute("LPUSH cat_toys yarn")
                db.execute("RPUSH cat_toys mouse")
                self.assertEqual(db.execute("LRANGE cat_toys 0 -1"), "yarn\nmouse\nEND")

                # test key ranges
                self.assertEqual(db.execute("RANGE luna milo"), "luna\nmilo\nEND")

                # test transaction rollback
                db.execute("BEGIN")
                db.execute("SET cat_nap sleeping")
                db.execute("ABORT")
                self.assertEqual(db.execute("GET cat_nap"), "")

                # test saved cat treats
                db = Database()
                self.assertEqual(db.execute("GET cat_treats"), str(treats + 1))

                # test clearing data
                db.execute("FLUSHDB")
                self.assertEqual(db.execute("GET cat_treats"), "")

            finally:
                # restore original directory
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
