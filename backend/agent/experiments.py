from ..core import require, clone, fingerprint, check_cancel, resolve


def dataset_split(items, seed='c-v1', test_percent=20):
    require(type(test_percent) is int and 1 <= test_percent <= 99, 'INVALID_SPLIT')
    seen, result = set(), {'train': [], 'test': [], 'seed': seed}
    for item in items:
        require(item.get('id') and item.get('groupId') and item['id'] not in seen, 'INVALID_EXPERIMENT_ITEM')
        seen.add(item['id'])
        bucket = int(fingerprint([seed, item['groupId']])[:8], 16) % 100
        result['test' if bucket < test_percent else 'train'].append(clone(item))
    return result


async def compare_strategies(items, baseline, candidate, version, seed='c-v1', signal=None):
    require(version and callable(baseline) and callable(candidate) and isinstance(items, list) and items, 'INVALID_EXPERIMENT')
    results = []
    for item in items:
        check_cancel(signal)
        reference = await resolve(baseline(clone(item), {'seed': seed, 'signal': signal}))
        check_cancel(signal)
        proposed = await resolve(candidate(clone(item), {'seed': seed, 'signal': signal}))
        check_cancel(signal)
        results.append({'id': item['id'], 'baseline': reference, 'candidate': proposed})
    return {'version': version, 'seed': seed, 'datasetHash': fingerprint(items), 'count': len(items), 'results': results, 'interpretation': '受控回放比较；不据此宣称真实学习效果提升'}
