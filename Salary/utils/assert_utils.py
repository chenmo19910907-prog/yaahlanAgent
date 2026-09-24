import logging


class AssertUtils:
    @staticmethod
    def assert_and_log(condition, error_message, success_message=""):
        assert condition, error_message
        if success_message:
            logging.info(success_message)
