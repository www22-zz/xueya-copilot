"""Verification tests for sidebar quick-ask, suggested questions, and video courses module."""
from pathlib import Path
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config


def test_courses_and_sidebar_assets_exist():
    root = Path(__file__).resolve().parent.parent
    courses_js = root / "frontend" / "js" / "courses-workspace.js"
    courses_css = root / "frontend" / "css" / "courses.css"
    index_html = root / "frontend" / "index.html"
    views_js = root / "frontend" / "js" / "ui" / "workspace-views.js"
    controller_js = root / "frontend" / "js" / "workspace-controller.js"
    selection_js = root / "frontend" / "js" / "ui" / "selection-menu.js"
    app_js = root / "frontend" / "js" / "app.js"

    assert courses_js.exists(), "courses-workspace.js must exist"
    assert courses_css.exists(), "courses.css must exist"
    assert index_html.exists(), "index.html must exist"

    # 1. Verify index.html inclusions
    html_text = index_html.read_text(encoding="utf-8")
    assert "courses.css" in html_text, "courses.css must be linked in index.html"
    assert "courses-workspace.js" in html_text, "courses-workspace.js must be loaded in index.html"
    assert 'data-view="courses"' in html_text, "Course learning link must be present in space-nav"
    assert "课程学习" in html_text, "Course learning tab label must be present"

    # 2. Verify selection menu sidebar ask action
    sel_text = selection_js.read_text(encoding="utf-8")
    assert 'data-action="sidebar-ask"' in sel_text, "selection menu must have sidebar-ask action"
    assert "xueya:sidebar-ask" in sel_text, "selection menu must dispatch xueya:sidebar-ask"

    # 3. Verify workspace-views.js for suggested questions & sidebar ask panel
    wv_text = views_js.read_text(encoding="utf-8")
    assert "getFollowupQuestions" in wv_text, "getFollowupQuestions must be defined"
    assert "getInitialCourseSuggestions" in wv_text, "getInitialCourseSuggestions must be defined"
    assert "sidebarAskPanel" in wv_text, "sidebarAskPanel must be defined"
    assert "chatSidebarAskPanel" in wv_text, "chatSidebarAskPanel markup must be present"
    assert "用户可能会提问的问题" in wv_text, "Follow-up questions title must be present"
    assert "猜你想问" in wv_text, "Suggested questions must be present"

    # 4. Verify workspace-controller.js event handling
    ctrl_text = controller_js.read_text(encoding="utf-8")
    assert "xueya:sidebar-ask" in ctrl_text, "workspace-controller must listen to xueya:sidebar-ask"
    assert "data-toggle-sidebar-ask" in ctrl_text, "workspace-controller must handle sidebar-ask toggle"
    assert "sidebarAskForm" in ctrl_text, "workspace-controller must handle sidebarAskForm submission"

    # 5. Verify app.js routing and views
    app_text = app_js.read_text(encoding="utf-8")
    assert "titles.courses" in app_text, "titles.courses must be registered"
    assert "renders.courses" in app_text, "renders.courses must be registered"

    # 6. Verify courses-workspace.js contains rich CS courses
    cw_text = courses_js.read_text(encoding="utf-8")
    assert "cs-ds-algo" in cw_text, "Data structures & algorithms course must be present"
    assert "cs-os-kernel" in cw_text, "Operating systems course must be present"
    assert "cs-network-http" in cw_text, "Computer networks course must be present"
    assert "cs-ai-agent" in cw_text, "AI and Agent course must be present"
    assert "copilotPrompts" in cw_text, "In-class Copilot questions must be present"


def test_courses_and_sidebar_http_serving(tmp_path):
    root = Path(__file__).resolve().parent.parent
    config = Config(root=root, data_dir=tmp_path, port=0, platform_enabled=False)
    app = create_app(config)
    client = TestClient(app)

    # 1. Fetch index.html
    resp = client.get("/index.html")
    assert resp.status_code == 200
    assert "课程学习" in resp.text
    assert "courses.css" in resp.text
    assert "courses-workspace.js" in resp.text

    # 2. Fetch css/courses.css
    resp_css = client.get("/css/courses.css")
    assert resp_css.status_code == 200
    assert ".courses-container" in resp_css.text

    # 3. Fetch js/courses-workspace.js
    resp_js = client.get("/js/courses-workspace.js")
    assert resp_js.status_code == 200
    assert "XueyaCourses" in resp_js.text
