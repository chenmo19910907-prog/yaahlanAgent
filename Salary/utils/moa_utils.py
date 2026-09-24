import logging

from momoKit.moa import MoaClient

logger = logging.getLogger(__name__)


class MoaUtils:
    @staticmethod
    def moa_request(uri="", method="", args=None, env="alpha"):
        if args is None:
            args = []
        moa_client = MoaClient(uri=uri, env=env)
        res = moa_client.req(method, args=args)
        logger.debug("moa_request uri=%s method=%s result=%s", uri, method, res)
        return res


if __name__ == "__main__":
    MoaUtils.moa_request()
