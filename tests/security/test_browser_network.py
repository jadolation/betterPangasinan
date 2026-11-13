import socket

import pytest

from scripts.browser_network import public_addresses


def test_public_addresses_rejects_mixed_private_answers():
    def resolver(*args, **kwargs):
        return [(socket.AF_INET, 0, 0, '', (ip, 443)) for ip in ['8.8.8.8', '127.0.0.1']]
    with pytest.raises(ValueError):
        public_addresses('psa.gov.ph', resolver)


def test_public_addresses_is_deterministic_and_requires_answers():
    assert public_addresses('psa.gov.ph', lambda *a, **k: [(2, 0, 0, '', ('8.8.8.8', 443))]) == ['8.8.8.8']
    with pytest.raises(ValueError):
        public_addresses('psa.gov.ph', lambda *a, **k: [])
