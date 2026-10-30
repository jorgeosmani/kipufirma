import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("KIPUFIRMA_CONFIG_DIR", str(tmp_path / "cfg"))
    yield


@pytest.fixture(scope="session")
def pki():
    from helpers import FakeEcPKI
    return FakeEcPKI()


@pytest.fixture()
def trust(pki):
    from kipufirma.core.trust import TrustStore
    return TrustStore([pki.root])


@pytest.fixture()
def settings():
    from kipufirma.core.config import Settings
    s = Settings()
    s.security.revocation_policy = "desactivada"
    s.security.check_clock = False
    return s


@pytest.fixture()
def credential(pki, trust, tmp_path):
    from helpers import PASSWORD
    from kipufirma.core.certificate import load_credential
    from kipufirma.core.secrets import SecretBuffer
    p = tmp_path / "firma.p12"
    p.write_bytes(pki.p12())
    return load_credential(p, SecretBuffer(PASSWORD), trust)
