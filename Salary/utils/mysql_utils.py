import logging
import re

import pymysql
from multipledispatch import dispatch

logger = logging.getLogger(__name__)

# 仅允许常见安全字符的数据库名（供 USE 切换），避免任意字符串拼接
_DB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


class MySQLUtils:
    def __init__(self, host, user, password, database, port):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.connection = None

    def connect(self):
        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except pymysql.MySQLError as e:
            logger.error("Error connecting to MySQL: %s", e)
            self.connection = None

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def switch_database(self, db_name):
        if not _DB_NAME_PATTERN.match(db_name):
            raise ValueError("invalid database name for USE: %r" % (db_name,))
        if self.connection:
            with self.connection.cursor() as cursor:
                cursor.execute("USE %s" % db_name)
            logger.info("Switched to database: %s", db_name)
        else:
            raise ConnectionError("No active database connection")

    def execute_query(self, query, params=None):
        result = None
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchall()
            self.connection.commit()
        except pymysql.MySQLError as e:
            logger.error("Error executing query: %s", e)
        return result

    def execute_update(self, query, params=None):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
            self.connection.commit()
        except pymysql.MySQLError as e:
            logger.error("Error executing update: %s", e)
            self.connection.rollback()

    @dispatch(str)
    def insert(self, query):
        self.execute_update(query)

    @dispatch(str, tuple)
    def insert(self, query, params):
        self.execute_update(query, params)

    def update(self, query, params):
        self.execute_update(query, params)

    @dispatch(str)
    def delete(self, query):
        self.execute_update(query)

    @dispatch(str, tuple)
    def delete(self, query, params):
        self.execute_update(query, params)

    def select(self, query, params=None):
        return self.execute_query(query, params)


if __name__ == "__main__":
    import os

    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "test")
    port = int(os.environ.get("MYSQL_PORT", "3306"))

    db = MySQLUtils(host=host, user=user, password=password, database=database, port=port)
    db.connect()
    if db.connection:
        logger.info("connected")
        db.disconnect()
