"""
simple moa client
"""
import enum
import json
import random
import time
from typing import Union

import redis
import yaml

LOOKUP_HOST_PROFILE_MAP = {
    "product": "moa_lookup.momo.com",
    "overseas": "moa_lookup_overseas.momo.com",
    "lab": "moa_lookup.momo.com",
    "pre_online": "test_moa_lookup.momo.com",
    "lab_pre_online": "test_moa_lookup.momo.com",
    "live_pre_online": "live_moa_test_lookup.momo.com",
    "beta": "moa_lookup.momo.com",
    "sandbox": "moa_lookup_sandbox.momo.com",
    "alpha": "moa_lookup_alpha.momo.com"
}
LOOK_UP_PORT = 10010


class StrEnum(str, enum.Enum):
    pass


class Env(StrEnum):
    product = "product"
    overseas = "overseas"
    lab = "lab"
    pre_online = "pre_online"
    lab_pre_online = "lab_pre_online"
    live_pre_online = "live_pre_online"
    beta = "beta"
    sandbox = "sandbox"
    alpha = "alpha"

    @property
    def lookup_address(self):
        return LOOKUP_HOST_PROFILE_MAP[self]


class MoaServiceError(Exception):
    pass


class MoaServiceConfigError(MoaServiceError):
    pass


class MoaServiceLookupError(MoaServiceError):
    pass


class _LookupClient:
    def __init__(self, host=None, port=None, expire=5):
        self.host = host or LOOKUP_HOST_PROFILE_MAP["product"]
        self.port = port or LOOK_UP_PORT
        self.expire = expire
        self.look_up_cache = {}
        self.look_up_expire = {}

    def update_uri_hosts(self, uri) -> list:
        try:
            print("self.host", self.host)
            _cli = redis.Redis(host=self.host, port=self.port)
            query_params = {
                "action": "/service/lookup",
                "params": {"m": "getService", "args": [uri, "redis"]},
            }
            raw_result = _cli.get(json.dumps(query_params))
            print("raw_result:", raw_result)
        except Exception as e:
            raise MoaServiceLookupError(f"Moa service lookup error on req: {e!r}") from e

        service_hosts = []
        try:
            result = json.loads(raw_result)
            assert result["ec"] == 0, "lookup failed: ec not 0"
            hosts = result["result"]["hosts"]
            print("hosts:", hosts)
            for raw_host in hosts:
                host_port = raw_host.split("?", 1)[0]
                host, port = host_port.split(":")
                item_host = {"host": host, "port": port}
                service_hosts.append(item_host)
            print("service_hosts:", service_hosts)
        except (json.JSONDecodeError, KeyError, AssertionError, ValueError, TypeError) as e:
            raise MoaServiceLookupError(f"Moa service lookup error on parse result({raw_result!r}): {e!r}") from e
        self.look_up_cache[uri] = service_hosts
        self.look_up_expire[uri] = int(time.time())
        return service_hosts

    def get_uri_hosts(self, uri) -> list:
        last_time = self.look_up_expire.get(uri) or 0
        if int(time.time()) - last_time < self.expire:
            cached_hosts = self.look_up_cache[uri]
            if cached_hosts:
                return cached_hosts

        self.update_uri_hosts(uri)
        return self.look_up_cache[uri]


class MoaClient:

    Env = Env

    def __init__(self, uri=None, timeout=None, env: Union[str, Env, None] = None):
        self._uri = uri
        self.timeout = timeout
        host = ""
        if env is None:
            host = self.get_default_host_from_env()
        if not host:
            env = env or Env.product
            if isinstance(env, str):
                env = Env(env)
            host = env.lookup_address
        print("host:", host)
        self.lookup_client = _LookupClient(host=host)

    @staticmethod
    def get_default_host_from_env() -> str:
        try:
            file_path = "/etc/momo/env.yaml"
            with open(file_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)
            lookup_hosts = yaml_data["application"]["moa"]["lookup"]["default"]
            the_host = lookup_hosts[0]
            return the_host.split(":")[0]
        except (OSError, KeyError, IndexError, TypeError, yaml.YAMLError):
            return ""

    def get_service_conn(self, uri):
        """ 获取连接 """
        service_hosts = self.lookup_client.get_uri_hosts(uri)
        one_host = random.choice(service_hosts)
        return redis.Redis(host=one_host["host"], port=one_host["port"], socket_timeout=self.timeout)

    def req(self, method, args, uri=None):
        uri = uri or self._uri
        if not uri:
            raise MoaServiceConfigError("service uri is needed on moa request")

        uri_service = self.get_service_conn(uri)
        moa_req_params = {"action": uri, "params": {"m": method, "args": args}}
        raw_params = json.dumps(moa_req_params)
        try:
            raw_result = uri_service.get(raw_params)
            result = json.loads(raw_result)
            assert result["ec"] == 0, f"invalid ec,  detail: {result}"
            return result["result"]
        except Exception as e:
            raise MoaServiceError(f"Moa service[{uri}] request error by params [{raw_params}]: {e!r}") from e
