"""Authorization boundaries for monitoring credentials and sensitive backups."""

import pytest
from app.app_factory import create_app, default_module_loader_factory
from app.config import ConfigManager
from app.storage import SnapshotStorage


@pytest.fixture
def secured_app(tmp_path):
    config = ConfigManager(str(tmp_path))
    config.save({'admin_password': 'synthetic-admin', 'modem_password': 'synthetic-modem',
                 'modem_type': 'sagemcom', 'metrics_require_token': True})
    storage = SnapshotStorage(str(tmp_path / 'docsis_history.db'), max_days=7)
    app = create_app(config_manager=config, storage=storage, environ={}, testing=True,
                     module_loader_factory=default_module_loader_factory(config, search_paths=[]))
    return app, storage


@pytest.mark.parametrize('method,path', [('POST', '/api/backup'), ('POST', '/api/backup/scheduled'),
    ('GET', '/api/backup/list'), ('DELETE', '/api/backup/test.tar.gz'),
    ('POST', '/api/restore'), ('POST', '/api/restore/validate'), ('GET', '/api/browse')])
def test_api_tokens_cannot_access_backup_operations(secured_app, method, path):
    app, storage = secured_app
    _, token = storage.create_api_token('integration')
    response = app.test_client().open(path, method=method,
                                     headers={'Authorization': 'Bearer ' + token})
    assert response.status_code in (302, 403)


def test_browser_admin_can_download_and_validate_backups(secured_app):
    import io
    app, _ = secured_app
    client = app.test_client()
    client.get('/login')
    with client.session_transaction() as session:
        csrf = session['login_csrf_token']
    assert client.post('/login', data={'password': 'synthetic-admin', 'csrf_token': csrf}).status_code == 302
    backup = client.post('/api/backup')
    assert backup.status_code == 200
    validation = client.post('/api/restore/validate', data={'file': (io.BytesIO(backup.data), 'test.tar.gz')})
    assert validation.status_code == 200
    assert validation.get_json()['valid'] is True
    backup.close()
