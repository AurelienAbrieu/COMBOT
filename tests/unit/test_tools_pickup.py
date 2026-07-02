from src.com_chatbot import tools_pickup


class _DummyClient:
    def __init__(self, search_payload):
        self.search_payload = search_payload
        self.last_post_path = None
        self.last_post_body = None

    def get(self, path, params=None):
        assert path == "/api/tracking-parcel/parcels"
        return self.search_payload

    def post(self, path, json_body=None):
        self.last_post_path = path
        self.last_post_body = json_body
        return {"status": "accepted"}


def test_resend_pickup_code_posts_pinres_payload(monkeypatch):
    search_payload = {
        "data": [
            {
                "_source": {
                    "attributes": {
                        "logistician": {"code": "LODEMO", "name": "Demo Logistician"},
                        "expirationDate": "2026-07-07T08:50:50.577Z",
                        "parcelNumber": "1646015534",
                    },
                    "current": {
                        "event": {
                            "locker": {
                                "deviceCode": "DEMO00002",
                                "boxPath": "DEMO00002/H201708420131/1/1",
                                "boxAllocated": {"code": "LODEMO", "size": "M"},
                            }
                        }
                    },
                    "device": {"deviceCode": "DEMO00002"},
                }
            }
        ]
    }

    dummy_client = _DummyClient(search_payload=search_payload)
    monkeypatch.setattr(tools_pickup, "client", dummy_client)
    monkeypatch.setattr(tools_pickup, "_utc_now_iso_millis", lambda: "2026-07-02T10:58:14.933Z")

    message = tools_pickup.resend_pickup_code("1646015534")

    assert "has been resent" in message
    assert dummy_client.last_post_path == "/api/parcel_commands/add_event/PINRES"
    assert dummy_client.last_post_body == {
        "timestamp": "2026-07-02T10:58:14.933Z",
        "deviceCode": "DEMO00002",
        "logisticianCode": "LODEMO",
        "logisticianName": "Demo Logistician",
        "parcel": {"parcelNumber": "1646015534"},
        "boxPath": "DEMO00002/H201708420131/1/1",
        "boxAllocated": {"code": "LODEMO", "size": "M"},
        "pickupAllowedUntil": "2026-07-07T08:50:50.577Z",
    }


def test_resend_pickup_code_fails_when_payload_is_missing_required_fields(monkeypatch):
    search_payload = {
        "data": [
            {
                "_source": {
                    "attributes": {
                        "logistician": {"code": "LODEMO", "name": "Demo Logistician"},
                        "expirationDate": "2026-07-07T08:50:50.577Z",
                    },
                    "current": {
                        "event": {
                            "locker": {
                                "deviceCode": "DEMO00002",
                                "boxAllocated": {"code": "LODEMO", "size": "M"},
                            }
                        }
                    },
                }
            }
        ]
    }

    dummy_client = _DummyClient(search_payload=search_payload)
    monkeypatch.setattr(tools_pickup, "client", dummy_client)

    message = tools_pickup.resend_pickup_code("1646015534")

    assert message.startswith("Error: failed to build PINRES payload")
    assert dummy_client.last_post_path is None
