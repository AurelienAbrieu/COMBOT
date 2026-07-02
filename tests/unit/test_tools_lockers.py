from src.com_chatbot import tools_lockers


class _DummyClient:
    def __init__(self, payload):
        self.payload = payload
        self.last_get_path = None
        self.last_get_params = None

    def get(self, path, params=None):
        self.last_get_path = path
        self.last_get_params = params or {}
        return self.payload


def _sample_device_hit(device_id="GBR20532", status="ACTIVE"):
    return {
        "_source": {
            "attributes": {
                "id": device_id,
                "status": status,
                "generation": "5",
                "installType": "INDOOR",
                "usage": "Open Network",
                "site": {
                    "name": "Museum Street",
                    "address": ["1 Museum Street"],
                    "city": "London",
                    "postCode": "WC1A 1JR",
                    "country": "United Kingdom",
                },
            }
        }
    }


def test_find_nearby_lockers_uses_city_filter_without_geo(monkeypatch):
    dummy_client = _DummyClient(payload={"data": [_sample_device_hit()], "total": 1})
    monkeypatch.setattr(tools_lockers, "client", dummy_client)

    message = tools_lockers.find_nearby_lockers(city="London", limit=10)

    assert "Found 1 accessible device" in message
    assert "city=London" in message
    assert dummy_client.last_get_path == "/api/tracking-device/devices"
    assert dummy_client.last_get_params == {
        "from": 0,
        "size": 10,
        "fterms_attributes.site.city": "London",
    }


def test_find_nearby_lockers_city_takes_precedence_over_coordinates(monkeypatch):
    dummy_client = _DummyClient(payload={"data": [_sample_device_hit()], "total": 1})
    monkeypatch.setattr(tools_lockers, "client", dummy_client)

    tools_lockers.find_nearby_lockers(city="London", latitude=51.5074, longitude=-0.1278, radius_km=5.0, limit=10)

    assert "fterms_attributes.site.city" in dummy_client.last_get_params
    assert "fgeo_attributes.site.coordinates" not in dummy_client.last_get_params


def test_find_nearby_lockers_coordinates_still_use_geo_filter(monkeypatch):
    dummy_client = _DummyClient(payload={"data": [_sample_device_hit()], "total": 1})
    monkeypatch.setattr(tools_lockers, "client", dummy_client)

    tools_lockers.find_nearby_lockers(latitude=51.5074, longitude=-0.1278, radius_km=5.0, limit=10)

    assert dummy_client.last_get_params["fgeo_attributes.site.coordinates"] == "51.5074,-0.1278_5.0_km"
    assert "fterms_attributes.site.city" not in dummy_client.last_get_params
