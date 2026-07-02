import base64
import json
import os
import threading

from dotenv import load_dotenv
import requests

from .app_logging import get_component_logger
from .request_context import get_web_session_key


PMD_LOGGER = get_component_logger("pmd", "pmd_api.log")
PMD_LOG_VERBOSE_PAYLOADS_ENV = "PMD_LOG_VERBOSE_PAYLOADS"
PMD_LOG_MAX_BODY_CHARS_DEFAULT = 4000


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class PMDClientError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


class PMDClient:
    def __init__(self, base_url, login=None, password=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.login = (login or "").strip()
        self.password = password or ""
        self.organization_id = None
        self._is_authenticated = False
        self._session = requests.Session()
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _extract_token_from_login_response(self, payload):
        if not isinstance(payload, dict):
            return None
        candidate_keys = ["token", "jwt", "accessToken", "idToken"]
        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        for container in ["data", "auth", "result", "payload"]:
            node = payload.get(container)
            if isinstance(node, dict):
                for key in candidate_keys:
                    value = node.get(key)
                    if isinstance(value, str) and value:
                        return value
        return None

    def _extract_organization_id(self, jwt_token):
        try:
            payload = jwt_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            return decoded["organizationId"]
        except Exception as e:
            raise PMDClientError(500, f"Unable to parse organizationId from JWT payload: {e}")

    def _authenticate(self, login, password):
        response = self._request(
            "POST",
            "/api/login",
            json_body={"login": login, "password": password},
            headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
        )
        body = response.json() if response.text else {}
        token = self._extract_token_from_login_response(body)
        if not token:
            raise PMDClientError(response.status_code, f"Login succeeded but no token found in response: {body}")
        return token

    def _refresh_authentication(self):
        if not self.login or not self.password:
            raise PMDClientError(401, "Missing PMD credentials for authentication")
        jwt_token = self._authenticate(login=self.login, password=self.password)
        self.headers["Authorization"] = f"Bearer {jwt_token}"
        self.organization_id = self._extract_organization_id(jwt_token)
        self._is_authenticated = True

    def login_with_credentials(self, login, password):
        self.login = (login or "").strip()
        self.password = password or ""
        self._refresh_authentication()

    def logout(self):
        self.headers.pop("Authorization", None)
        self.organization_id = None
        self._is_authenticated = False
        self.login = ""
        self.password = ""

    @property
    def is_authenticated(self):
        has_auth_header = bool(self.headers.get("Authorization"))
        return self._is_authenticated and has_auth_header

    _SENSITIVE_KEYS = frozenset({
        "password", "pwd", "pass", "token", "jwt",
        "accesstoken", "idtoken", "refreshtoken",
        "authorization", "apikey", "api_key", "secret",
        "pincode", "pin", "accesscode", "access_code",
    })

    def _redact_sensitive_data(self, value):
        sensitive_keys = self._SENSITIVE_KEYS
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if isinstance(key, str) and key.lower() in sensitive_keys:
                    redacted[key] = "***redacted***"
                else:
                    redacted[key] = self._redact_sensitive_data(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_sensitive_data(item) for item in value]
        return value

    def _sanitize_json_body(self, json_body):
        return self._redact_sensitive_data(json_body)

    def _sanitize_log_value(self, value):
        sanitized = self._redact_sensitive_data(value)
        if isinstance(sanitized, str):
            return self._truncate_for_log(sanitized)
        try:
            serialized = json.dumps(sanitized, default=str, sort_keys=True)
        except (TypeError, ValueError):
            serialized = str(sanitized)
        return self._truncate_for_log(serialized)

    def _sanitize_response_text(self, response_text):
        if not response_text:
            return response_text
        try:
            parsed = json.loads(response_text)
        except ValueError:
            return self._truncate_for_log(response_text)
        return self._sanitize_log_value(parsed)

    def _truncate_for_log(self, text):
        if not isinstance(text, str):
            return text
        max_body_chars = PMD_LOG_MAX_BODY_CHARS_DEFAULT
        configured_max = os.environ.get("PMD_LOG_MAX_BODY_CHARS", str(PMD_LOG_MAX_BODY_CHARS_DEFAULT))
        try:
            max_body_chars = max(500, int(configured_max))
        except (TypeError, ValueError):
            max_body_chars = max(500, PMD_LOG_MAX_BODY_CHARS_DEFAULT)
        # Keep one-line logs readable even when payloads contain line breaks.
        text = text.replace("\r", "\\r").replace("\n", "\\n")
        if len(text) <= max_body_chars:
            return text
        truncated_chars = len(text) - max_body_chars
        return f"{text[:max_body_chars]}... [truncated {truncated_chars} chars]"

    def _verbose_payload_logging_enabled(self):
        return _env_bool(PMD_LOG_VERBOSE_PAYLOADS_ENV, default=False)

    def _format_request_metadata(self, params=None, json_body=None):
        metadata = []
        if params:
            if isinstance(params, dict):
                metadata.append(f"param_count={len(params)}")
                metadata.append(f"params={self._sanitize_log_value(params)}")
            else:
                metadata.append(f"params_type={type(params).__name__}")
        if json_body is not None:
            if isinstance(json_body, dict):
                metadata.append(f"body_fields={len(json_body)}")
            elif isinstance(json_body, list):
                metadata.append(f"body_items={len(json_body)}")
            else:
                metadata.append(f"body_type={type(json_body).__name__}")
        if not metadata:
            return ""
        return " " + " ".join(metadata)

    def _format_response_metadata(self, response_text):
        if not response_text:
            return " payload=empty chars=0"
        metadata = [f"payload={self._sanitize_response_text(response_text)}", f"chars={len(response_text)}"]
        try:
            parsed = json.loads(response_text)
        except ValueError:
            metadata.append("format=text")
        else:
            metadata.append("format=json")
            if isinstance(parsed, list):
                metadata.append(f"top_level_items={len(parsed)}")
            else:
                metadata.append(f"top_level_type={type(parsed).__name__}")
        return " " + " ".join(metadata)

    def _log_request(self, method, path, params=None, json_body=None):
        req = self._format_request_metadata(params=params, json_body=json_body)
        if self._verbose_payload_logging_enabled():
            req = ""
            if params:
                req += f" params={self._sanitize_log_value(params)}"
            if json_body is not None:
                req += f" body={self._sanitize_log_value(self._sanitize_json_body(json_body))}"
        PMD_LOGGER.info("REQ  %s %s%s", method, path, req)

    def _log_response(self, method, path, status_code, response_text):
        if self._verbose_payload_logging_enabled():
            PMD_LOGGER.info("RESP %s %s -> %s %s", method, path, status_code, self._sanitize_response_text(response_text))
            return
        PMD_LOGGER.info("RESP %s %s -> %s%s", method, path, status_code, self._format_response_metadata(response_text))

    def _request(self, method, path, params=None, json_body=None, headers=None):
        req_headers = headers if headers is not None else self.headers
        if path != "/api/login" and headers is None and not self.is_authenticated:
            raise PMDClientError(401, "PMD session is not authenticated")
        self._log_request(method, path, params=params, json_body=json_body)
        url = path if isinstance(path, str) and path.startswith(("http://", "https://")) else f"{self.base_url}{path}"
        allow_retry = headers is None and path != "/api/login" and bool(self.login and self.password)

        def send_request(active_headers):
            return self._session.request(
                method=method,
                url=url,
                headers=active_headers,
                params=params,
                json=json_body,
                timeout=self.timeout,
            )

        try:
            response = send_request(req_headers)
        except requests.RequestException as e:
            self._log_response(method, path, "NETWORK_ERROR", str(e))
            raise PMDClientError(0, f"Network error: {e}")

        if response.status_code == 401 and allow_retry:
            self._log_response(method, path, response.status_code, response.text)
            self._refresh_authentication()
            req_headers = self.headers
            self._log_request(method, path, params=params, json_body=json_body)
            try:
                response = send_request(req_headers)
            except requests.RequestException as e:
                self._log_response(method, path, "NETWORK_ERROR", str(e))
                raise PMDClientError(0, f"Network error: {e}")

        self._log_response(method, path, response.status_code, response.text)
        if not response.ok:
            raise PMDClientError(response.status_code, response.text)
        return response

    def get(self, path, params=None):
        r = self._request("GET", path, params=params)
        return r.json()

    def post(self, path, json_body=None):
        r = self._request("POST", path, json_body=json_body)
        if not r.text:
            return {"status": "accepted"}
        try:
            return r.json()
        except ValueError:
            body = r.text.strip()
            if len(body) == 36:
                return {"id": body}
            return {"raw": body}

    def delete(self, path):
        r = self._request("DELETE", path)
        return r.json() if r.text else {"status": "accepted"}

    def put(self, path, json_body=None):
        r = self._request("PUT", path, json_body=json_body)
        if not r.text:
            return {"status": "accepted"}
        try:
            return r.json()
        except ValueError:
            body = r.text.strip()
            if len(body) == 36:
                return {"id": body}
            return {"raw": body}


class _SessionAwarePMDClientRegistry:
    def __init__(self, default_client: PMDClient):
        self._default_client = default_client
        self._clients_by_web_session_key: dict[str, PMDClient] = {}
        self._lock = threading.Lock()

    @property
    def default_client(self) -> PMDClient:
        return self._default_client

    def get_client(self, web_session_key: str, create: bool = True) -> PMDClient | None:
        resolved_key = (web_session_key or "").strip()
        if not resolved_key:
            return self._default_client
        with self._lock:
            client = self._clients_by_web_session_key.get(resolved_key)
            if client is None and create:
                client = PMDClient(
                    base_url=self._default_client.base_url,
                    timeout=self._default_client.timeout,
                )
                self._clients_by_web_session_key[resolved_key] = client
            return client

    def logout_client(self, web_session_key: str) -> None:
        resolved_key = (web_session_key or "").strip()
        if not resolved_key:
            self._default_client.logout()
            return
        with self._lock:
            client = self._clients_by_web_session_key.pop(resolved_key, None)
        if client is not None:
            client.logout()

    def reset_web_clients(self) -> None:
        with self._lock:
            clients = list(self._clients_by_web_session_key.values())
            self._clients_by_web_session_key.clear()
        for client in clients:
            client.logout()


def get_active_client(create: bool = True) -> PMDClient:
    web_session_key = get_web_session_key()
    active_client = _CLIENT_REGISTRY.get_client(web_session_key, create=create)
    return active_client or _CLIENT_REGISTRY.default_client


def get_default_client() -> PMDClient:
    return _CLIENT_REGISTRY.default_client


def reset_web_session_clients() -> None:
    _CLIENT_REGISTRY.reset_web_clients()


class PMDClientProxy:
    @property
    def is_authenticated(self):
        active_client = _CLIENT_REGISTRY.get_client(get_web_session_key(), create=False)
        if active_client is None:
            return False
        return active_client.is_authenticated

    @property
    def organization_id(self):
        active_client = _CLIENT_REGISTRY.get_client(get_web_session_key(), create=False)
        if active_client is None:
            return None
        return active_client.organization_id

    def login_with_credentials(self, login, password):
        return get_active_client(create=True).login_with_credentials(login, password)

    def logout(self):
        return _CLIENT_REGISTRY.logout_client(get_web_session_key())

    def get(self, path, *args, **kwargs):
        return get_active_client(create=True).get(path, *args, **kwargs)

    def post(self, path, *args, **kwargs):
        return get_active_client(create=True).post(path, *args, **kwargs)

    def put(self, path, *args, **kwargs):
        return get_active_client(create=True).put(path, *args, **kwargs)

    def delete(self, path, *args, **kwargs):
        return get_active_client(create=True).delete(path, *args, **kwargs)


load_dotenv()

from .settings import get_settings  # noqa: E402

_pmd_settings = get_settings()

_DEFAULT_CLIENT = PMDClient(
    base_url=_pmd_settings.pmd_api_base_url,
    login=_pmd_settings.pmd_login or None,
    password=_pmd_settings.pmd_password or None,
)

_CLIENT_REGISTRY = _SessionAwarePMDClientRegistry(_DEFAULT_CLIENT)

client = PMDClientProxy()
