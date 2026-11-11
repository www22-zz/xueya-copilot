"""Recognize retired metadata-only demo rows without hiding user files."""
from .learning import COURSE


def is_demo_placeholder(document):
    return (not document.get('fileHash') and not document.get('chunks')
            and document.get('status') == '示例已索引'
            and any(document.get('id') == sample['id'] and document.get('name') == sample['name']
                    for sample in COURSE['documents']))
