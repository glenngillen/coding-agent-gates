def test_register_and_get(api):
    created = api.customers.handle_register({"customer_id": "c1", "name": "Ada", "email": "a@x.io"})
    assert created.status == 201
    assert api.customers.handle_get("c1").body == {"customer_id": "c1", "name": "Ada",
                                                   "email": "a@x.io", "tier": "standard"}


def test_duplicate_customer_conflicts(api):
    api.customers.handle_register({"customer_id": "c1", "name": "Ada", "email": "a@x.io"})
    assert api.customers.handle_register({"customer_id": "c1", "name": "B", "email": "b@x.io"}).status == 409


def test_invalid_registration(api):
    assert api.customers.handle_register({"customer_id": "", "name": "A", "email": "a@x.io"}).status == 400
    assert api.customers.handle_register({"customer_id": "c", "name": "A", "email": "a@x.io",
                                          "tier": "platinum"}).status == 400


def test_unknown_customer(api):
    assert api.customers.handle_get("nobody").status == 404
