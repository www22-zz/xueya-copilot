from backend.xueya.app import create_app
from backend.xueya.config import Config
from conftest import live_server
from scripts.seed_learning_demo import seed


def test_demo_import_uses_real_store_without_model_and_is_repeatable(tmp_path):
    app=create_app(Config(data_dir=tmp_path/'demo'))
    with live_server(app) as url:
        first=seed(url)
        second=seed(url)
        assert first==second
        assert len(app.state.platform.repo.all(app.state.platform.scope(),'document'))==1
        assert not app.state.platform.db.all('SELECT * FROM invocations')
