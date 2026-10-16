"""Run from project root: python -m scripts.run_c_local_experiments."""
import argparse
import json
from pathlib import Path
from backend.agent.local_experiments import run_local_experiments, render_local_experiment_report
from backend.core import require


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='test-results/c-local-experiments-python')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = (root/args.output).resolve()
    require(output.is_relative_to(root), 'OUTPUT_OUTSIDE_PROJECT')
    value = json.loads((root/'backend/fixtures/local-study-course.json').read_text(encoding='utf-8'))
    result = run_local_experiments(value)
    output.mkdir(parents=True, exist_ok=True)
    (output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'report.md').write_text(render_local_experiment_report(result), encoding='utf-8')
    print('Completed 4 planning cases and 5 review events; synthetic records only.')


if __name__ == '__main__':
    main()
