"""Document limits shared by the RAG HTTP and CPU extraction paths."""
PDF_MAX_BYTES = 64 * 1024 * 1024
OFFICE_MAX_BYTES = 10 * 1024 * 1024
TEXT_MAX_BYTES = 1024 * 1024


def document_limit(name):
    kind = str(name or '').rsplit('.', 1)[-1].lower()
    return PDF_MAX_BYTES if kind == 'pdf' else TEXT_MAX_BYTES if kind in ('txt', 'md') else OFFICE_MAX_BYTES
