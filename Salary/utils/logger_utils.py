import logging


class LogUtils(object):
    def __init__(self):
        pass

    def sys_log_info(self, title, log):
        title1 = "【" + title + "】"
        logging.debug(title1 + log)
