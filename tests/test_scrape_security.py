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
    _, token = storage.create_api_token('integration', scope='api')
    response = app.test_client().open(path, method=method,
                                     headers={'Authorization': 'Bearer ' + token})
    assert response.status_code in (302, 403)


def test_metrics_token_is_denied_on_every_other_registered_route(secured_app):
    app, storage = secured_app
    _, token = storage.create_api_token('prometheus')
    client = app.test_client()
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get('/metrics', headers=headers).status_code == 200
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'metrics_bp.metrics':
            continue
        values = {name: (1 if converter.__class__.__name__ == 'IntegerConverter' else 'audit')
                  for name, converter in rule._converters.items()}
        with app.test_request_context():
            from flask import url_for
            path = url_for(rule.endpoint, **values)
        method = next(iter(rule.methods - {'HEAD', 'OPTIONS'}), 'GET')
        response = client.open(path, method=method, headers=headers)
        assert response.status_code == 403, (method, path, response.status_code)


def test_metrics_scope_applies_without_admin_password(secured_app):
    from app.runtime import get_runtime
    app, storage = secured_app
    get_runtime(app).config_manager.save({'admin_password': ''})
    _, token = storage.create_api_token('prometheus')
    assert app.test_client().get('/api/tokens', headers={'Authorization': 'Bearer ' + token}).status_code == 403


def test_token_scope_storage_and_legacy_migration(tmp_path):
    import sqlite3
    from werkzeug.security import generate_password_hash

    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE api_tokens (id INTEGER PRIMARY KEY, name TEXT, token_hash TEXT, '
                     'token_prefix TEXT, created_at TEXT, last_used_at TEXT, revoked INTEGER DEFAULT 0)')
        conn.execute('INSERT INTO api_tokens (name, token_hash, token_prefix, created_at) VALUES (?, ?, ?, ?)',
                     ('legacy', generate_password_hash('dsk_legacy'), 'dsk_lega', '2026-01-01T00:00:00Z'))
    storage = SnapshotStorage(str(path), max_days=7)
    assert storage.validate_api_token('dsk_legacy')['scope'] == 'api'
    _, metrics = storage.create_api_token('prometheus')
    assert storage.validate_api_token(metrics)['scope'] == 'metrics'
    token_id, api = storage.create_api_token('integration', scope='api')
    assert storage.validate_api_token(api)['scope'] == 'api'
    assert storage.revoke_api_token(token_id)
    assert storage.validate_api_token(api) is None
    with pytest.raises(ValueError):
        storage.create_api_token('invalid', scope='admin')
    assert {token['scope'] for token in storage.get_api_tokens()} == {'api', 'metrics'}


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
