from api.reports import report
from api.tests.test_domain import scene


def test_exported_html_has_clickable_absolute_evidence_and_escaped_content():
    s=scene([(0,.5),(.25,.5)])
    s.update(title='<script>alert(1)</script>',source={'title':'source','url':'https://example.org/source','author':'A&B','license':'CC BY-SA4.0'},processing={'sample_fps':4},notes=[])
    content,media=report(s,'A',3,'html',origin='https://demo.example')
    assert media=='text/html'
    assert '<a href="https://demo.example/media/unit/e.jpg"' in content
    assert '<a href="https://example.org/source"' in content
    assert '<script>' not in content
    assert '&lt;script&gt;' in content


def test_report_source_links_do_not_execute_javascript():
    s=scene([])
    s.update(title='unit',source={'title':'x','url':'javascript:alert(1)','author':'a','license':'cc'},notes=[])
    content,_=report(s,'A',3,'html',origin='https://demo.example')
    assert 'href="javascript:' not in content
